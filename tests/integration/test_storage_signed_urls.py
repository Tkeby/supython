"""Tests for signed URL issuance, verification, expiry, tamper-detection,
and the public-bucket endpoint.

Fixtures:
- ``storage_backend`` (autouse) replaces the global backend singleton
  with a ``LocalBackend`` rooted in a temporary directory.
- ``clean_storage_tables`` (autouse) wipes storage tables around each test.
"""

import time
from unittest.mock import patch

import asyncpg
import httpx
import pytest
import pytest_asyncio

import supython.storage.backends as _backends_mod
from supython.storage import signing
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


async def _create_bucket(
    client: httpx.AsyncClient,
    token: str,
    name: str,
    *,
    public: bool = False,
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
    content: bytes = b"hello signed world",
) -> dict:
    r = await client.post(
        f"/storage/v1/object/{bucket}/{path}",
        files={"file": (path.rsplit("/", 1)[-1], content, "text/plain")},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _sign(
    client: httpx.AsyncClient,
    token: str,
    bucket: str,
    path: str,
    expires_in: int = 3600,
) -> dict:
    r = await client.post(
        f"/storage/v1/object/sign/{bucket}/{path}",
        json={"expires_in": expires_in},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Tests — happy path
# ---------------------------------------------------------------------------


async def test_issue_signed_url_returns_token_and_expiry(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "shared")
    await _upload(client, token, "shared", "doc.txt")

    body = await _sign(client, token, "shared", "doc.txt", expires_in=600)

    assert body["token"]
    assert body["signed_url"]
    assert body["expires_in"] == 600
    assert body["expires_at"]
    assert "/storage/v1/object/signed/shared/doc.txt" in body["signed_url"]


async def test_fetch_signed_url_within_ttl_returns_200(client: httpx.AsyncClient):
    payload = b"supersecret content"
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "shared")
    await _upload(client, token, "shared", "secret.txt", payload)

    sign_body = await _sign(client, token, "shared", "secret.txt", expires_in=3600)

    # Fetch via signed URL (no Authorization header needed)
    r = await client.get(
        f"/storage/v1/object/signed/shared/secret.txt?token={sign_body['token']}"
    )
    assert r.status_code == 200
    assert r.content == payload


async def test_signed_url_supports_range_download(client: httpx.AsyncClient):
    payload = b"ABCDEFGHIJKLMNOP"  # 16 bytes
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "shared")
    await _upload(client, token, "shared", "data.bin", payload)

    sign_body = await _sign(client, token, "shared", "data.bin")

    r = await client.get(
        f"/storage/v1/object/signed/shared/data.bin?token={sign_body['token']}",
        headers={"range": "bytes=0-4"},
    )
    assert r.status_code == 206
    assert r.content == b"ABCDE"


# ---------------------------------------------------------------------------
# Tests — tamper detection
# ---------------------------------------------------------------------------


async def test_tampered_token_returns_400_invalid_signature(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "shared")
    await _upload(client, token, "shared", "file.txt")

    sign_body = await _sign(client, token, "shared", "file.txt")
    real_token = sign_body["token"]

    # Corrupt one character in the signature portion
    tampered = real_token[:-4] + "XXXX"
    r = await client.get(
        f"/storage/v1/object/signed/shared/file.txt?token={tampered}"
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_signature"


async def test_signed_url_wrong_path_returns_400(client: httpx.AsyncClient):
    """A token signed for one path must not work for a different path."""
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "shared")
    await _upload(client, token, "shared", "real.txt")
    await _upload(client, token, "shared", "other.txt")

    sign_body = await _sign(client, token, "shared", "real.txt")

    # Reuse the token for a different path
    r = await client.get(
        f"/storage/v1/object/signed/shared/other.txt?token={sign_body['token']}"
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_signature"


async def test_signed_url_wrong_bucket_returns_400(client: httpx.AsyncClient):
    """A token signed for one bucket must not work for a different bucket."""
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "bucket-a")
    await _create_bucket(client, token, "bucket-b")
    await _upload(client, token, "bucket-a", "file.txt")
    await _upload(client, token, "bucket-b", "file.txt")

    sign_body = await _sign(client, token, "bucket-a", "file.txt")

    r = await client.get(
        f"/storage/v1/object/signed/bucket-b/file.txt?token={sign_body['token']}"
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_signature"


# ---------------------------------------------------------------------------
# Tests — expiry (monkeypatched time)
# ---------------------------------------------------------------------------


async def test_expired_signed_url_returns_400_signature_expired(client: httpx.AsyncClient):
    """Simulate expiry by monkeypatching ``time.time`` to return a future timestamp."""
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "shared")
    await _upload(client, token, "shared", "doc.txt")

    # Issue a signed URL with a 1-second TTL
    sign_body = await _sign(client, token, "shared", "doc.txt", expires_in=1)
    signed_token = sign_body["token"]

    # itsdangerous calls time.time() during unsign to check max_age.
    # Patch it to return a timestamp 60 seconds in the future so the 1-second
    # TTL is definitively exceeded.
    future_time = time.time() + 60.0
    with patch("time.time", return_value=future_time):
        r = await client.get(
            f"/storage/v1/object/signed/shared/doc.txt?token={signed_token}"
        )

    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "signature_expired"


