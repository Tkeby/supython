"""Integration tests for /admin/api/v1/storage endpoints."""

import asyncpg
import httpx
import pytest
import pytest_asyncio

import supython.storage.backends as _backends_mod
from supython import passwords
from supython.admin import session as admin_session
from supython.storage.backends import LocalBackend, make_object_key


@pytest.fixture(autouse=True)
def storage_backend(tmp_path, monkeypatch):
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


@pytest_asyncio.fixture
async def admin_user(pool: asyncpg.Pool):
    email = "ops@example.com"
    password = "correct horse battery staple"
    pw_hash = passwords.hash_password(password)
    async with pool.acquire() as conn:
        await conn.execute("delete from admin.admin_sessions")
        await conn.execute("delete from admin.admin_audit")
        await conn.execute("delete from admin.admin_users")
        admin_id = await conn.fetchval(
            """
            insert into admin.admin_users (email, password_hash, is_root)
            values ($1, $2, true)
            returning id
            """,
            email,
            pw_hash,
        )
    yield {"id": admin_id, "email": email, "password": password}
    async with pool.acquire() as conn:
        await conn.execute("delete from admin.admin_sessions")
        await conn.execute("delete from admin.admin_audit")
        await conn.execute("delete from admin.admin_users")


async def _login(client: httpx.AsyncClient, admin_user: dict) -> None:
    r = await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert r.status_code == 200, r.text
    assert client.cookies.get(admin_session.SESSION_COOKIE) is not None


