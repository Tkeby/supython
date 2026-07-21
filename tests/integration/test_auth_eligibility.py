"""Account-eligibility gate: an ineligible user is refused a session (GHSA-27m9-35j7-7g5f).

(A) `banned_until` was inert; issuance now checks it at the single funnel
(`_issue_pair`) plus `refresh_grant`, which mints its own pair. A banned user
gets `403 account_disabled`.

(B) A pre-created row with `activated_at is null` cannot authenticate through
the passwordless endpoints; it gets `403 account_inactive` until
`service.activate_user` is called. Signup and OAuth sign-in activate inline.

The `request_*` endpoints stay enumeration-resistant (202 for a banned or
inactive email); the gate lives at grant/verify, not request.
"""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest

from supython.auth import service
from supython.auth.providers import Provider, ProviderProfile


async def _signup(client: httpx.AsyncClient, email: str, password: str = "password123") -> dict:
    r = await client.post("/auth/v1/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


async def _set_banned_until(pool: asyncpg.Pool, email: str, until: datetime | None) -> None:
    async with pool.acquire() as conn:
        updated = await conn.fetchval(
            "update auth.users set banned_until = $1 where email = $2 returning id",
            until,
            email,
        )
    assert updated is not None, f"no user to ban for {email}"


async def _ban(pool: asyncpg.Pool, email: str) -> None:
    await _set_banned_until(pool, email, datetime.now(UTC) + timedelta(hours=1))


async def _get_email_payload(pool: asyncpg.Pool) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select payload from jobs.jobs where name = 'send_auth_email' "
            "order by created_at desc limit 1"
        )
    if row is None:
        return None
    p = row["payload"]
    return p if isinstance(p, dict) else json.loads(p)


async def _precreate_inactive(pool: asyncpg.Pool, email: str) -> UUID:
    """Insert a bare auth.users row — no password, activated_at null — as an
    invite-style consumer would, and return its id."""
    async with pool.acquire() as conn:
        uid = await conn.fetchval(
            "insert into auth.users (email) values ($1) returning id", email
        )
    return uid


async def _activated_at(pool: asyncpg.Pool, email: str) -> datetime | None:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "select activated_at from auth.users where email = $1", email
        )


# ---------------------------------------------------------------------------
# Banned user is refused on every grant type
# ---------------------------------------------------------------------------


