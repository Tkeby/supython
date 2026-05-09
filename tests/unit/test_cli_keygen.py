"""Filesystem tests for ``supython keygen``."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from typer.testing import CliRunner

from supython import jwks, keyset, settings
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
    keys_dir = chdir / ".supython" / "keys"
    manifest = chdir / ".supython" / "keyset.json"
    jwks_path = chdir / ".supython" / "jwks.json"
    monkeypatch.setenv("JWT_ALG", "RS256")
    monkeypatch.setenv("JWT_KEYS_DIR", str(keys_dir))
    monkeypatch.setenv("JWT_KEYSET_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("JWT_JWKS_PATH", str(jwks_path))
    monkeypatch.setenv("JWT_KID", "")
    monkeypatch.setenv("JWT_PRIVATE_KEY", "")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")
    settings.get_settings.cache_clear()
    jwks.clear_cache()
    yield {"keys_dir": keys_dir, "manifest": manifest, "jwks": jwks_path}
    settings.get_settings.cache_clear()
    jwks.clear_cache()


@pytest.fixture
def silence_postgrest_reload(monkeypatch):
    """Stub `_postgrest_reload` so tests don't actually shell out to docker."""
    calls: list[bool] = []
    monkeypatch.setattr(
        "supython.cli._postgrest_reload",
        lambda: calls.append(True),
    )
    return calls


@pytest.mark.parametrize(
    ("alg", "kty"),
    [("RS256", "RSA"), ("ES256", "EC")],
)
def test_keygen_writes_pem_and_jwks(chdir: Path, alg: str, kty: str):
    runner = CliRunner()
    result = runner.invoke(app, ["keygen", "--alg", alg])

    assert result.exit_code == 0, result.output
    private_path = chdir / ".supython" / "jwt_private.pem"
    jwks_path = chdir / ".supython" / "jwks.json"
    assert private_path.is_file()
    assert jwks_path.is_file()
    assert private_path.read_text().startswith("-----BEGIN PRIVATE KEY-----")

    doc = json.loads(jwks_path.read_text())
    assert len(doc["keys"]) == 1
    key = doc["keys"][0]
    assert key["alg"] == alg
    assert key["kty"] == kty
    assert key["kid"]
    assert key["use"] == "sig"
    for private_member in {"d", "p", "q", "dp", "dq", "qi", "k"}:
        assert private_member not in key

    assert f"JWT_ALG={alg}" in result.output
    assert "JWT_PRIVATE_KEY_PATH=.supython/jwt_private.pem" in result.output
    assert "JWT_JWKS_PATH=.supython/jwks.json" in result.output


def test_keygen_refuses_overwrite_without_force(chdir: Path):
    runner = CliRunner()
    first = runner.invoke(app, ["keygen"])
    assert first.exit_code == 0, first.output

    second = runner.invoke(app, ["keygen"])
    assert second.exit_code == 1
    output = second.output + (second.stderr or "")
    assert "pass --force to overwrite" in output


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits only")
def test_keygen_private_file_perms(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["keygen"])

    assert result.exit_code == 0, result.output
    mode = ((chdir / ".supython" / "jwt_private.pem").stat().st_mode) & 0o777
    assert mode == 0o600


def test_keygen_init_alias_still_works(chdir: Path):
    """`supython keygen init --alg RS256` retains the legacy single-key behavior."""
    runner = CliRunner()
    result = runner.invoke(app, ["keygen", "init", "--alg", "RS256"])

    assert result.exit_code == 0, result.output
    assert (chdir / ".supython" / "jwt_private.pem").is_file()
    assert (chdir / ".supython" / "jwks.json").is_file()
    assert "JWT_PRIVATE_KEY_PATH=.supython/jwt_private.pem" in result.output


def test_keygen_rotate_adds_kid_without_flipping_active(
    rotation_env, silence_postgrest_reload
):
    runner = CliRunner()
    keyset.add_key("RS256")
    first = keyset.active_kid()
    assert first is not None

    result = runner.invoke(app, ["keygen", "rotate", "--alg", "RS256"])

    assert result.exit_code == 0, result.output
    assert keyset.active_kid() == first, "rotate must NOT flip the active kid"
    new_kids = [e.kid for e in keyset.list_keys() if e.kid != first]
    assert len(new_kids) == 1
    statuses = {e.kid: e.status for e in keyset.list_keys()}
    assert statuses[new_kids[0]] == "verifying"
    assert statuses[first] == "active"


