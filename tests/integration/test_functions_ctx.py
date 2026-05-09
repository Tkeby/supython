"""Ctx integration tests.

Exercises the per-request Ctx object delivered to user handlers:

- ``ctx.user`` identity (id, email, role) decoded from the bearer JWT.
- ``ctx.db`` RLS: each user only sees their own rows.
- ``ctx.storage`` upload + sign; RLS hides another user's objects.
- ``ctx.postgrest`` Authorization header forwarding (and absence for anon).
- ``ctx.send_email`` routes through the injected mailer.

All tests require a live Postgres pool (provided by the session-scoped
``pool`` fixture in conftest.py).
"""

import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest
import pytest_asyncio

import supython.functions.context as ctx_mod
import supython.storage.backends as _backends_mod
from supython import db as _db
from supython import tokens
from supython.functions.loader import FunctionRegistry, reset_registry, set_registry
from supython.storage.backends import LocalBackend

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "functions"


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def functions_registry():
    """Point the global dispatcher at the test fixture functions."""
    reg = FunctionRegistry(FIXTURES, hot_reload=True)
    reg.discover()
    set_registry(reg)
    yield reg
    reset_registry()


@pytest.fixture(autouse=True)
def storage_backend(tmp_path, monkeypatch):
    """Replace the global storage backend with a fresh local temp dir."""
    backend = LocalBackend(tmp_path / "storage")
    monkeypatch.setattr(_backends_mod, "_backend", backend)
    return backend


@pytest_asyncio.fixture(autouse=True)
async def clean_storage_tables(pool: asyncpg.Pool):
    async def _wipe(conn: asyncpg.Connection) -> None:
        await conn.execute("delete from storage.objects")
        await conn.execute("delete from storage.buckets")

    async with pool.acquire() as conn:
        await _wipe(conn)
    yield
    async with pool.acquire() as conn:
        await _wipe(conn)


