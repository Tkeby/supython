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
