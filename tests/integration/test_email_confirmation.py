"""Signup email-confirmation flow and the honest email_confirmed_at semantics."""

import json

import asyncpg
import httpx
import pytest

from supython import settings

EMAIL = "confirmme@example.com"
PASSWORD = "password123"


@pytest.fixture
def require_confirmation(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRE_EMAIL_CONFIRMATION", "true")
    settings.get_settings.cache_clear()
    yield
    monkeypatch.delenv("AUTH_REQUIRE_EMAIL_CONFIRMATION", raising=False)
    settings.get_settings.cache_clear()


async def _signup(client: httpx.AsyncClient, email: str = EMAIL) -> httpx.Response:
    return await client.post(
        "/auth/v1/signup", json={"email": email, "password": PASSWORD}
    )


async def _latest_email_token(pool: asyncpg.Pool) -> str | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select payload from jobs.jobs where name = 'send_auth_email' "
            "order by created_at desc limit 1"
        )
    if row is None:
        return None
    p = row["payload"]
    payload = p if isinstance(p, dict) else json.loads(p)
    # Works for both shapes: "...: <token>" (otp/recover) and "...?token=<token>"
    # (magic link / signup confirm).
    tail = payload["text"].rsplit(maxsplit=1)[-1]
    return tail.split("?token=")[-1].strip()


async def _confirmed_at(pool: asyncpg.Pool, email: str = EMAIL):
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "select email_confirmed_at from auth.users where email = $1", email
        )


# ---------------------------------------------------------------------------
# Default mode (confirmation off)
# ---------------------------------------------------------------------------


async def test_signup_returns_tokens_but_no_email_proof(client, pool):
    r = await _signup(client)
    assert r.status_code == 201
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    # Signup no longer stamps email_confirmed_at: nothing was proven.
    assert await _confirmed_at(pool) is None


async def test_magic_link_verify_stamps_email_proof(client, pool):
    await _signup(client)
    await client.post("/auth/v1/magiclink", json={"email": EMAIL})
    token = await _latest_email_token(pool)
    r = await client.post(f"/auth/v1/magiclink/verify?token={token}")
    assert r.status_code == 200
    assert await _confirmed_at(pool) is not None


async def test_otp_verify_stamps_email_proof(client, pool):
    await _signup(client)
    await client.post("/auth/v1/otp", json={"email": EMAIL})
    token = await _latest_email_token(pool)
    r = await client.post("/auth/v1/otp/verify", json={"email": EMAIL, "token": token})
    assert r.status_code == 200
    assert await _confirmed_at(pool) is not None


async def test_recover_verify_stamps_email_proof(client, pool):
    await _signup(client)
    await client.post("/auth/v1/recover", json={"email": EMAIL})
    token = await _latest_email_token(pool)
    r = await client.post(
        "/auth/v1/recover/verify",
        json={"email": EMAIL, "token": token, "password": "newpassword123"},
    )
    assert r.status_code == 200
    assert await _confirmed_at(pool) is not None


# ---------------------------------------------------------------------------
# Confirmation-required mode
# ---------------------------------------------------------------------------


async def test_signup_returns_202_without_tokens(require_confirmation, client, pool):
    r = await _signup(client)
    assert r.status_code == 202
    body = r.json()
    assert body["user"]["email"] == EMAIL
    assert body["confirmation_sent_at"]
    assert "access_token" not in body
    assert await _confirmed_at(pool) is None
    assert await _latest_email_token(pool) is not None


async def test_password_login_blocked_until_confirmed(
    require_confirmation, client, pool
):
    await _signup(client)
    r = await client.post(
        "/auth/v1/token", json={"email": EMAIL, "password": PASSWORD}
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "email_not_confirmed"


async def test_confirm_verify_issues_first_session(require_confirmation, client, pool):
    await _signup(client)
    token = await _latest_email_token(pool)

    r = await client.post(f"/auth/v1/confirm/verify?token={token}")
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == EMAIL
    assert await _confirmed_at(pool) is not None

    # Password login now works.
    r = await client.post(
        "/auth/v1/token", json={"email": EMAIL, "password": PASSWORD}
    )
    assert r.status_code == 200

    # Audit trail records the proof.
    async with pool.acquire() as conn:
        assert await conn.fetchval(
            "select 1 from auth.audit_log where event = 'email_confirmed'"
        )


async def test_confirm_token_is_single_use(require_confirmation, client, pool):
    await _signup(client)
    token = await _latest_email_token(pool)
    assert (await client.post(f"/auth/v1/confirm/verify?token={token}")).status_code == 200
    r = await client.post(f"/auth/v1/confirm/verify?token={token}")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_token"


async def test_confirm_verify_rejects_garbage_token(require_confirmation, client):
    r = await client.post("/auth/v1/confirm/verify?token=not-a-real-token")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_token"


async def test_resend_sends_new_token_and_old_still_works_flow(
    require_confirmation, client, pool
):
    await _signup(client)
    first = await _latest_email_token(pool)

    r = await client.post("/auth/v1/confirm/resend", json={"email": EMAIL})
    assert r.status_code == 202
    second = await _latest_email_token(pool)
    assert second is not None and second != first

    r = await client.post(f"/auth/v1/confirm/verify?token={second}")
    assert r.status_code == 200


async def test_resend_is_silent_for_unknown_email(require_confirmation, client, pool):
    r = await client.post(
        "/auth/v1/confirm/resend", json={"email": "ghost@example.com"}
    )
    assert r.status_code == 202
    assert await _latest_email_token(pool) is None


async def test_resend_is_silent_for_already_confirmed(
    require_confirmation, client, pool
):
    await _signup(client)
    token = await _latest_email_token(pool)
    await client.post(f"/auth/v1/confirm/verify?token={token}")

    r = await client.post("/auth/v1/confirm/resend", json={"email": EMAIL})
    assert r.status_code == 202
    # No new email beyond the original signup one.
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "select count(*) from jobs.jobs where name = 'send_auth_email'"
        )
    assert count == 1


async def test_refresh_of_preexisting_session_blocked_until_confirmed(
    client, pool, monkeypatch
):
    """A session issued while confirmation was off dies at its next refresh
    once the operator turns the requirement on."""
    r = await _signup(client)
    assert r.status_code == 201
    refresh_token = r.json()["refresh_token"]

    monkeypatch.setenv("AUTH_REQUIRE_EMAIL_CONFIRMATION", "true")
    settings.get_settings.cache_clear()
    try:
        r = await client.post(
            "/auth/v1/refresh", json={"refresh_token": refresh_token}
        )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "email_not_confirmed"
    finally:
        monkeypatch.delenv("AUTH_REQUIRE_EMAIL_CONFIRMATION", raising=False)
        settings.get_settings.cache_clear()