async def _signup(client: httpx.AsyncClient, email: str) -> dict:
    r = await client.post(
        "/auth/v1/signup", json={"email": email, "password": "password123"}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _create_bucket(
    client: httpx.AsyncClient, token: str, name: str, *, public: bool = False
) -> dict:
    r = await client.post(
        "/storage/v1/bucket",
        json={"name": name, "public": public},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _upload(
    client: httpx.AsyncClient,
    token: str,
    bucket: str,
    path: str,
    data: bytes,
    content_type: str = "text/plain",
) -> dict:
    r = await client.post(
        f"/storage/v1/object/{bucket}/{path}",
        files={"file": (path.rsplit("/", 1)[-1], data, content_type)},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_buckets_requires_admin(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/storage/buckets")
    assert r.status_code == 401


async def test_objects_requires_admin(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/storage/buckets/x/objects")
    assert r.status_code == 401


async def test_sign_requires_admin(client: httpx.AsyncClient):
    r = await client.post(
        "/admin/api/v1/storage/objects/00000000-0000-0000-0000-000000000000/sign"
    )
    assert r.status_code == 401


async def test_delete_requires_admin(client: httpx.AsyncClient):
    r = await client.delete(
        "/admin/api/v1/storage/objects/00000000-0000-0000-0000-000000000000"
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# List buckets
# ---------------------------------------------------------------------------


async def test_list_buckets_includes_counts_and_size(
    client: httpx.AsyncClient, admin_user: dict
):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "photos", public=True)
    await _create_bucket(client, token, "docs")
    await _upload(client, token, "photos", "a.txt", b"hello")
    await _upload(client, token, "photos", "b.txt", b"world!!")

    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/storage/buckets")
    assert r.status_code == 200, r.text
    rows = r.json()
    by_name = {row["name"]: row for row in rows}

    photos = by_name["photos"]
    assert photos["public"] is True
    assert photos["object_count"] == 2
    assert photos["total_size"] == len(b"hello") + len(b"world!!")
    assert photos["owner"] is not None

    docs = by_name["docs"]
    assert docs["public"] is False
    assert docs["object_count"] == 0
    assert docs["total_size"] == 0


# ---------------------------------------------------------------------------
# List objects
# ---------------------------------------------------------------------------


async def test_list_objects_with_prefix(client: httpx.AsyncClient, admin_user: dict):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "photos")
    await _upload(client, token, "photos", "2024/jan/a.txt", b"a")
    await _upload(client, token, "photos", "2024/feb/b.txt", b"bb")
    await _upload(client, token, "photos", "2025/jan/c.txt", b"ccc")

    await _login(client, admin_user)
    r = await client.get(
        "/admin/api/v1/storage/buckets/photos/objects?prefix=2024/"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    names = [row["name"] for row in body["rows"]]
    assert names == ["2024/feb/b.txt", "2024/jan/a.txt"]
    assert body["prefix"] == "2024/"


async def test_list_objects_no_prefix_returns_all(
    client: httpx.AsyncClient, admin_user: dict
):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "photos")
    await _upload(client, token, "photos", "a.txt", b"a")
    await _upload(client, token, "photos", "b.txt", b"b")

    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/storage/buckets/photos/objects")
    assert r.status_code == 200
    assert r.json()["total"] == 2


async def test_list_objects_unknown_bucket_404(
    client: httpx.AsyncClient, admin_user: dict
):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/storage/buckets/nope/objects")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "bucket_not_found"


# ---------------------------------------------------------------------------
# Sign object
# ---------------------------------------------------------------------------


async def test_sign_object_default_service_role(
    client: httpx.AsyncClient, admin_user: dict, pool: asyncpg.Pool
):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "photos")
    obj = await _upload(client, token, "photos", "a.txt", b"hello")

    await _login(client, admin_user)
    r = await client.post(
        f"/admin/api/v1/storage/objects/{obj['id']}/sign",
        json={"expires_in": 60},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["signed_under_role"] == "service_role"
    assert body["expires_in"] == 60
    assert body["token"]
    assert body["signed_url"].endswith(f"token={body['token']}")

    async with pool.acquire() as conn:
        action = await conn.fetchval(
            "select action from admin.admin_audit where target = $1 order by at desc limit 1",
            obj["id"],
        )
    assert action == "storage.object.sign"


async def test_signed_url_is_fetchable(
    client: httpx.AsyncClient, admin_user: dict
):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "photos")
    obj = await _upload(client, token, "photos", "a.txt", b"hello-bytes")

    await _login(client, admin_user)
    r = await client.post(
        f"/admin/api/v1/storage/objects/{obj['id']}/sign",
        json={"expires_in": 60},
    )
    assert r.status_code == 200
    signed_token = r.json()["token"]

    fetch = await client.get(
        "/storage/v1/object/signed/photos/a.txt",
        params={"token": signed_token},
    )
    assert fetch.status_code == 200
    assert fetch.content == b"hello-bytes"


async def test_sign_object_authenticated_requires_sub(
    client: httpx.AsyncClient, admin_user: dict
):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "photos")
    obj = await _upload(client, token, "photos", "a.txt", b"x")

    await _login(client, admin_user)
    r = await client.post(
        f"/admin/api/v1/storage/objects/{obj['id']}/sign",
        json={"role": "authenticated"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "preview_sub_required"


async def test_sign_object_anon_denied_for_private_bucket(
    client: httpx.AsyncClient, admin_user: dict
):
    """anon role cannot read a private object → RLS denies → 404."""
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "photos")  # private
    obj = await _upload(client, token, "photos", "a.txt", b"x")

    await _login(client, admin_user)
    r = await client.post(
        f"/admin/api/v1/storage/objects/{obj['id']}/sign",
        json={"role": "anon"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "object_not_found"


async def test_sign_unknown_object_404(
    client: httpx.AsyncClient, admin_user: dict
):
    await _login(client, admin_user)
    r = await client.post(
        "/admin/api/v1/storage/objects/00000000-0000-0000-0000-000000000000/sign"
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "object_not_found"


# ---------------------------------------------------------------------------
# Delete object
# ---------------------------------------------------------------------------


async def test_delete_object_removes_metadata_and_bytes(
    client: httpx.AsyncClient, admin_user: dict, pool: asyncpg.Pool, storage_backend
):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "photos")
    obj = await _upload(client, token, "photos", "a.txt", b"hello")

    key_path = storage_backend._resolve(make_object_key("photos", "a.txt"))
    assert key_path.exists()

    await _login(client, admin_user)
    r = await client.delete(f"/admin/api/v1/storage/objects/{obj['id']}")
    assert r.status_code == 204

    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "select 1 from storage.objects where id = $1", obj["id"]
        )
        action = await conn.fetchval(
            "select action from admin.admin_audit where target = $1 order by at desc limit 1",
            obj["id"],
        )
    assert exists is None
    assert action == "storage.object.delete"
    assert not key_path.exists()


async def test_delete_unknown_object_404(
    client: httpx.AsyncClient, admin_user: dict
):
    await _login(client, admin_user)
    r = await client.delete(
        "/admin/api/v1/storage/objects/00000000-0000-0000-0000-000000000000"
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "object_not_found"
