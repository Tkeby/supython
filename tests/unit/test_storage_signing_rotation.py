"""Unit tests for storage signing with secret rotation grace window."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from supython import secretset, settings
from supython.storage import signing


@pytest.fixture(autouse=True)
def _reset_caches():
    settings.get_settings.cache_clear()
    secretset.clear_cache()
    signing.reset_signer_cache()
    yield
    settings.get_settings.cache_clear()
    secretset.clear_cache()
    signing.reset_signer_cache()


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
    signing.reset_signer_cache()
    yield tmp_path, secrets_dir, manifest
    settings.get_settings.cache_clear()
    secretset.clear_cache()
    signing.reset_signer_cache()


def test_sign_uses_active_secret(secretset_env):
    secretset.rotate("storage_signed_url")
    token, _ = signing.sign("bucket", "path", 3600)
    signing.verify(token, "bucket", "path")


def test_verify_accepts_active_secret(secretset_env):
    secretset.rotate("storage_signed_url")
    token, _ = signing.sign("bucket", "path", 3600)
    signing.verify(token, "bucket", "path")  # must not raise


def test_verify_accepts_retired_secret_within_grace(secretset_env, monkeypatch):
    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.secretset._now", lambda: fixed[0])

    first = secretset.rotate("storage_signed_url")
    token, _ = signing.sign("bucket", "path", 3600)

    second = secretset.rotate("storage_signed_url")
    fixed[0] = fixed[0] + timedelta(seconds=10)
    secretset.activate("storage_signed_url", second.kid)
    secretset.clear_cache()
    signing.reset_signer_cache()

    fixed[0] = fixed[0] + timedelta(seconds=60)
    signing.verify(token, "bucket", "path")  # still within grace


def test_verify_rejects_retired_secret_past_grace(secretset_env, monkeypatch):
    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "100")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.secretset._now", lambda: fixed[0])

    first = secretset.rotate("storage_signed_url")
    token, _ = signing.sign("bucket", "path", 3600)

    second = secretset.rotate("storage_signed_url")
    fixed[0] = fixed[0] + timedelta(seconds=10)
    secretset.activate("storage_signed_url", second.kid)
    secretset.clear_cache()
    signing.reset_signer_cache()

    fixed[0] = fixed[0] + timedelta(seconds=200)
    with pytest.raises(signing.SignatureError):
        signing.verify(token, "bucket", "path")


def test_fallback_to_settings_when_no_manifest(secretset_env, monkeypatch):
    monkeypatch.setenv("STORAGE_SIGNED_URL_SECRET", "a" * 48)
    settings.get_settings.cache_clear()
    secretset.clear_cache()
    signing.reset_signer_cache()

    token, _ = signing.sign("bucket", "path", 3600)
    signing.verify(token, "bucket", "path")


def test_missing_manifest_and_missing_env_secret_raises_clear_error(secretset_env):
    with pytest.raises(RuntimeError, match="no storage signed-url secret configured"):
        signing.sign("bucket", "path", 3600)