async def test_banned_user_cannot_password_grant(client, pool):
    email = "banned-pw@example.com"
    await _signup(client, email, "correcthorse")
    await _ban(pool, email)

    r = await client.post("/auth/v1/token", json={"email": email, "password": "correcthorse"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "account_disabled"


async def test_banned_user_cannot_refresh(client, pool):
    email = "banned-refresh@example.com"
    tokens = await _signup(client, email)
    await _ban(pool, email)

    r = await client.post("/auth/v1/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "account_disabled"


async def test_banned_user_refresh_token_is_not_burned(client, pool):
    """A refused refresh must not revoke the token: unban, then it works again."""
    email = "banned-refresh-intact@example.com"
    tokens = await _signup(client, email)
    await _ban(pool, email)

    blocked = await client.post(
        "/auth/v1/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert blocked.status_code == 403

    await _set_banned_until(pool, email, None)
    allowed = await client.post(
        "/auth/v1/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert allowed.status_code == 200, allowed.text


async def test_banned_user_cannot_verify_magic_link(client, pool):
    email = "banned-magic@example.com"
    await _signup(client, email)

    # Request the link while still eligible, then ban before verifying.
    await client.post("/auth/v1/magiclink", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split("?token=")[-1].strip()

    await _ban(pool, email)

    r = await client.get(f"/auth/v1/magiclink/verify?token={raw_token}")
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "account_disabled"


async def test_banned_user_cannot_verify_otp(client, pool):
    email = "banned-otp@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/otp", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split(": ")[-1].strip()

    await _ban(pool, email)

    r = await client.post("/auth/v1/otp/verify", json={"email": email, "token": raw_token})
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "account_disabled"


async def test_banned_user_cannot_verify_recover(client, pool):
    email = "banned-recover@example.com"
    await _signup(client, email)

    await client.post("/auth/v1/recover", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split(": ")[-1].strip()

    await _ban(pool, email)

    r = await client.post(
        "/auth/v1/recover/verify",
        json={"email": email, "token": raw_token, "password": "newpassword456"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "account_disabled"


# ---------------------------------------------------------------------------
# OAuth callback is gated too (shares the _issue_pair funnel)
# ---------------------------------------------------------------------------


class _MockProvider(Provider):
    name = "mock"
    _PROFILE = ProviderProfile(
        provider_user_id="ext_oauth_elig",
        email="oauth-elig@example.com",
        email_verified=True,
        raw={"id": "ext_oauth_elig", "email": "oauth-elig@example.com"},
    )

    async def authorize_url(
        self, state: str, redirect_uri: str, code_verifier: str | None = None
    ) -> str:
        return (
            f"https://provider.example/auth?response_type=code&state={state}"
            f"&redirect_uri={redirect_uri}"
        )

    async def exchange(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> ProviderProfile:
        return self._PROFILE


@pytest.fixture
def mock_provider(monkeypatch):
    provider = _MockProvider()
    monkeypatch.setattr(
        "supython.auth.providers.registry.get_provider",
        lambda _name: provider,
    )
    return provider


async def _run_oauth_callback(client: httpx.AsyncClient) -> httpx.Response:
    redirect_uri = "http://localhost:3000/callback"
    r_auth = await client.get(f"/auth/v1/authorize/mock?redirect_uri={redirect_uri}")
    state = parse_qs(urlparse(r_auth.headers["location"]).query)["state"][0]
    return await client.get(f"/auth/v1/callback/mock?code=fake_code&state={state}")


async def test_banned_user_cannot_oauth_callback(client, pool, mock_provider):
    # First callback creates the user (and succeeds, 302).
    first = await _run_oauth_callback(client)
    assert first.status_code == 302

    await _ban(pool, "oauth-elig@example.com")

    second = await _run_oauth_callback(client)
    assert second.status_code == 403, second.text
    assert second.json()["detail"]["code"] == "account_disabled"


# ---------------------------------------------------------------------------
# An expired / lifted ban issues normally
# ---------------------------------------------------------------------------


async def test_expired_ban_allows_login(client, pool):
    email = "expired-ban@example.com"
    await _signup(client, email, "correcthorse")
    await _set_banned_until(pool, email, datetime.now(UTC) - timedelta(hours=1))

    r = await client.post("/auth/v1/token", json={"email": email, "password": "correcthorse"})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


async def test_unban_restores_login(client, pool):
    email = "unban@example.com"
    await _signup(client, email, "correcthorse")
    await _ban(pool, email)

    blocked = await client.post(
        "/auth/v1/token", json={"email": email, "password": "correcthorse"}
    )
    assert blocked.status_code == 403

    await _set_banned_until(pool, email, None)
    allowed = await client.post(
        "/auth/v1/token", json={"email": email, "password": "correcthorse"}
    )
    assert allowed.status_code == 200, allowed.text


# ---------------------------------------------------------------------------
# Enumeration resistance: request_* stays 202 for a banned email
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/auth/v1/magiclink", "/auth/v1/otp", "/auth/v1/recover"])
async def test_request_endpoints_stay_202_for_banned_email(client, pool, path):
    email = "banned-enum@example.com"
    await _signup(client, email)
    await _ban(pool, email)

    r = await client.post(path, json={"email": email})
    assert r.status_code == 202, r.text


# ---------------------------------------------------------------------------
# (B) Not-yet-activated accounts (activated_at is null)
# ---------------------------------------------------------------------------


async def test_signup_activates_user(client, pool):
    email = "signup-active@example.com"
    await _signup(client, email)
    assert await _activated_at(pool, email) is not None


async def test_inactive_user_cannot_verify_magic_link(client, pool):
    email = "inactive-magic@example.com"
    await _precreate_inactive(pool, email)

    r_req = await client.post("/auth/v1/magiclink", json={"email": email})
    assert r_req.status_code == 202
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split("?token=")[-1].strip()

    r = await client.get(f"/auth/v1/magiclink/verify?token={raw_token}")
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "account_inactive"


async def test_inactive_user_cannot_verify_otp(client, pool):
    email = "inactive-otp@example.com"
    await _precreate_inactive(pool, email)

    await client.post("/auth/v1/otp", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split(": ")[-1].strip()

    r = await client.post("/auth/v1/otp/verify", json={"email": email, "token": raw_token})
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "account_inactive"


async def test_inactive_user_cannot_verify_recover_and_password_not_set(client, pool):
    email = "inactive-recover@example.com"
    uid = await _precreate_inactive(pool, email)

    await client.post("/auth/v1/recover", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split(": ")[-1].strip()

    r = await client.post(
        "/auth/v1/recover/verify",
        json={"email": email, "token": raw_token, "password": "newpassword456"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "account_inactive"

    # The 403 is raised inside verify_recover's transaction, so the password
    # write and the token consumption must have rolled back.
    async with pool.acquire() as conn:
        pw = await conn.fetchval(
            "select encrypted_password from auth.users where id = $1", uid
        )
        used = await conn.fetchval(
            "select used_at from auth.one_time_tokens where user_id = $1", uid
        )
    assert pw is None
    assert used is None


async def test_activate_user_enables_login(client, pool):
    """A refused verify must not burn the token: after activate_user, the same
    magic-link token verifies successfully."""
    email = "activate-me@example.com"
    uid = await _precreate_inactive(pool, email)

    await client.post("/auth/v1/magiclink", json={"email": email})
    payload = await _get_email_payload(pool)
    assert payload is not None
    raw_token = payload["text"].split("?token=")[-1].strip()

    blocked = await client.get(f"/auth/v1/magiclink/verify?token={raw_token}")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "account_inactive"

    async with pool.acquire() as conn:
        await service.activate_user(conn, uid)

    allowed = await client.get(f"/auth/v1/magiclink/verify?token={raw_token}")
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["access_token"]


async def test_activate_user_is_idempotent(pool):
    email = "idempotent@example.com"
    uid = await _precreate_inactive(pool, email)

    async with pool.acquire() as conn:
        await service.activate_user(conn, uid)
        first = await conn.fetchval(
            "select activated_at from auth.users where id = $1", uid
        )
        await service.activate_user(conn, uid)
        second = await conn.fetchval(
            "select activated_at from auth.users where id = $1", uid
        )
    assert first is not None
    assert first == second  # re-activation does not move the timestamp


async def test_activate_user_unknown_id_raises(pool):
    async with pool.acquire() as conn:
        with pytest.raises(service.AuthError) as exc:
            await service.activate_user(conn, uuid4())
    assert exc.value.code == "user_not_found"
    assert exc.value.status == 404


async def test_oauth_signin_activates_new_user(client, pool, mock_provider):
    r = await _run_oauth_callback(client)
    assert r.status_code == 302
    assert await _activated_at(pool, "oauth-elig@example.com") is not None


async def test_oauth_signin_activates_precreated_user(client, pool, mock_provider):
    # A consumer pre-creates the invite row by email; the user's first OAuth
    # sign-in (same email) links the identity and activates them.
    email = "oauth-elig@example.com"
    await _precreate_inactive(pool, email)
    assert await _activated_at(pool, email) is None

    r = await _run_oauth_callback(client)
    assert r.status_code == 302
    assert await _activated_at(pool, email) is not None


@pytest.mark.parametrize("path", ["/auth/v1/magiclink", "/auth/v1/otp", "/auth/v1/recover"])
async def test_request_endpoints_stay_202_for_inactive_email(client, pool, path):
    email = "inactive-enum@example.com"
    await _precreate_inactive(pool, email)

    r = await client.post(path, json={"email": email})
    assert r.status_code == 202, r.text
