"""Unit tests for OAuth state signing with secret rotation grace window."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from supython import secretset, settings
from supython.auth.service import _state_signer, oauth_finish, oauth_start


@pytest.fixture(autouse=True)
def _reset_caches():
    settings.get_settings.cache_clear()
    secretset.clear_cache()
    yield
    settings.get_settings.cache_clear()
    secretset.clear_cache()


@pytest.fixture
def secretset_env(monkeypatch, tmp_path):
    secrets_dir = tmp_path / "secrets"
    manifest = tmp_path / "secrets.json"
    monkeypatch.setenv("SECRETS_DIR", str(secrets_dir))
    monkeypatch.setenv("SECRETS_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("STORAGE_SIGNED_URL_SECRET", "")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "")
    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "3600")
    settings.get_settings.cache_clear()
    secretset.clear_cache()
    yield tmp_path, secrets_dir, manifest
    settings.get_settings.cache_clear()
    secretset.clear_cache()


def _async_run(coro):
    return asyncio.run(coro)


class _FakeProvider:
    name = "mock"

    async def authorize_url(self, state, redirect_uri, code_verifier):
        return f"https://example.com/auth?state={state}"

    async def exchange(self, code, redirect_uri, code_verifier):
        from supython.auth.providers import ProviderProfile
        return ProviderProfile(
            provider_user_id="ext_42",
            email="mock@example.com",
            raw={"id": "ext_42", "email": "mock@example.com"},
        )


def test_oauth_start_signs_with_active_secret(secretset_env, monkeypatch):
    secretset.rotate("oauth_state")
    monkeypatch.setattr(
        "supython.auth.providers.registry.get_provider", lambda _name: _FakeProvider()
    )

    url = _async_run(oauth_start("mock", "http://localhost/callback"))
    assert "state=" in url


def test_oauth_finish_verifies_with_active_secret(secretset_env, monkeypatch):
    from unittest.mock import AsyncMock

    secretset.rotate("oauth_state")
    monkeypatch.setattr(
        "supython.auth.providers.registry.get_provider", lambda _name: _FakeProvider()
    )

    url = _async_run(oauth_start("mock", "http://localhost/callback"))
    state = url.split("state=")[1]

    mock_conn = AsyncMock()
    with pytest.raises(Exception):  # will fail at DB ops, but state verifies
        _async_run(oauth_finish(mock_conn, "mock", "code", state))


def test_oauth_finish_verifies_with_retired_secret_within_grace(
    secretset_env, monkeypatch
):
    from unittest.mock import AsyncMock

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.secretset._now", lambda: fixed[0])
    monkeypatch.setattr(
        "supython.auth.providers.registry.get_provider", lambda _name: _FakeProvider()
    )

    first = secretset.rotate("oauth_state")
    url = _async_run(oauth_start("mock", "http://localhost/callback"))
    state = url.split("state=")[1]

    second = secretset.rotate("oauth_state")
    fixed[0] = fixed[0] + timedelta(seconds=10)
    secretset.activate("oauth_state", second.kid)
    secretset.clear_cache()

    fixed[0] = fixed[0] + timedelta(seconds=60)
    mock_conn = AsyncMock()
    with pytest.raises(Exception):  # will fail at DB ops, but state verifies
        _async_run(oauth_finish(mock_conn, "mock", "code", state))


def test_oauth_finish_rejects_retired_secret_past_grace(secretset_env, monkeypatch):
    from unittest.mock import AsyncMock
    from supython.auth.service import AuthError

    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "100")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.secretset._now", lambda: fixed[0])
    monkeypatch.setattr(
        "supython.auth.providers.registry.get_provider", lambda _name: _FakeProvider()
    )

    first = secretset.rotate("oauth_state")
    url = _async_run(oauth_start("mock", "http://localhost/callback"))
    state = url.split("state=")[1]

    second = secretset.rotate("oauth_state")
    fixed[0] = fixed[0] + timedelta(seconds=10)
    secretset.activate("oauth_state", second.kid)
    secretset.clear_cache()

    fixed[0] = fixed[0] + timedelta(seconds=200)
    mock_conn = AsyncMock()
    with pytest.raises(AuthError, match="OAuth state is invalid or expired"):
        _async_run(oauth_finish(mock_conn, "mock", "code", state))


def test_fallback_to_settings_when_no_manifest(secretset_env, monkeypatch):
    monkeypatch.setenv("OAUTH_STATE_SECRET", "a" * 48)
    settings.get_settings.cache_clear()
    secretset.clear_cache()

    monkeypatch.setattr(
        "supython.auth.providers.registry.get_provider", lambda _name: _FakeProvider()
    )

    url = _async_run(oauth_start("mock", "http://localhost/callback"))
    assert "state=" in url


def test_missing_manifest_and_missing_env_secret_raises_clear_error(secretset_env):
    with pytest.raises(RuntimeError, match="no OAuth state secret configured"):
        _state_signer()