# ---------------------------------------------------------------------------
# Tests — unit-level verify
# ---------------------------------------------------------------------------


def test_verify_valid_token_does_not_raise():
    token, _ = signing.sign("bucket", "path/to/file.txt", 3600)
    signing.verify(token, "bucket", "path/to/file.txt")  # must not raise


def test_verify_tampered_token_raises_invalid_signature():
    token, _ = signing.sign("bucket", "file.txt", 3600)
    bad = token[:-4] + "ZZZZ"
    with pytest.raises(signing.SignatureError):
        signing.verify(bad, "bucket", "file.txt")


def test_verify_wrong_path_raises_invalid_signature():
    token, _ = signing.sign("bucket", "a.txt", 3600)
    with pytest.raises(signing.SignatureError):
        signing.verify(token, "bucket", "b.txt")


def test_verify_expired_token_raises_expired_signature():
    token, _ = signing.sign("bucket", "file.txt", 1)
    future = time.time() + 60.0
    with patch("time.time", return_value=future), pytest.raises(signing.ExpiredSignature):
        signing.verify(token, "bucket", "file.txt")


# ---------------------------------------------------------------------------
# Tests — public buckets
# ---------------------------------------------------------------------------


async def test_public_bucket_accessible_without_token(client: httpx.AsyncClient):
    payload = b"public data here"
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "pub", public=True)
    await _upload(client, token, "pub", "readme.txt", payload)

    # No Authorization header
    r = await client.get("/storage/v1/object/public/pub/readme.txt")
    assert r.status_code == 200
    assert r.content == payload


async def test_private_bucket_not_accessible_via_public_endpoint(client: httpx.AsyncClient):
    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "priv", public=False)
    await _upload(client, token, "priv", "secret.txt", b"shh")

    # anon role cannot see private objects
    r = await client.get("/storage/v1/object/public/priv/secret.txt")
    assert r.status_code == 404


async def test_nonowner_can_read_public_bucket_object(client: httpx.AsyncClient):
    """Any user — even one who doesn't own the object — can read public objects."""
    alice = await _signup(client, "alice@example.com")
    await _signup(client, "bob@example.com")

    await _create_bucket(client, alice["access_token"], "open", public=True)
    await _upload(client, alice["access_token"], "open", "shared.txt", b"open to all")

    # Bob fetches without a token via the public endpoint
    r = await client.get("/storage/v1/object/public/open/shared.txt")
    assert r.status_code == 200
    assert r.content == b"open to all"


async def test_signed_url_still_verifies_after_rotation_within_grace(
    client: httpx.AsyncClient, monkeypatch
):
    """A URL signed before rotation must still verify after activation while within grace."""
    from datetime import datetime, timedelta, timezone
    from supython import secretset, settings

    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "3600")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.secretset._now", lambda: fixed[0])

    tokens = await _signup(client, "alice@example.com")
    token = tokens["access_token"]
    await _create_bucket(client, token, "shared")
    await _upload(client, token, "shared", "doc.txt", b"rotation test")

    sign_body = await _sign(client, token, "shared", "doc.txt", expires_in=3600)
    signed_token = sign_body["token"]

    # Rotate and activate
    secretset.rotate("storage_signed_url")
    new_kid = secretset.active_secret("storage_signed_url").kid
    secretset.rotate("storage_signed_url")
    second = secretset.active_secret("storage_signed_url")
    # Actually we need to rotate again to have a new one to activate
    secretset.rotate("storage_signed_url")
    all_kids = [e.kid for e in secretset.list_secrets("storage_signed_url")]
    newest = [k for k in all_kids if k != new_kid][0]
    fixed[0] = fixed[0] + timedelta(seconds=10)
    secretset.activate("storage_signed_url", newest)
    secretset.clear_cache()

    fixed[0] = fixed[0] + timedelta(seconds=60)

    r = await client.get(
        f"/storage/v1/object/signed/shared/doc.txt?token={signed_token}"
    )
    assert r.status_code == 200
    assert r.content == b"rotation test"
