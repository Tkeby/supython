"""OAuth flow tests with a mocked provider.exchange (no real HTTP to Google/GitHub)."""

import json
from urllib.parse import parse_qs, urlparse

import pytest

from supython.auth.providers import Provider, ProviderProfile


class _MockProvider(Provider):
    """Deterministic provider that always returns a fixed identity.

    The default profile is email-verified, matching a well-behaved provider;
    tests for the fail-closed path swap ``profile`` for an unverified one.
    """

    name = "mock"

    def __init__(self, profile: ProviderProfile | None = None) -> None:
        self.profile = profile or ProviderProfile(
            provider_user_id="ext_user_42",
            email="oauth_user@example.com",
            email_verified=True,
            raw={"id": "ext_user_42", "email": "oauth_user@example.com"},
        )

    async def authorize_url(
        self, state: str, redirect_uri: str, code_verifier: str | None = None
    ) -> str:
        url = (
            f"https://provider.example/auth"
            f"?response_type=code&state={state}&redirect_uri={redirect_uri}"
        )
        if code_verifier:
            url += f"&code_challenge_method=S256&code_challenge={code_verifier}"
        return url

    async def exchange(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> ProviderProfile:
        return self.profile


@pytest.fixture
def mock_provider(monkeypatch):
    provider = _MockProvider()
    monkeypatch.setattr(
        "supython.auth.providers.registry.get_provider",
        lambda _name: provider,
    )
    return provider


async def test_authorize_redirects_to_provider(client, mock_provider):
    redirect_uri = "http://localhost:3000/callback"
    r = await client.get(
        f"/auth/v1/authorize/mock?redirect_uri={redirect_uri}",
    )
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("https://provider.example/auth")

    # State and PKCE params are embedded in the provider URL
    parsed = urlparse(location)
    qs = parse_qs(parsed.query)
    assert "state" in qs
    assert qs.get("code_challenge_method") == ["S256"]
    assert "code_challenge" in qs


async def test_callback_issues_tokens_and_redirects(client, mock_provider):
    redirect_uri = "http://localhost:3000/callback"

    # Step 1: get the provider redirect URL (and extract signed state from it)
    r_auth = await client.get(
        f"/auth/v1/authorize/mock?redirect_uri={redirect_uri}",
    )
    assert r_auth.status_code == 302
    provider_url = r_auth.headers["location"]
    state = parse_qs(urlparse(provider_url).query)["state"][0]

    # Step 2: simulate the provider callback
    r_cb = await client.get(
        f"/auth/v1/callback/mock?code=fake_code&state={state}",
    )
    assert r_cb.status_code == 302
    final_url = r_cb.headers["location"]

    assert final_url.startswith(redirect_uri + "#")
    fragment = dict(
        pair.split("=", 1) for pair in final_url.split("#", 1)[1].split("&")
    )
    assert "access_token" in fragment
    assert "refresh_token" in fragment
    assert fragment["token_type"] == "bearer"


async def test_callback_creates_user_and_identity(client, mock_provider, pool):
    redirect_uri = "http://localhost:3000/callback"

    r_auth = await client.get(f"/auth/v1/authorize/mock?redirect_uri={redirect_uri}")
    state = parse_qs(urlparse(r_auth.headers["location"]).query)["state"][0]

    await client.get(f"/auth/v1/callback/mock?code=fake_code&state={state}")

    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "select id, email from auth.users where email = 'oauth_user@example.com'"
        )
        assert user is not None

        identity = await conn.fetchrow(
            """
            select provider, provider_user_id
            from auth.identities
            where provider = 'mock' and provider_user_id = 'ext_user_42'
            """
        )
        assert identity is not None
        assert identity["provider_user_id"] == "ext_user_42"


async def test_callback_second_login_reuses_existing_user(client, mock_provider, pool):
    """A second OAuth login with the same identity must not create a duplicate user."""
    redirect_uri = "http://localhost:3000/callback"

    async def _do_oauth():
        r = await client.get(f"/auth/v1/authorize/mock?redirect_uri={redirect_uri}")
        state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
        await client.get(f"/auth/v1/callback/mock?code=fake_code&state={state}")

    await _do_oauth()
    await _do_oauth()

    async with pool.acquire() as conn:
        user_count = await conn.fetchval(
            "select count(*) from auth.users where email = 'oauth_user@example.com'"
        )
        assert user_count == 1

        identity_count = await conn.fetchval(
            "select count(*) from auth.identities where provider_user_id = 'ext_user_42'"
        )
        assert identity_count == 1


async def test_invalid_state_returns_400(client, mock_provider):
    r = await client.get(
        "/auth/v1/callback/mock?code=fake_code&state=totallyfakestate",
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_state"


async def test_callback_writes_identity_linked_audit_log(client, mock_provider, pool):
    redirect_uri = "http://localhost:3000/callback"
    r = await client.get(f"/auth/v1/authorize/mock?redirect_uri={redirect_uri}")
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    await client.get(f"/auth/v1/callback/mock?code=fake_code&state={state}")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select event, payload from auth.audit_log where event = 'oauth_identity_linked'"
        )

    assert row is not None
    assert row["event"] == "oauth_identity_linked"
    payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
    assert payload["provider"] == "mock"
    assert payload["provider_user_id"] == "ext_user_42"


async def test_callback_second_login_no_duplicate_audit_log(client, mock_provider, pool):
    redirect_uri = "http://localhost:3000/callback"

    async def _do_oauth():
        r = await client.get(f"/auth/v1/authorize/mock?redirect_uri={redirect_uri}")
        state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
        await client.get(f"/auth/v1/callback/mock?code=fake_code&state={state}")

    await _do_oauth()
    await _do_oauth()

    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "select count(*) from auth.audit_log where event = 'oauth_identity_linked'"
        )
    assert count == 1


