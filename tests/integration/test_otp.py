"""Email OTP flow: request → capture token → POST verify → token pair."""

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


async def test_otp_always_returns_202_for_unknown_email(client, pool):
    r = await client.post("/auth/v1/otp", json={"email": "ghost@example.com"})
    assert r.status_code == 202
    payload = await _get_email_payload(pool)
    assert payload is None


async def test_otp_enqueues_email_job(client, pool):
    email = "otp@example.com"
    await _signup(client, email)

    r = await client.post("/auth/v1/otp", json={"email": email})
    assert r.status_code == 202
    payload = await _get_email_payload(pool)
    assert payload is not None
    assert email in payload["to"]


async def test_otp_verify_issues_token_pair(client, pool):
    email = "otpverify@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/otp", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    msg_text = payload["text"]
    raw_token = msg_text.split(": ")[-1].strip()

    r = await client.post(
        "/auth/v1/otp/verify",
        json={"email": email, "token": raw_token},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == email


async def test_otp_token_is_single_use(client, pool):
    email = "otpsingle@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/otp", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split(": ")[-1].strip()

    await client.post("/auth/v1/otp/verify", json={"email": email, "token": raw_token})

    r = await client.post(
        "/auth/v1/otp/verify",
        json={"email": email, "token": raw_token},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_token"


async def test_otp_wrong_email_returns_400(client, pool):
    email = "otpemail@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/otp", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split(": ")[-1].strip()

    r = await client.post(
        "/auth/v1/otp/verify",
        json={"email": "wrong@example.com", "token": raw_token},
    )
    assert r.status_code == 400


async def test_invalid_otp_token_returns_400(client):
    r = await client.post(
        "/auth/v1/otp/verify",
        json={"email": "nobody@example.com", "token": "notavalidtoken"},
    )
    assert r.status_code == 400