@pytest_asyncio.fixture(autouse=True)
async def clean_todos(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        await conn.execute("delete from public.todos")
    yield
    async with pool.acquire() as conn:
        await conn.execute("delete from public.todos")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _signup(client: httpx.AsyncClient, email: str) -> dict:
    r = await client.post(
        "/auth/v1/signup", json={"email": email, "password": "password123"}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _create_bucket(
    client: httpx.AsyncClient, token: str, name: str, *, public: bool = False
) -> None:
    r = await client.post(
        "/storage/v1/bucket",
        json={"name": name, "public": public},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# ctx.user
# ---------------------------------------------------------------------------


async def test_ctx_user_email_and_role(client: httpx.AsyncClient):
    data = await _signup(client, "alice@example.com")
    token = data["access_token"]

    r = await client.post(
        "/functions/me", headers={"authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "authenticated"
    assert body["id"] is not None


async def test_ctx_user_id_matches_sub_claim(client: httpx.AsyncClient):
    """ctx.user.id must equal the 'sub' UUID from the JWT."""
    user_id = uuid.uuid4()
    raw_jwt, _ = tokens.issue_access_token(user_id, "sub_test@example.com")

    r = await client.post(
        "/functions/me", headers={"authorization": f"Bearer {raw_jwt}"}
    )
    assert r.status_code == 200
    assert r.json()["id"] == str(user_id)


# ---------------------------------------------------------------------------
# ctx.db RLS
# ---------------------------------------------------------------------------


async def test_ctx_db_rls_isolates_users(client: httpx.AsyncClient, pool: asyncpg.Pool):
    """Each authenticated connection only sees the caller's own todos."""
    alice = await _signup(client, "alice_rls@example.com")
    bob = await _signup(client, "bob_rls@example.com")

    alice_claims = tokens.decode_access_token(alice["access_token"])
    bob_claims = tokens.decode_access_token(bob["access_token"])

    async with _db.as_role("authenticated", alice_claims) as conn:
        await conn.execute("insert into public.todos (title) values ($1)", "alice-todo")

    async with _db.as_role("authenticated", bob_claims) as conn:
        await conn.execute(
            "insert into public.todos (title) values ($1), ($2)",
            "bob-todo-1",
            "bob-todo-2",
        )

    r_alice = await client.post(
        "/functions/todo_count",
        headers={"authorization": f"Bearer {alice['access_token']}"},
    )
    assert r_alice.status_code == 200
    assert r_alice.json()["count"] == 1

    r_bob = await client.post(
        "/functions/todo_count",
        headers={"authorization": f"Bearer {bob['access_token']}"},
    )
    assert r_bob.status_code == 200
    assert r_bob.json()["count"] == 2


# ---------------------------------------------------------------------------
# ctx.storage
# ---------------------------------------------------------------------------


async def test_ctx_storage_upload_and_sign(client: httpx.AsyncClient):
    """upload.py writes via ctx.storage and returns a key + signed URL."""
    alice = await _signup(client, "alice_storage@example.com")
    token = alice["access_token"]
    await _create_bucket(client, token, "avatars")

    r = await client.post(
        "/functions/upload",
        content=b"hello payload",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["key"].startswith("avatars/")
    assert body["signed_url"]


async def test_ctx_storage_rls_other_user_denied(client: httpx.AsyncClient):
    """An object uploaded by alice is not visible to bob via the storage API."""
    alice = await _signup(client, "alice_stor2@example.com")
    bob = await _signup(client, "bob_stor2@example.com")
    await _create_bucket(client, alice["access_token"], "avatars")

    upload_r = await client.post(
        "/functions/upload",
        content=b"alice's secret",
        headers={"authorization": f"Bearer {alice['access_token']}"},
    )
    assert upload_r.status_code == 200

    # Strip the leading "avatars/" bucket prefix to get just the object path.
    full_key = upload_r.json()["key"]
    obj_path = full_key.split("/", 1)[1]

    r_bob = await client.get(
        f"/storage/v1/object/avatars/{obj_path}",
        headers={"authorization": f"Bearer {bob['access_token']}"},
    )
    assert r_bob.status_code == 404


# ---------------------------------------------------------------------------
# ctx.postgrest — Authorization header forwarding
# ---------------------------------------------------------------------------


async def test_ctx_postgrest_forwards_bearer_for_authenticated_request(
    client: httpx.AsyncClient, monkeypatch
):
    """Authenticated call: the caller's JWT is forwarded to PostgREST."""
    captured: list[str | None] = []

    class SpyPostgrestClient:
        def __init__(self, base_url: str, jwt: str | None) -> None:
            captured.append(jwt)

        async def get(self, url: str, **kw) -> httpx.Response:
            return httpx.Response(200, json=[])

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(ctx_mod, "PostgrestClient", SpyPostgrestClient)

    data = await _signup(client, "alice_pgrest@example.com")
    token = data["access_token"]

    r = await client.post(
        "/functions/proxy",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert len(captured) == 1
    assert captured[0] == token


async def test_ctx_postgrest_no_jwt_for_anon_request_without_token(
    client: httpx.AsyncClient, monkeypatch
):
    """Anon call with no bearer: PostgrestClient receives jwt=None."""
    captured: list[str | None] = []

    class SpyPostgrestClient:
        def __init__(self, base_url: str, jwt: str | None) -> None:
            captured.append(jwt)

        async def get(self, url: str, **kw) -> httpx.Response:
            return httpx.Response(200, json=[])

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(ctx_mod, "PostgrestClient", SpyPostgrestClient)

    # hello is auth="anon"; calling it without a token means raw_jwt=None.
    r = await client.get("/functions/hello")
    assert r.status_code == 200
    assert len(captured) == 1
    assert captured[0] is None


# ---------------------------------------------------------------------------
# ctx.send_email
# ---------------------------------------------------------------------------


async def test_ctx_send_email_captured_by_injected_mailer(
    client: httpx.AsyncClient, monkeypatch, capturing_mailer
):
    """notify.py calls ctx.send_email; message ends up in the capturing mailer."""
    monkeypatch.setattr(ctx_mod, "get_mailer", lambda: capturing_mailer)

    data = await _signup(client, "alice_mail@example.com")
    token = data["access_token"]

    r = await client.post(
        "/functions/notify",
        json={"to": "target@example.com", "subject": "Hello", "text": "World"},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == {"sent": True}

    assert len(capturing_mailer.messages) == 1
    msg = capturing_mailer.messages[0]
    assert "target@example.com" in msg.to
    assert msg.subject == "Hello"
    assert msg.text == "World"