async def test_oauth_state_still_verifies_after_rotation_within_grace(
    client, mock_provider, monkeypatch
):
    """An OAuth state issued before rotation must still verify after activation within grace."""
    from datetime import datetime, timedelta, timezone
    from supython import secretset, settings

    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "3600")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.secretset._now", lambda: fixed[0])

    redirect_uri = "http://localhost:3000/callback"

    r_auth = await client.get(f"/auth/v1/authorize/mock?redirect_uri={redirect_uri}")
    assert r_auth.status_code == 302
    state = parse_qs(urlparse(r_auth.headers["location"]).query)["state"][0]

    # Rotate and activate
    secretset.rotate("oauth_state")
    secretset.rotate("oauth_state")
    all_kids = [e.kid for e in secretset.list_secrets("oauth_state")]
    newest = all_kids[-1]
    fixed[0] = fixed[0] + timedelta(seconds=10)
    secretset.activate("oauth_state", newest)
    secretset.clear_cache()

    fixed[0] = fixed[0] + timedelta(seconds=60)

    r_cb = await client.get(f"/auth/v1/callback/mock?code=fake_code&state={state}")
    assert r_cb.status_code == 302


# ---------------------------------------------------------------------------
# Verified-email linking gates (pre-hijack defence)
# ---------------------------------------------------------------------------


async def _do_oauth_flow(client, redirect_uri="http://localhost:3000/callback"):
    r = await client.get(f"/auth/v1/authorize/mock?redirect_uri={redirect_uri}")
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    return await client.get(f"/auth/v1/callback/mock?code=fake_code&state={state}")


async def test_unverified_provider_email_is_refused(client, mock_provider, pool):
    mock_provider.profile = ProviderProfile(
        provider_user_id="ext_unverified",
        email="unverified@example.com",
        email_verified=False,
        raw={},
    )
    r = await _do_oauth_flow(client)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "provider_email_unverified"

    async with pool.acquire() as conn:
        assert not await conn.fetchval(
            "select 1 from auth.users where email = 'unverified@example.com'"
        )
        assert not await conn.fetchval(
            "select 1 from auth.identities where provider_user_id = 'ext_unverified'"
        )


async def test_existing_identity_signs_in_even_if_profile_unverified(
    client, mock_provider, pool
):
    """The verified-email gate guards linking/creation, not established identities."""
    r = await _do_oauth_flow(client)
    assert r.status_code == 302

    mock_provider.profile = ProviderProfile(
        provider_user_id="ext_user_42",
        email="oauth_user@example.com",
        email_verified=False,
        raw={},
    )
    r = await _do_oauth_flow(client)
    assert r.status_code == 302
    assert "access_token=" in r.headers["location"]


async def test_link_refused_into_unproven_password_account(client, mock_provider, pool):
    """Pre-hijack: attacker signs up with the victim's email; the victim's later
    OAuth sign-in must not be linked to the attacker-credentialed account."""
    r = await client.post(
        "/auth/v1/signup",
        json={"email": "oauth_user@example.com", "password": "attacker-pw1"},
    )
    assert r.status_code == 201  # signup no longer proves the email

    r = await _do_oauth_flow(client)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "email_conflict"

    async with pool.acquire() as conn:
        assert not await conn.fetchval(
            "select 1 from auth.identities where provider_user_id = 'ext_user_42'"
        )
        audit = await conn.fetchrow(
            "select payload from auth.audit_log where event = 'oauth_link_refused'"
        )
    assert audit is not None
    payload = (
        json.loads(audit["payload"])
        if isinstance(audit["payload"], str)
        else audit["payload"]
    )
    assert payload["reason"] == "unproven_email_with_password"


async def test_link_allowed_into_proven_password_account(client, mock_provider, pool):
    await client.post(
        "/auth/v1/signup",
        json={"email": "oauth_user@example.com", "password": "victim-pw123"},
    )
    async with pool.acquire() as conn:
        await conn.execute(
            "update auth.users set email_confirmed_at = now() "
            "where email = 'oauth_user@example.com'"
        )

    r = await _do_oauth_flow(client)
    assert r.status_code == 302
    assert "access_token=" in r.headers["location"]

    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "select count(*) from auth.users where email = 'oauth_user@example.com'"
        )
        assert count == 1
        assert await conn.fetchval(
            "select 1 from auth.identities where provider_user_id = 'ext_user_42'"
        )


async def test_link_allowed_into_passwordless_invite_row(client, mock_provider, pool):
    """An operator-created invite row (no password, unproven email) may come
    online via its first OAuth sign-in, which also stamps the email proof."""
    async with pool.acquire() as conn:
        await conn.execute(
            "insert into auth.users (email) values ('oauth_user@example.com')"
        )

    r = await _do_oauth_flow(client)
    assert r.status_code == 302
    assert "access_token=" in r.headers["location"]

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select email_confirmed_at, activated_at from auth.users "
            "where email = 'oauth_user@example.com'"
        )
    assert row["email_confirmed_at"] is not None
    assert row["activated_at"] is not None


async def test_oauth_created_user_has_email_proof(client, mock_provider, pool):
    await _do_oauth_flow(client)
    async with pool.acquire() as conn:
        confirmed = await conn.fetchval(
            "select email_confirmed_at from auth.users "
            "where email = 'oauth_user@example.com'"
        )
    assert confirmed is not None
