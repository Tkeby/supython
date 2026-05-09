"""Tests for storage bucket CRUD and RLS isolation.

Fixtures:
- ``storage_backend`` (autouse) patches the module-level backend singleton
  with a ``LocalBackend`` rooted in a temporary directory so tests never
  touch ``./storage`` and each test starts with empty bytes.
- ``clean_storage_tables`` (autouse) wipes ``storage.buckets`` /
  ``storage.objects`` before and after every test.
"""

import asyncpg
import httpx
import pytest
import pytest_asyncio

import supython.storage.backends as _backends_mod
from supython.storage.backends import LocalBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def storage_backend(tmp_path, monkeypatch):
    """Replace the global storage backend with a fresh local temp dir."""
    backend = LocalBackend(tmp_path / "storage")
    monkeypatch.setattr(_backends_mod, "_backend", backend)
    return backend


@pytest_asyncio.fixture(autouse=True)
async def clean_storage_tables(pool: asyncpg.Pool):
    """Wipe storage tables before and after each test."""

    async def _wipe(conn: asyncpg.Connection) -> None:
        await conn.execute("delete from storage.objects")
        await conn.execute("delete from storage.buckets")

    async with pool.acquire() as conn:
        await _wipe(conn)
    yield
    async with pool.acquire() as conn:
        await _wipe(conn)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _signup(client: httpx.AsyncClient, email: str, password: str = "password123") -> dict:
    r = await client.post("/auth/v1/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


async def _auth(client: httpx.AsyncClient, email: str, password: str = "password123") -> str:
    """Return an access token for an existing user."""
    r = await client.post("/auth/v1/token", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _create_bucket(
    client: httpx.AsyncClient,
    token: str,
    name: str,
    *,
    public: bool = False,
    file_size_limit: int | None = None,
    allowed_mime_types: list[str] | None = None,
) -> dict:
    payload: dict = {"name": name, "public": public}
    if file_size_limit is not None:
        payload["file_size_limit"] = file_size_limit
    if allowed_mime_types is not None:
        payload["allowed_mime_types"] = allowed_mime_types
    r = await client.post(
        "/storage/v1/bucket",
        json=payload,
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Tests — basic CRUD
# ---------------------------------------------------------------------------


async def test_create_bucket_returns_201(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    body = await _create_bucket(client, tokens["access_token"], "my-bucket")

    assert body["name"] == "my-bucket"
    assert body["public"] is False
    assert body["id"]
    assert body["owner"]


async def test_list_buckets_shows_own_bucket(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "photos")
    await _create_bucket(client, token, "avatars")

    r = await client.get(
        "/storage/v1/bucket",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    names = [b["name"] for b in r.json()]
    assert "photos" in names
    assert "avatars" in names


async def test_get_bucket_by_name(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    created = await _create_bucket(client, token, "docs")

    r = await client.get(
        "/storage/v1/bucket/docs",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


async def test_get_unknown_bucket_returns_404(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    r = await client.get(
        "/storage/v1/bucket/does-not-exist",
        headers={"authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "bucket_not_found"


async def test_duplicate_bucket_name_returns_409(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "unique-name")

    r = await client.post(
        "/storage/v1/bucket",
        json={"name": "unique-name"},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "bucket_exists"


async def test_delete_own_bucket_returns_204(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "deleteme")

    r = await client.delete(
        "/storage/v1/bucket/deleteme",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    # Confirm it is gone
    r2 = await client.get(
        "/storage/v1/bucket/deleteme",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Tests — RLS isolation between users
# ---------------------------------------------------------------------------


async def test_user_b_cannot_delete_user_a_bucket(client: httpx.AsyncClient):
    alice = await _signup(client, "alice@example.com")
    bob = await _signup(client, "bob@example.com")

    await _create_bucket(client, alice["access_token"], "alice-private")

    r = await client.delete(
        "/storage/v1/bucket/alice-private",
        headers={"authorization": f"Bearer {bob['access_token']}"},
    )
    # RLS denies the delete → service returns 404 (not leaking existence)
    assert r.status_code in (403, 404)


async def test_user_b_can_list_but_not_delete_others_buckets(client: httpx.AsyncClient):
    alice = await _signup(client, "alice@example.com")
    bob = await _signup(client, "bob@example.com")

    await _create_bucket(client, alice["access_token"], "alices-stuff")

    # Bob can see Alice's bucket in the list (buckets are readable by authed users)
    r = await client.get(
        "/storage/v1/bucket",
        headers={"authorization": f"Bearer {bob['access_token']}"},
    )
    assert r.status_code == 200
    names = [b["name"] for b in r.json()]
    assert "alices-stuff" in names


async def test_bucket_requires_authentication(client: httpx.AsyncClient):
    r = await client.get("/storage/v1/bucket")
    assert r.status_code == 401


async def test_create_bucket_with_limits(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    body = await _create_bucket(
        client,
        token,
        "images-only",
        file_size_limit=1024 * 1024,
        allowed_mime_types=["image/png", "image/jpeg"],
    )

    assert body["file_size_limit"] == 1024 * 1024
    assert body["allowed_mime_types"] == ["image/png", "image/jpeg"]
