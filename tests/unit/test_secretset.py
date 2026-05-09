"""Unit tests for the symmetric secret manifest module."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from supython import secretset, settings


@pytest.fixture(autouse=True)
def _reset_caches():
    settings.get_settings.cache_clear()
    secretset.clear_cache()
    yield
    settings.get_settings.cache_clear()
    secretset.clear_cache()


@pytest.fixture
def secretset_paths(monkeypatch, tmp_path: Path):
    secrets_dir = tmp_path / "secrets"
    manifest = tmp_path / "secrets.json"
    monkeypatch.setenv("SECRETS_DIR", str(secrets_dir))
    monkeypatch.setenv("SECRETS_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("STORAGE_SIGNED_URL_SECRET", "")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "")
    settings.get_settings.cache_clear()
    return tmp_path, secrets_dir, manifest


def test_load_manifest_missing_returns_none(secretset_paths):
    assert secretset.load_manifest() is None
    assert secretset.list_secrets("storage_signed_url") == []
    assert secretset.active_secret("storage_signed_url") is None
    assert secretset.has_manifest() is False


def test_rotate_adds_secret_and_manifest_entry(secretset_paths):
    _, secrets_dir, manifest = secretset_paths

    entry = secretset.rotate("storage_signed_url")

    assert (secrets_dir / f"storage_signed_url.{entry.kid}.secret").is_file()
    assert manifest.is_file()

    payload = json.loads(manifest.read_text())
    assert payload["storage_signed_url"]["active"] == entry.kid
    assert len(payload["storage_signed_url"]["keys"]) == 1
    assert payload["storage_signed_url"]["keys"][0]["kid"] == entry.kid
    assert payload["storage_signed_url"]["keys"][0]["status"] == "active"


def test_rotate_second_call_keeps_first_active(secretset_paths):
    first = secretset.rotate("storage_signed_url")
    second = secretset.rotate("storage_signed_url")

    assert first.kid != second.kid
    assert secretset.active_secret("storage_signed_url").kid == first.kid
    statuses = {e.kid: e.status for e in secretset.list_secrets("storage_signed_url")}
    assert statuses[first.kid] == "active"
    assert statuses[second.kid] == "verifying"


def test_activate_flips_active_pointer_and_retires_previous(secretset_paths, monkeypatch):
    fixed = datetime(2026, 4, 24, 22, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("supython.secretset._now", lambda: fixed)

    first = secretset.rotate("storage_signed_url")
    second = secretset.rotate("storage_signed_url")

    secretset.activate("storage_signed_url", second.kid)

    assert secretset.active_secret("storage_signed_url").kid == second.kid
    statuses = {e.kid: e for e in secretset.list_secrets("storage_signed_url")}
    assert statuses[second.kid].status == "active"
    assert statuses[second.kid].retired_at is None
    assert statuses[first.kid].status == "retired"
    assert statuses[first.kid].retired_at == fixed


def test_activate_unknown_kid_raises(secretset_paths):
    secretset.rotate("storage_signed_url")
    with pytest.raises(KeyError, match="kid not in"):
        secretset.activate("storage_signed_url", "nope")


def test_activate_without_manifest_raises(secretset_paths):
    with pytest.raises(FileNotFoundError):
        secretset.activate("storage_signed_url", "anything")


def test_prune_respects_grace_window(secretset_paths, monkeypatch):
    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "3600")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.secretset._now", lambda: fixed[0])

    first = secretset.rotate("storage_signed_url")
    second = secretset.rotate("storage_signed_url")
    fixed[0] = fixed[0] + timedelta(seconds=10)
    secretset.activate("storage_signed_url", second.kid)
    fixed[0] = fixed[0] + timedelta(seconds=60)

    removed = secretset.prune("storage_signed_url")

    assert removed == []
    assert {e.kid for e in secretset.list_secrets("storage_signed_url")} == {first.kid, second.kid}


def test_prune_drops_secrets_past_grace(secretset_paths, monkeypatch):
    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "100")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.secretset._now", lambda: fixed[0])

    first = secretset.rotate("storage_signed_url")
    second = secretset.rotate("storage_signed_url")
    secretset.activate("storage_signed_url", second.kid)
    fixed[0] = fixed[0] + timedelta(seconds=200)

    removed = secretset.prune("storage_signed_url")

    assert removed == [first.kid]
    assert {e.kid for e in secretset.list_secrets("storage_signed_url")} == {second.kid}
    assert not (secretset.secrets_dir() / f"storage_signed_url.{first.kid}.secret").exists()
    assert (secretset.secrets_dir() / f"storage_signed_url.{second.kid}.secret").exists()


def test_prune_force_drops_all_retired(secretset_paths, monkeypatch):
    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "999999")
    settings.get_settings.cache_clear()

    first = secretset.rotate("storage_signed_url")
    second = secretset.rotate("storage_signed_url")
    secretset.activate("storage_signed_url", second.kid)

    removed = secretset.prune("storage_signed_url", force_all=True)

    assert removed == [first.kid]
    assert {e.kid for e in secretset.list_secrets("storage_signed_url")} == {second.kid}


def test_import_legacy_single_secret_creates_manifest(secretset_paths, monkeypatch):
    monkeypatch.setenv("STORAGE_SIGNED_URL_SECRET", "a" * 48)
    settings.get_settings.cache_clear()

    entry = secretset.import_legacy_single_secret("storage_signed_url")

    assert entry is not None
    assert entry.status == "active"
    assert secretset.active_secret("storage_signed_url").kid == entry.kid
    assert (secretset.secrets_dir() / f"storage_signed_url.{entry.kid}.secret").is_file()
    assert secretset.has_manifest()


def test_import_legacy_single_secret_is_idempotent(secretset_paths):
    secretset.rotate("storage_signed_url")
    assert secretset.import_legacy_single_secret("storage_signed_url") is None


def test_import_legacy_single_secret_no_legacy_no_op(secretset_paths):
    assert secretset.import_legacy_single_secret("storage_signed_url") is None


def test_import_legacy_rejects_short_secret(secretset_paths, monkeypatch):
    class _FakeSettings:
        secrets_dir = secretset_paths[1]
        secrets_manifest_path = secretset_paths[2]
        storage_signed_url_secret = "short"
        oauth_state_secret = None

    monkeypatch.setattr("supython.secretset.get_settings", lambda: _FakeSettings())

    assert secretset.import_legacy_single_secret("storage_signed_url") is None


def test_load_verification_secrets_includes_active_and_recent_retired(
    secretset_paths, monkeypatch
):
    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "3600")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.secretset._now", lambda: fixed[0])

    first = secretset.rotate("storage_signed_url")
    second = secretset.rotate("storage_signed_url")
    secretset.activate("storage_signed_url", second.kid)
    fixed[0] = fixed[0] + timedelta(seconds=60)

    secretset.clear_cache()
    secrets = secretset.load_verification_secrets("storage_signed_url")
    kids = {kid for _value, kid in secrets}
    assert kids == {first.kid, second.kid}


def test_load_verification_secrets_excludes_expired_retired(
    secretset_paths, monkeypatch
):
    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "100")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.secretset._now", lambda: fixed[0])

    first = secretset.rotate("storage_signed_url")
    second = secretset.rotate("storage_signed_url")
    secretset.activate("storage_signed_url", second.kid)
    fixed[0] = fixed[0] + timedelta(seconds=200)

    secretset.clear_cache()
    secrets = secretset.load_verification_secrets("storage_signed_url")
    kids = {kid for _value, kid in secrets}
    assert kids == {second.kid}


def test_load_signing_secret_returns_none_when_manifest_absent(secretset_paths):
    secretset.clear_cache()
    assert secretset.load_signing_secret("storage_signed_url") is None


def test_load_signing_secret_returns_none_when_section_missing(secretset_paths):
    """One secret family in the manifest must not break the other family.

    Per §18 "each secret family still rotates independently" — when the
    manifest has ``storage_signed_url`` but no ``oauth_state`` section,
    callers must fall back to the legacy env var for ``oauth_state``.
    """
    secretset.rotate("storage_signed_url")
    secretset.clear_cache()

    assert secretset.load_manifest() is not None
    assert secretset.load_signing_secret("oauth_state") is None


def test_load_signing_secret_raises_when_active_kid_dangles(secretset_paths):
    secretset.rotate("storage_signed_url")
    manifest = secretset.load_manifest()
    manifest["storage_signed_url"]["active"] = "missing-kid"
    secretset.write_manifest(manifest)
    secretset.clear_cache()

    with pytest.raises(RuntimeError, match="not present in manifest"):
        secretset.load_signing_secret("storage_signed_url")


def test_load_signing_secret_raises_when_manifest_has_no_active_secret(
    secretset_paths, monkeypatch
):
    monkeypatch.setenv("STORAGE_SIGNED_URL_SECRET", "a" * 48)
    settings.get_settings.cache_clear()

    secretset.import_legacy_single_secret("storage_signed_url")
    # manually clear active
    manifest = secretset.load_manifest()
    manifest["storage_signed_url"]["active"] = None
    secretset.write_manifest(manifest)
    secretset.clear_cache()

    with pytest.raises(RuntimeError, match="no active secret"):
        secretset.load_signing_secret("storage_signed_url")


def test_manifest_is_atomic_write_no_tmp_left(secretset_paths):
    _, _, manifest = secretset_paths
    secretset.rotate("storage_signed_url")
    tmp_path = manifest.with_suffix(manifest.suffix + ".tmp")
    assert manifest.is_file()
    assert not tmp_path.exists()


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX mode bits only")
def test_secret_files_have_0600_perms(secretset_paths):
    secretset.rotate("storage_signed_url")
    entry = secretset.active_secret("storage_signed_url")
    mode = entry.secret_path.stat().st_mode & 0o777
    assert mode == 0o600, oct(mode)
