"""Password reset: request recover → capture token → verify → new password works."""

import json

import httpx
import asyncpg


async def _signup(client: httpx.AsyncClient, email: str) -> dict:
    r = await client.post(
        "/auth/v1/signup",
        json={"email": email, "password": "oldpassword123"},
    )
    assert r.status_code == 201
    return r.json()


async def _get_email_payload(pool: asyncpg.Pool) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select payload from jobs.jobs where name = 'send_auth_email' order by created_at desc limit 1"
        )
    if row is None:
        return None
    p = row["payload"]
    return p if isinstance(p, dict) else json.loads(p)


async def test_recover_always_returns_202_even_for_unknown_email(client, pool):
    r = await client.post(
        "/auth/v1/recover",
        json={"email": "nobody@example.com"},
    )
    assert r.status_code == 202
    payload = await _get_email_payload(pool)
    assert payload is None


async def test_recover_enqueues_email_job(client, pool):
    await _signup(client, "recover@example.com")
    r = await client.post(
        "/auth/v1/recover",
        json={"email": "recover@example.com"},
    )
    assert r.status_code == 202
    payload = await _get_email_payload(pool)
    assert payload is not None
    assert "recover@example.com" in payload["to"]
    assert "token" in payload["text"].lower()


async def test_verify_recover_issues_new_token_pair(client, pool):
    email = "resetme@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/recover", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None

    raw_token = payload["text"].split(": ")[-1].strip()

    r = await client.post(
        "/auth/v1/recover/verify",
        json={"email": email, "token": raw_token, "password": "newpassword456"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["user"]["email"] == email


async def test_verify_recover_new_password_works(client, pool):
    email = "pwchange@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/recover", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split(": ")[-1].strip()

    await client.post(
        "/auth/v1/recover/verify",
        json={"email": email, "token": raw_token, "password": "newpassword456"},
    )

    r_old = await client.post(
        "/auth/v1/token",
        json={"email": email, "password": "oldpassword123"},
    )
    assert r_old.status_code == 401

    r_new = await client.post(
        "/auth/v1/token",
        json={"email": email, "password": "newpassword456"},
    )
    assert r_new.status_code == 200


async def test_recover_token_is_single_use(client, pool):
    email = "singleuse@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/recover", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split(": ")[-1].strip()

    await client.post(
        "/auth/v1/recover/verify",
        json={"email": email, "token": raw_token, "password": "newpassword456"},
    )

    r = await client.post(
        "/auth/v1/recover/verify",
        json={"email": email, "token": raw_token, "password": "anotherpassword789"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_token"


async def test_verify_recover_writes_audit_log(client, pool):
    email = "audit@example.com"
    await _signup(client, email)
    await client.post("/auth/v1/recover", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split(": ")[-1].strip()

    r = await client.post(
        "/auth/v1/recover/verify",
        json={"email": email, "token": raw_token, "password": "newpassword456"},
    )
    assert r.status_code == 200

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select event, payload from auth.audit_log where event = 'password_change'"
        )

    assert row is not None
    assert row["event"] == "password_change"
    audit_payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
    assert audit_payload["via"] == "recover"


async def test_failed_verify_recover_writes_no_audit_log(client, pool):
    email = "noaudit@example.com"
    await _signup(client, email)

    r = await client.post(
        "/auth/v1/recover/verify",
        json={"email": email, "token": "badtoken", "password": "newpassword456"},
    )
    assert r.status_code == 400

    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "select count(*) from auth.audit_log where event = 'password_change'"
        )
    assert count == 0


async def test_reset_revokes_all_existing_sessions(client, pool):
    email = "reset-revoke@example.com"
    s1 = await _signup(client, email)
    r = await client.post(
        "/auth/v1/token", json={"email": email, "password": "oldpassword123"}
    )
    s2 = r.json()

    await client.post("/auth/v1/recover", json={"email": email})
    payload = await _get_email_payload(pool)
    raw_token = payload["text"].split(": ")[-1].strip()
    r = await client.post(
        "/auth/v1/recover/verify",
        json={"email": email, "token": raw_token, "password": "brandnewpass789"},
    )
    assert r.status_code == 200
    fresh = r.json()["refresh_token"]

    # Every pre-reset session is dead; the pair issued by the reset survives.
    for dead in (s1["refresh_token"], s2["refresh_token"]):
        rr = await client.post("/auth/v1/refresh", json={"refresh_token": dead})
        assert rr.status_code == 401
    rr = await client.post("/auth/v1/refresh", json={"refresh_token": fresh})
    assert rr.status_code == 200


async def test_reset_invalidates_other_pending_recover_tokens(client, pool):
    email = "reset-pending@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/recover", json={"email": email})
    first = (await _get_email_payload(pool))["text"].split(": ")[-1].strip()
    await client.post("/auth/v1/recover", json={"email": email})
    second = (await _get_email_payload(pool))["text"].split(": ")[-1].strip()
    assert first != second

    r = await client.post(
        "/auth/v1/recover/verify",
        json={"email": email, "token": second, "password": "brandnewpass789"},
    )
    assert r.status_code == 200

    # The unused first token died with the reset. Asserted in the DB rather
    # than via a 4th HTTP call, which would trip the recover rate limit
    # (request + verify share the auth.recover bucket, 3 per window).
    async with pool.acquire() as conn:
        pending = await conn.fetchval(
            """
            select count(*) from auth.one_time_tokens ott
            join auth.users u on u.id = ott.user_id
            where u.email = $1 and ott.type = 'recover' and ott.used_at is null
            """,
            email,
        )
    assert pending == 0
