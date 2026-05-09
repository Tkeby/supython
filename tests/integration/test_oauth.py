"""OAuth flow tests with a mocked provider.exchange (no real HTTP to Google/GitHub)."""

import json
from urllib.parse import parse_qs, urlparse

import pytest

from supython.auth.providers import Provider, ProviderProfile


class _MockProvider(Provider):
    """Deterministic provider that always returns a fixed identity."""

    name = "mock"
    _PROFILE = ProviderProfile(
        provider_user_id="ext_user_42",
        email="oauth_user@example.com",
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
        return self._PROFILE


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