def test_keygen_rotate_migrates_legacy_single_key_on_first_run(
    monkeypatch, chdir: Path, silence_postgrest_reload
):
    legacy_pem = chdir / "legacy.pem"
    pem_bytes = rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    ).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    legacy_pem.write_bytes(pem_bytes)

    keys_dir = chdir / ".supython" / "keys"
    manifest = chdir / ".supython" / "keyset.json"
    jwks_path = chdir / ".supython" / "jwks.json"
    monkeypatch.setenv("JWT_ALG", "RS256")
    monkeypatch.setenv("JWT_KEYS_DIR", str(keys_dir))
    monkeypatch.setenv("JWT_KEYSET_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("JWT_JWKS_PATH", str(jwks_path))
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(legacy_pem))
    monkeypatch.setenv("JWT_KID", "")
    monkeypatch.setenv("JWT_PRIVATE_KEY", "")
    settings.get_settings.cache_clear()
    jwks.clear_cache()

    runner = CliRunner()
    result = runner.invoke(app, ["keygen", "rotate"])

    assert result.exit_code == 0, result.output
    assert "imported legacy single key" in result.output

    kids = [e.kid for e in keyset.list_keys()]
    assert len(kids) == 2
    statuses = {e.kid: e.status for e in keyset.list_keys()}
    active = keyset.active_kid()
    assert statuses[active] == "active"
    other = next(k for k in kids if k != active)
    assert statuses[other] == "verifying"


def test_keygen_activate_flips_signing_kid(rotation_env, silence_postgrest_reload):
    runner = CliRunner()
    first = keyset.add_key("RS256")
    second = keyset.add_key("RS256")
    assert keyset.active_kid() == first.kid

    result = runner.invoke(app, ["keygen", "activate", second.kid])

    assert result.exit_code == 0, result.output
    assert keyset.active_kid() == second.kid
    statuses = {e.kid: e for e in keyset.list_keys()}
    assert statuses[first.kid].status == "retired"
    assert statuses[first.kid].retired_at is not None
    assert statuses[second.kid].status == "active"


def test_keygen_activate_unknown_kid_exits_nonzero(
    rotation_env, silence_postgrest_reload
):
    runner = CliRunner()
    keyset.add_key("RS256")

    result = runner.invoke(app, ["keygen", "activate", "no-such-kid"])

    assert result.exit_code != 0
    assert "kid not in keyset" in (result.output + (result.stderr or ""))


def test_keygen_prune_skips_kids_inside_grace_window(
    rotation_env, silence_postgrest_reload, monkeypatch
):
    monkeypatch.setenv("JWT_ROTATION_GRACE_SECONDS", "3600")
    settings.get_settings.cache_clear()

    fixed = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("supython.keyset._now", lambda: fixed[0])

    first = keyset.add_key("RS256")
    second = keyset.add_key("RS256")
    keyset.activate(second.kid)
    fixed[0] = fixed[0] + timedelta(seconds=60)

    runner = CliRunner()
    result = runner.invoke(app, ["keygen", "prune"])

    assert result.exit_code == 0, result.output
    assert "nothing pruned" in result.output
    assert {e.kid for e in keyset.list_keys()} == {first.kid, second.kid}


def test_keygen_prune_force_drops_all_retired(
    rotation_env, silence_postgrest_reload
):
    runner = CliRunner()
    first = keyset.add_key("RS256")
    second = keyset.add_key("RS256")
    keyset.activate(second.kid)

    result = runner.invoke(app, ["keygen", "prune", "--force"])

    assert result.exit_code == 0, result.output
    assert f"pruned kid={first.kid}" in result.output
    remaining = {e.kid for e in keyset.list_keys()}
    assert remaining == {second.kid}


def test_keygen_no_reload_skips_docker_call(rotation_env, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return _Result()

    monkeypatch.setattr("supython.cli.subprocess.run", fake_run)

    runner = CliRunner()
    result = runner.invoke(app, ["keygen", "rotate", "--no-reload"])

    assert result.exit_code == 0, result.output
    assert calls == [], f"--no-reload should not invoke subprocess.run, got {calls!r}"


def test_keygen_reload_invokes_docker(rotation_env, monkeypatch):
    """Inverse of --no-reload: by default, the rotate path shells out to docker."""
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return _Result()

    monkeypatch.setattr("supython.cli.subprocess.run", fake_run)

    runner = CliRunner()
    result = runner.invoke(app, ["keygen", "rotate"])

    assert result.exit_code == 0, result.output
    assert any(
        "SIGUSR2" in part and "postgrest" in cmd
        for cmd in calls
        for part in cmd
    ), f"expected SIGUSR2 postgrest call, got {calls!r}"

