"""Magic-link flow: request → capture token → GET verify → token pair."""

import json

import asyncpg
import httpx


async def _signup(client: httpx.AsyncClient, email: str) -> None:
    r = await client.post(
        "/auth/v1/signup",
        json={"email": email, "password": "password123"},
    )
    assert r.status_code == 201


async def _get_email_payload(pool: asyncpg.Pool) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select payload from jobs.jobs where name = 'send_auth_email' order by created_at desc limit 1"
        )
    if row is None:
        return None
    p = row["payload"]
    return p if isinstance(p, dict) else json.loads(p)


async def test_magic_link_always_returns_202_for_unknown_email(client, pool):
    r = await client.post("/auth/v1/magiclink", json={"email": "ghost@example.com"})
    assert r.status_code == 202
    payload = await _get_email_payload(pool)
    assert payload is None


async def test_magic_link_enqueues_email_job(client, pool):
    email = "magic@example.com"
    await _signup(client, email)

    r = await client.post("/auth/v1/magiclink", json={"email": email})
    assert r.status_code == 202
    payload = await _get_email_payload(pool)
    assert payload is not None
    assert email in payload["to"]
    assert "token" in payload["text"].lower()


async def test_magic_link_verify_issues_token_pair(client, pool):
    email = "magicverify@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/magiclink", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    msg_text = payload["text"]
    raw_token = msg_text.split("?token=")[-1].strip()

    r = await client.get(f"/auth/v1/magiclink/verify?token={raw_token}")
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == email


async def test_magic_link_token_is_single_use(client, pool):
    email = "magicsingle@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/magiclink", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split("?token=")[-1].strip()

    await client.get(f"/auth/v1/magiclink/verify?token={raw_token}")

    r = await client.get(f"/auth/v1/magiclink/verify?token={raw_token}")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_token"


async def test_invalid_magic_link_token_returns_400(client):
    r = await client.get("/auth/v1/magiclink/verify?token=notavalidtoken")
    assert r.status_code == 400


async def test_magic_link_request_rejects_unlisted_redirect(client, monkeypatch):
    from supython.settings import get_settings

    monkeypatch.setenv("MAGIC_LINK_REDIRECT_ALLOWLIST", "https://app.example.com")
    get_settings.cache_clear()

    r = await client.post(
        "/auth/v1/magiclink",
        json={"email": "whoever@example.com", "redirect_url": "https://evil.example.com/x"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_redirect"
    get_settings.cache_clear()


async def test_magic_link_verify_redirects_when_requested(client, pool, monkeypatch):
    from supython.settings import get_settings

    monkeypatch.setenv(
        "MAGIC_LINK_REDIRECT_ALLOWLIST",
        "https://operator.example.com,http://localhost:5173",
    )
    get_settings.cache_clear()

    email = "magicredirect@example.com"
    await _signup(client, email)

    r = await client.post(
        "/auth/v1/magiclink",
        json={
            "email": email,
            "redirect_url": "http://localhost:5173/accept-invite",
        },
    )
    assert r.status_code == 202

    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split("?token=")[-1].strip()

    r = await client.get(f"/auth/v1/magiclink/verify?token={raw_token}")
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("http://localhost:5173/accept-invite#")
    assert "access_token=" in location
    assert "refresh_token=" in location
    get_settings.cache_clear()


async def test_magic_link_verify_without_redirect_still_returns_json(client, pool):
    # No redirect_url at request time ⇒ legacy JSON behaviour, unchanged.
    email = "magicjson@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/magiclink", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split("?token=")[-1].strip()

    r = await client.get(f"/auth/v1/magiclink/verify?token={raw_token}")
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["user"]["email"] == email


async def test_magic_link_ttl_is_clamped_to_max(client, pool, monkeypatch):
    from supython.settings import get_settings

    monkeypatch.setenv("MAGIC_LINK_MAX_TTL", "3600")
    get_settings.cache_clear()

    email = "magicttl@example.com"
    await _signup(client, email)

    # Request a ttl far beyond the 1-hour ceiling; the stored expiry should be
    # clamped, not honoured verbatim.
    r = await client.post(
        "/auth/v1/magiclink", json={"email": email, "ttl": 999999}
    )
    assert r.status_code == 202

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select expires_at, created_at from auth.one_time_tokens
            where type = 'magic_link'
            order by created_at desc limit 1
            """
        )
    assert row is not None
    delta = (row["expires_at"] - row["created_at"]).total_seconds()
    assert delta <= 3600 + 5  # small allowance for test execution time
    get_settings.cache_clear()
