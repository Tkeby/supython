"""Unit tests for the JWT keyset manifest module."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from supython import jwks, keyset, settings


@pytest.fixture(autouse=True)
def _reset_caches():
    settings.get_settings.cache_clear()
    jwks.clear_cache()
    yield
    settings.get_settings.cache_clear()
    jwks.clear_cache()


@pytest.fixture
def keyset_paths(monkeypatch, tmp_path: Path):
    keys_dir = tmp_path / "keys"
    manifest = tmp_path / "keyset.json"
    monkeypatch.setenv("JWT_KEYS_DIR", str(keys_dir))
    monkeypatch.setenv("JWT_KEYSET_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("JWT_ALG", "RS256")
    monkeypatch.setenv("JWT_KID", "")
    monkeypatch.setenv("JWT_PRIVATE_KEY", "")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")
    settings.get_settings.cache_clear()
    return tmp_path, keys_dir, manifest


def test_load_manifest_missing_returns_none(keyset_paths):
    assert keyset.load_manifest() is None
    assert keyset.list_keys() == []
    assert keyset.active_kid() is None
    assert keyset.has_manifest() is False


def test_add_key_appends_pem_and_manifest_entry(keyset_paths):
    _, keys_dir, manifest = keyset_paths

    entry = keyset.add_key("RS256", status="verifying")

    assert (keys_dir / f"{entry.kid}.pem").is_file()
    assert manifest.is_file()

    payload = json.loads(manifest.read_text())
    assert payload["active"] == entry.kid  # first key auto-promoted
    assert len(payload["keys"]) == 1
    assert payload["keys"][0]["kid"] == entry.kid
    assert payload["keys"][0]["status"] == "active"


def test_add_key_second_call_keeps_first_active(keyset_paths):
    first = keyset.add_key("RS256", status="verifying")
    second = keyset.add_key("RS256", status="verifying")

    assert first.kid != second.kid
    assert keyset.active_kid() == first.kid
    statuses = {e.kid: e.status for e in keyset.list_keys()}
    assert statuses[first.kid] == "active"
    assert statuses[second.kid] == "verifying"


def test_activate_flips_active_pointer_and_retires_previous(keyset_paths, monkeypatch):
    fixed = datetime(2026, 4, 24, 22, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("supython.keyset._now", lambda: fixed)

    first = keyset.add_key("RS256", status="verifying")
    second = keyset.add_key("RS256", status="verifying")

    keyset.activate(second.kid)

    assert keyset.active_kid() == second.kid
    statuses = {e.kid: e for e in keyset.list_keys()}
    assert statuses[second.kid].status == "active"
    assert statuses[second.kid].retired_at is None
    assert statuses[first.kid].status == "retired"
    assert statuses[first.kid].retired_at == fixed


def test_activate_unknown_kid_raises(keyset_paths):
    keyset.add_key("RS256")
    with pytest.raises(KeyError, match="kid not in keyset"):
        keyset.activate("nope")


def test_activate_without_manifest_raises(keyset_paths):
    with pytest.raises(FileNotFoundError):
        keyset.activate("anything")


def test_prune_respects_grace_window(keyset_paths, monkeypatch):
    monkeypatch.setenv("JWT_ROTATION_GRACE_SECONDS", "3600")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.keyset._now", lambda: fixed[0])

    first = keyset.add_key("RS256")
    second = keyset.add_key("RS256")
    fixed[0] = fixed[0] + timedelta(seconds=10)
    keyset.activate(second.kid)
    fixed[0] = fixed[0] + timedelta(seconds=60)

    removed = keyset.prune()

    assert removed == []
    assert {e.kid for e in keyset.list_keys()} == {first.kid, second.kid}


def test_prune_drops_kids_past_grace(keyset_paths, monkeypatch):
    monkeypatch.setenv("JWT_ROTATION_GRACE_SECONDS", "100")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.keyset._now", lambda: fixed[0])

    first = keyset.add_key("RS256")
    second = keyset.add_key("RS256")
    keyset.activate(second.kid)
    fixed[0] = fixed[0] + timedelta(seconds=200)

    removed = keyset.prune()

    assert removed == [first.kid]
    assert {e.kid for e in keyset.list_keys()} == {second.kid}
    assert not (keyset.keys_dir() / f"{first.kid}.pem").exists()
    assert (keyset.keys_dir() / f"{second.kid}.pem").exists()


def test_prune_force_drops_all_retired(keyset_paths, monkeypatch):
    monkeypatch.setenv("JWT_ROTATION_GRACE_SECONDS", "999999")
    settings.get_settings.cache_clear()

    first = keyset.add_key("RS256")
    second = keyset.add_key("RS256")
    keyset.activate(second.kid)

    removed = keyset.prune(force_all=True)

    assert removed == [first.kid]
    assert {e.kid for e in keyset.list_keys()} == {second.kid}


def test_import_legacy_single_key_migrates_jwt_private_key_path(
    keyset_paths, monkeypatch, tmp_path: Path
):
    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pem_path = tmp_path / "legacy.pem"
    pem_path.write_bytes(pem)
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(pem_path))
    settings.get_settings.cache_clear()

    entry = keyset.import_legacy_single_key()

    assert entry is not None
    assert entry.status == "active"
    assert keyset.active_kid() == entry.kid
    assert (keyset.keys_dir() / f"{entry.kid}.pem").is_file()
    assert keyset.has_manifest()


def test_import_legacy_single_key_is_idempotent(keyset_paths):
    keyset.add_key("RS256")
    assert keyset.import_legacy_single_key() is None


def test_import_legacy_single_key_no_legacy_no_op(keyset_paths):
    assert keyset.import_legacy_single_key() is None


def test_jwt_kid_env_overrides_manifest_active(keyset_paths, monkeypatch):
    first = keyset.add_key("RS256")
    second = keyset.add_key("RS256")
    keyset.activate(second.kid)

    assert keyset.active_kid() == second.kid

    monkeypatch.setenv("JWT_KID", first.kid)
    settings.get_settings.cache_clear()

    assert keyset.active_kid() == first.kid


def test_manifest_atomic_write_no_tmp_left(keyset_paths):
    _, _, manifest = keyset_paths
    keyset.add_key("RS256")
    tmp_path = manifest.with_suffix(manifest.suffix + ".tmp")
    assert manifest.is_file()
    assert not tmp_path.exists()
