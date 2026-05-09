"""Filesystem tests for ``supython secret`` CLI."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from supython import secretset, settings
from supython.cli import app


@pytest.fixture
def chdir(tmp_path: Path):
    prev = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(prev)


@pytest.fixture
def rotation_env(monkeypatch, chdir):
    secrets_dir = chdir / ".supython" / "secrets"
    manifest = chdir / ".supython" / "secrets.json"
    monkeypatch.setenv("SECRETS_DIR", str(secrets_dir))
    monkeypatch.setenv("SECRETS_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("STORAGE_SIGNED_URL_SECRET", "")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "")
    settings.get_settings.cache_clear()
    secretset.clear_cache()
    yield {"secrets_dir": secrets_dir, "manifest": manifest}
    settings.get_settings.cache_clear()
    secretset.clear_cache()


def test_secret_status_shows_manifest_state(rotation_env):
    runner = CliRunner()
    secretset.rotate("storage_signed_url")

    result = runner.invoke(app, ["secret", "status"])

    assert result.exit_code == 0, result.output
    assert "storage_signed_url" in result.output
    assert "active" in result.output


def test_secret_rotate_imports_legacy_then_adds_verifying(monkeypatch, chdir: Path):
    secrets_dir = chdir / ".supython" / "secrets"
    manifest = chdir / ".supython" / "secrets.json"
    monkeypatch.setenv("SECRETS_DIR", str(secrets_dir))
    monkeypatch.setenv("SECRETS_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("STORAGE_SIGNED_URL_SECRET", "a" * 48)
    monkeypatch.setenv("OAUTH_STATE_SECRET", "")
    settings.get_settings.cache_clear()
    secretset.clear_cache()

    runner = CliRunner()
    result = runner.invoke(app, ["secret", "rotate", "storage"])

    assert result.exit_code == 0, result.output
    # After rotate, we should have the legacy imported as active + a new verifying
    kids = [e.kid for e in secretset.list_secrets("storage_signed_url")]
    assert len(kids) == 2
    statuses = {e.kid: e.status for e in secretset.list_secrets("storage_signed_url")}
    active = secretset.active_secret("storage_signed_url").kid
    assert statuses[active] == "active"
    other = next(k for k in kids if k != active)
    assert statuses[other] == "verifying"


def test_secret_activate_flips_active(rotation_env):
    runner = CliRunner()
    first = secretset.rotate("storage_signed_url")
    second = secretset.rotate("storage_signed_url")
    assert secretset.active_secret("storage_signed_url").kid == first.kid

    result = runner.invoke(app, ["secret", "activate", "storage", second.kid])

    assert result.exit_code == 0, result.output
    assert secretset.active_secret("storage_signed_url").kid == second.kid
    statuses = {e.kid: e for e in secretset.list_secrets("storage_signed_url")}
    assert statuses[first.kid].status == "retired"
    assert statuses[first.kid].retired_at is not None
    assert statuses[second.kid].status == "active"


def test_secret_prune_drops_retired(rotation_env, monkeypatch):
    monkeypatch.setenv("SECRET_ROTATION_GRACE_SECONDS", "999999")
    settings.get_settings.cache_clear()

    runner = CliRunner()
    first = secretset.rotate("storage_signed_url")
    second = secretset.rotate("storage_signed_url")
    secretset.activate("storage_signed_url", second.kid)

    result = runner.invoke(app, ["secret", "prune", "storage", "--force"])

    assert result.exit_code == 0, result.output
    assert f"pruned kid={first.kid}" in result.output
    remaining = {e.kid for e in secretset.list_secrets("storage_signed_url")}
    assert remaining == {second.kid}


def test_secret_rotate_unknown_name_exits_nonzero(rotation_env):
    runner = CliRunner()
    result = runner.invoke(app, ["secret", "rotate", "nope"])

    assert result.exit_code != 0
    assert "must be 'storage' or 'oauth'" in (result.output + (result.stderr or ""))
