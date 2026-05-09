"""Tests for storage object upload, download (full + range), delete,
size limits, mime-type restrictions, and S3Backend (mocked).

Fixtures:
- ``storage_backend`` (autouse) replaces the global backend singleton
  with a ``LocalBackend`` rooted in a temporary directory.
- ``clean_storage_tables`` (autouse) wipes storage tables around each test.
"""

import sys
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import httpx
import pytest
import pytest_asyncio

import supython.storage.backends as _backends_mod
from supython.storage.backends import LocalBackend, S3Backend

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


async def _upload(
    client: httpx.AsyncClient,
    token: str,
    bucket: str,
    path: str,
    content: bytes = b"hello world",
    content_type: str = "text/plain",
) -> dict:
    r = await client.post(
        f"/storage/v1/object/{bucket}/{path}",
        files={"file": (path.rsplit("/", 1)[-1], content, content_type)},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Tests — upload
# ---------------------------------------------------------------------------


async def test_upload_returns_201_with_metadata(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "uploads")

    body = await _upload(client, token, "uploads", "avatar.png", b"PNG bytes", "image/png")

    assert body["name"] == "avatar.png"
    assert body["bucket"] == "uploads"
    assert body["size"] == len(b"PNG bytes")
    assert body["mime_type"] == "image/png"
    assert body["etag"]
    assert body["id"]


async def test_upload_duplicate_path_returns_409(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "uploads")
    await _upload(client, token, "uploads", "readme.txt")

    r = await client.post(
        "/storage/v1/object/uploads/readme.txt",
        files={"file": ("readme.txt", b"second", "text/plain")},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "object_exists"


async def test_upload_to_nonexistent_bucket_returns_404(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    r = await client.post(
        "/storage/v1/object/ghost-bucket/file.txt",
        files={"file": ("file.txt", b"data", "text/plain")},
        headers={"authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "bucket_not_found"


# ---------------------------------------------------------------------------
# Tests — download (full)
# ---------------------------------------------------------------------------


async def test_download_full_object_returns_200(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    payload = b"the quick brown fox"
    await _create_bucket(client, token, "files")
    await _upload(client, token, "files", "fox.txt", payload, "text/plain")

    r = await client.get(
        "/storage/v1/object/files/fox.txt",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.content == payload
    assert r.headers["content-length"] == str(len(payload))
    assert r.headers["accept-ranges"] == "bytes"


# ---------------------------------------------------------------------------
# Tests — download (range)
# ---------------------------------------------------------------------------


async def test_range_download_returns_206(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    payload = b"0123456789abcdef"  # 16 bytes
    await _create_bucket(client, token, "files")
    await _upload(client, token, "files", "data.bin", payload, "application/octet-stream")

    r = await client.get(
        "/storage/v1/object/files/data.bin",
        headers={
            "authorization": f"Bearer {token}",
            "range": "bytes=0-9",
        },
    )
    assert r.status_code == 206
    assert r.content == b"0123456789"
    assert len(r.content) == 10
    assert "content-range" in r.headers
    assert r.headers["content-range"].startswith("bytes 0-9/")
    assert r.headers["content-length"] == "10"


async def test_range_download_open_end(client: httpx.AsyncClient):
    """``Range: bytes=4-`` should return everything from byte 4 onward."""
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    payload = b"ABCDEFGHIJ"  # 10 bytes
    await _create_bucket(client, token, "files")
    await _upload(client, token, "files", "alpha.bin", payload, "application/octet-stream")

    r = await client.get(
        "/storage/v1/object/files/alpha.bin",
        headers={
            "authorization": f"Bearer {token}",
            "range": "bytes=4-",
        },
    )
    assert r.status_code == 206
    assert r.content == b"EFGHIJ"
    assert r.headers["content-range"].startswith("bytes 4-9/10")


# ---------------------------------------------------------------------------
# Tests — RLS: non-owner is denied
# ---------------------------------------------------------------------------


async def test_nonowner_cannot_download_private_object(client: httpx.AsyncClient):
    alice = await _signup(client, "alice@example.com")
    bob = await _signup(client, "bob@example.com")

    await _create_bucket(client, alice["access_token"], "private")
    await _upload(client, alice["access_token"], "private", "secret.txt", b"top secret")

    r = await client.get(
        "/storage/v1/object/private/secret.txt",
        headers={"authorization": f"Bearer {bob['access_token']}"},
    )
    assert r.status_code == 404


async def test_nonowner_cannot_delete_object(client: httpx.AsyncClient):
    alice = await _signup(client, "alice@example.com")
    bob = await _signup(client, "bob@example.com")

    await _create_bucket(client, alice["access_token"], "mypics")
    await _upload(client, alice["access_token"], "mypics", "photo.jpg", b"JPEG data", "image/jpeg")

    r = await client.delete(
        "/storage/v1/object/mypics/photo.jpg",
        headers={"authorization": f"Bearer {bob['access_token']}"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tests — size and mime limits
# ---------------------------------------------------------------------------


async def test_file_too_large_returns_413(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "tiny", file_size_limit=10)

    r = await client.post(
        "/storage/v1/object/tiny/big.txt",
        files={"file": ("big.txt", b"A" * 11, "text/plain")},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == "file_too_large"


async def test_disallowed_mime_type_returns_415(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(
        client,
        token,
        "images-only",
        allowed_mime_types=["image/png", "image/jpeg"],
    )

    r = await client.post(
        "/storage/v1/object/images-only/script.js",
        files={"file": ("script.js", b"alert(1)", "application/javascript")},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 415
    assert r.json()["detail"]["code"] == "mime_not_allowed"


async def test_allowed_mime_type_uploads_ok(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(
        client, token, "imgs", allowed_mime_types=["image/png"]
    )

    r = await client.post(
        "/storage/v1/object/imgs/photo.png",
        files={"file": ("photo.png", b"\x89PNG", "image/png")},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# Tests — delete
# ---------------------------------------------------------------------------


async def test_delete_object_returns_204(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "trash")
    await _upload(client, token, "trash", "old.txt", b"bye")

    r = await client.delete(
        "/storage/v1/object/trash/old.txt",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    # Confirm gone
    r2 = await client.get(
        "/storage/v1/object/trash/old.txt",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Unit tests — S3Backend with mocked aioboto3
# ---------------------------------------------------------------------------


def _make_mock_aioboto3() -> MagicMock:
    """Return a MagicMock that behaves like the aioboto3 package."""
    mock_aioboto3 = MagicMock()

    # put_object response
    put_resp = {"ETag": '"abc123"'}
    # get_object response
    body_mock = MagicMock()

    async def _iter_chunks(_size: int) -> AsyncIterator[bytes]:
        yield b"hello"
        yield b" world"

    body_mock.iter_chunks = _iter_chunks
    get_resp = {
        "Body": body_mock,
        "ContentLength": 11,
        "ContentType": "text/plain",
        "ETag": '"abc123"',
        "ContentRange": "bytes 0-10/11",
    }
    head_resp = {
        "ContentLength": 11,
        "ETag": '"abc123"',
        "ContentType": "text/plain",
    }

    s3_client = AsyncMock()
    s3_client.put_object = AsyncMock(return_value=put_resp)
    s3_client.get_object = AsyncMock(return_value=get_resp)
    s3_client.head_object = AsyncMock(return_value=head_resp)
    s3_client.delete_object = AsyncMock(return_value={})

    client_ctx = MagicMock()
    client_ctx.__aenter__ = AsyncMock(return_value=s3_client)
    client_ctx.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.client = MagicMock(return_value=client_ctx)
    mock_aioboto3.Session = MagicMock(return_value=session)

    return mock_aioboto3


@pytest.fixture
def s3_backend():
    """S3Backend with fully mocked aioboto3."""
    mock_aioboto3 = _make_mock_aioboto3()
    with patch.dict(sys.modules, {"aioboto3": mock_aioboto3}):
        backend = S3Backend(
            bucket="test-physical-bucket",
            endpoint_url=None,
            region="us-east-1",
            access_key_id="key",
            secret_access_key="secret",
        )
        # Force session reset so _client() picks up the mocked aioboto3
        backend._session = None
        yield backend, mock_aioboto3


async def test_s3_backend_put(s3_backend):
    backend, mock_aioboto3 = s3_backend

    async def _data() -> AsyncIterator[bytes]:
        yield b"hello world"

    with patch.dict(sys.modules, {"aioboto3": mock_aioboto3}):
        stat = await backend.put("mybucket/file.txt", _data(), "text/plain")

    assert stat.key == "mybucket/file.txt"
    assert stat.size == 11
    assert stat.etag  # non-empty


async def test_s3_backend_get(s3_backend):
    backend, mock_aioboto3 = s3_backend

    with patch.dict(sys.modules, {"aioboto3": mock_aioboto3}):
        stream = await backend.get("mybucket/file.txt")

    chunks = [chunk async for chunk in stream.iterator]
    assert b"".join(chunks) == b"hello world"
    assert stream.content_length == 11
    assert stream.content_type == "text/plain"


async def test_s3_backend_stat(s3_backend):
    backend, mock_aioboto3 = s3_backend

    with patch.dict(sys.modules, {"aioboto3": mock_aioboto3}):
        stat = await backend.stat("mybucket/file.txt")

    assert stat is not None
    assert stat.size == 11
    assert stat.content_type == "text/plain"


async def test_s3_backend_delete(s3_backend):
    backend, mock_aioboto3 = s3_backend

    with patch.dict(sys.modules, {"aioboto3": mock_aioboto3}):
        # Should not raise
        await backend.delete("mybucket/file.txt")
