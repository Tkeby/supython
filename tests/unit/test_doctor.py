"""Unit tests for symmetric secret ``supython doctor`` checks."""

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from supython import secretset, settings
from supython.cli import app


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("JWT_ALG", raising=False)
    monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("JWT_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.delenv("JWT_KID", raising=False)
    monkeypatch.delenv("JWT_JWKS_PATH", raising=False)
    monkeypatch.setenv("JWT_KEYSET_MANIFEST_PATH", str(tmp_path / "keyset.json"))
    monkeypatch.setenv("JWT_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setenv("SECRETS_MANIFEST_PATH", str(tmp_path / "secrets.json"))
    monkeypatch.setenv("STORAGE_SIGNED_URL_SECRET", "")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "")
    settings.get_settings.cache_clear()
    secretset.clear_cache()
    yield
    settings.get_settings.cache_clear()
    secretset.clear_cache()


@pytest.fixture
def chdir(tmp_path: Path):
    prev = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(prev)


@pytest.fixture(autouse=True)
def stub_database_and_jwt(monkeypatch):
    from supython import cli

    monkeypatch.setattr(
        cli,
        "_check_database",
        lambda _database_url: cli._DoctorReport(
            ok=["Postgres check skipped in doctor unit test"]
        ),
    )
    monkeypatch.setattr(
        cli,
        "_check_jwt",
        lambda _settings: cli._DoctorReport(
            ok=["JWT check skipped in doctor unit test"]
        ),
    )
    monkeypatch.setattr(
        cli,
        "_check_postgrest",
        lambda _settings: cli._DoctorReport(),
    )


def test_doctor_reports_missing_symmetric_secret_manifest_and_env(monkeypatch, chdir: Path):
    monkeypatch.setenv("STORAGE_SIGNED_URL_SECRET", "")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "")
    settings.get_settings.cache_clear()

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    output = result.output + (result.stderr or "")
    assert "storage_signed_url: no manifest and no valid legacy env var" in output
    assert "oauth_state: no manifest and no valid legacy env var" in output


def test_doctor_reports_missing_active_symmetric_secret(monkeypatch, chdir: Path):
    secretset.rotate("storage_signed_url")
    # clear active manually
    manifest = secretset.load_manifest()
    manifest["storage_signed_url"]["active"] = None
    secretset.write_manifest(manifest)
    secretset.clear_cache()

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    output = result.output + (result.stderr or "")
    assert "storage_signed_url: manifest exists but has no active kid" in output


def test_doctor_reports_missing_secret_file(monkeypatch, chdir: Path):
    secretset.rotate("storage_signed_url")
    entry = secretset.active_secret("storage_signed_url")
    entry.secret_path.unlink()
    secretset.clear_cache()

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    output = result.output + (result.stderr or "")
    assert "storage_signed_url: active secret file missing" in output


def test_doctor_warns_when_secret_grace_is_shorter_than_storage_default_ttl(
    monkeypatch, chdir: Path
):
    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "100")
    monkeypatch.setenv("STORAGE_SIGNED_URL_DEFAULT_TTL", "3600")
    settings.get_settings.cache_clear()
    secretset.rotate("storage_signed_url")
    secretset.rotate("oauth_state")
    secretset.clear_cache()

    result = CliRunner().invoke(app, ["doctor"])

    output = result.output + (result.stderr or "")
    assert "warn: SECRET_ROTATION_GRACE_SECONDS" in output
    assert "shorter than STORAGE_SIGNED_URL_DEFAULT_TTL" in output
