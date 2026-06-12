"""Smoke tests for ``supython init`` (project scaffold).

Pure filesystem tests; no database, no HTTP.
"""

import json
import os
import stat
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from typer.testing import CliRunner

from supython.cli import app
from supython.scaffold.init_project import _TEMPLATES_DIR  # type: ignore[attr-defined]
from supython.settings import Settings


@pytest.fixture
def chdir(tmp_path: Path):
    """Run each test inside its own ``tmp_path`` so ``Path.cwd()`` is hermetic."""
    prev = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(prev)


_EXPECTED_FILES = (
    "docker-compose.yml",
    ".env.example",
    ".gitignore",
    "README.md",
    "functions/README.md",
    "migrations/.gitkeep",
    "demo/settings.py",
    "demo/asgi.py",
    "manage.py",
    "demo/__init__.py",
    "demo/jobs/__init__.py",
    "demo/jobs/example.py",
    "demo/hooks/__init__.py",
    "demo/hooks/welcome.py",
)


def test_init_writes_expected_layout(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "demo"])

    assert result.exit_code == 0, result.output
    project = chdir / "demo"
    for rel in _EXPECTED_FILES:
        assert (project / rel).is_file(), f"missing {rel}\n--- output ---\n{result.output}"


def test_init_writes_keypair_and_jwks(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "demo"])
    assert result.exit_code == 0, result.output

    pem_path = chdir / "demo" / ".supython" / "jwt_private.pem"
    jwks_path = chdir / "demo" / ".supython" / "jwks.json"
    assert pem_path.is_file()
    assert jwks_path.is_file()

    key = serialization.load_pem_private_key(pem_path.read_bytes(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    assert key.key_size >= 2048

    doc = json.loads(jwks_path.read_text())
    assert len(doc["keys"]) == 1
    jwk = doc["keys"][0]
    assert jwk["kty"] == "RSA"
    assert jwk["alg"] == "RS256"
    assert jwk["use"] == "sig"
    assert "d" not in jwk and "p" not in jwk

    if os.name == "posix":
        mode = stat.S_IMODE(pem_path.stat().st_mode)
        assert mode == 0o600, oct(mode)


def test_init_env_does_not_contain_jwt_secret(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "demo"])
    assert result.exit_code == 0, result.output

    env = (chdir / "demo" / ".env.example").read_text()
    assert "JWT_SECRET" not in env, env
    assert "JWT_ALG=RS256" in env
    assert "JWT_PRIVATE_KEY_PATH=./.supython/jwt_private.pem" in env
    assert "JWT_JWKS_PATH=./.supython/jwks.json" in env


def test_init_gitignore_excludes_private_key(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "demo"])
    assert result.exit_code == 0, result.output

    ignore = (chdir / "demo" / ".gitignore").read_text().splitlines()
    assert ".supython/jwt_private.pem" in ignore
    assert ".supython/keys/" in ignore
    assert ".supython/keyset.json" in ignore
    assert ".supython/jwks.json" not in ignore
    assert ".supython/" not in ignore
    assert ".supython/secrets/" in ignore
    assert ".supython/secrets.json" in ignore


def test_env_example_contains_project_name_and_fresh_non_jwt_secrets(chdir: Path):
    runner = CliRunner()
    runner.invoke(app, ["init", "demo"])

    env = (chdir / "demo" / ".env.example").read_text()

    assert "demo" in env, env
    assert "OAUTH_STATE_SECRET=" not in env


def test_env_example_pins_backup_container_to_project_name(chdir: Path):
    runner = CliRunner()
    runner.invoke(app, ["init", "demo"])

    env = (chdir / "demo" / ".env.example").read_text()

    assert "BACKUP_DOCKER_CONTAINER=demo-db" in env, env
    assert "STORAGE_SIGNED_URL_SECRET=" not in env
    assert ".supython/secrets.json" in env

    manifest_path = chdir / "demo" / ".supython" / "secrets.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text())

    oauth_secret_path = chdir / "demo" / ".supython" / "secrets" / "oauth_state.v1.secret"
    assert oauth_secret_path.is_file()
    oauth = oauth_secret_path.read_text().strip()
    assert len(oauth) >= 32

    storage_secret_path = chdir / "demo" / ".supython" / "secrets" / "storage_signed_url.v1.secret"
    assert storage_secret_path.is_file()
    storage = storage_secret_path.read_text().strip()
    assert len(storage) >= 32

    assert manifest["oauth_state"]["active"] == "v1"
    assert manifest["storage_signed_url"]["active"] == "v1"


def test_each_init_generates_unique_secrets(chdir: Path):
    runner = CliRunner()
    runner.invoke(app, ["init", "alpha"])
    runner.invoke(app, ["init", "beta"])

    a_manifest = json.loads((chdir / "alpha" / ".supython" / "secrets.json").read_text())
    b_manifest = json.loads((chdir / "beta" / ".supython" / "secrets.json").read_text())

    a_oauth = (
        (chdir / "alpha" / ".supython" / "secrets" / "oauth_state.v1.secret").read_text().strip()
    )
    b_oauth = (
        (chdir / "beta" / ".supython" / "secrets" / "oauth_state.v1.secret").read_text().strip()
    )
    assert a_oauth != b_oauth

    a_storage = (
        (chdir / "alpha" / ".supython" / "secrets" / "storage_signed_url.v1.secret")
        .read_text()
        .strip()
    )
    b_storage = (
        (chdir / "beta" / ".supython" / "secrets" / "storage_signed_url.v1.secret")
        .read_text()
        .strip()
    )
    assert a_storage != b_storage

    a_jwks = json.loads((chdir / "alpha" / ".supython" / "jwks.json").read_text())
    b_jwks = json.loads((chdir / "beta" / ".supython" / "jwks.json").read_text())
    assert a_jwks["keys"][0]["kid"] != b_jwks["keys"][0]["kid"]
    assert a_jwks["keys"][0]["n"] != b_jwks["keys"][0]["n"]


def test_docker_compose_is_valid_yaml(chdir: Path):
    runner = CliRunner()
    runner.invoke(app, ["init", "demo"])

    raw = (chdir / "demo" / "docker-compose.yml").read_text()
    doc = yaml.safe_load(raw)
    assert doc["name"] == "demo"
    assert "db" in doc["services"]
    assert "postgrest" in doc["services"]


def test_init_refuses_non_empty_dir_without_force(chdir: Path):
    runner = CliRunner()
    runner.invoke(app, ["init", "demo"])
    before = sorted((chdir / "demo").rglob("*"))

    result = runner.invoke(app, ["init", "demo"])
    assert result.exit_code != 0
    assert "not empty" in (result.output + (result.stderr or ""))

    after = sorted((chdir / "demo").rglob("*"))
    assert before == after


def test_init_force_overwrites(chdir: Path):
    runner = CliRunner()
    runner.invoke(app, ["init", "demo"])

    target = chdir / "demo" / "README.md"
    target.write_text("local edit")

    result = runner.invoke(app, ["init", "demo", "--force"])
    assert result.exit_code == 0, result.output
    assert target.read_text() != "local edit"


def test_init_dot_uses_current_dir(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "demo", "."])
    assert result.exit_code == 0, result.output

    # The {name} Python package directory is legitimately created by
    # the {name}/-prefixed templates (settings.py, __init__.py, etc.).
    assert (chdir / "demo").is_dir()
    for rel in _EXPECTED_FILES:
        assert (chdir / rel).is_file(), f"missing {rel}"


def test_init_dot_writes_alongside_existing_files(chdir: Path):
    """`init name .` (explicit target) scaffolds into a non-empty dir, Django-style."""
    runner = CliRunner()
    (chdir / "KEEP.md").write_text("keep me")

    result = runner.invoke(app, ["init", "demo", "."])
    assert result.exit_code == 0, result.output

    assert (chdir / "KEEP.md").read_text() == "keep me"
    for rel in _EXPECTED_FILES:
        assert (chdir / rel).is_file(), f"missing {rel}"


def test_init_into_explicit_subdir(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "demo", "srv"])
    assert result.exit_code == 0, result.output

    project = chdir / "srv"
    for rel in _EXPECTED_FILES:
        assert (project / rel).is_file(), f"missing {rel}"


def test_init_requires_name(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code != 0


def test_template_files_present():
    """Sanity: every entry in ``_TEMPLATE_MAP`` resolves to a real template file."""
    for tmpl in (
        "docker-compose.yml.tmpl",
        "env.example.tmpl",
        "gitignore.tmpl",
        "README.md.tmpl",
        "functions_README.md.tmpl",
        "settings.py.tmpl",
        "asgi.py.tmpl",
        "manage.py.tmpl",
        "package_init.py.tmpl",
        "package_jobs_init.py.tmpl",
        "apps_jobs_example.py.tmpl",
        "package_hooks_init.py.tmpl",
        "apps_hooks_welcome.py.tmpl",
    ):
        assert (_TEMPLATES_DIR / tmpl).is_file()


def test_manage_py_is_executable(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "demo"])
    assert result.exit_code == 0, result.output

    manage_py = chdir / "demo" / "manage.py"
    assert manage_py.is_file()
    if os.name == "posix":
        mode = stat.S_IMODE(manage_py.stat().st_mode)
        assert mode & 0o111, f"manage.py not executable: {oct(mode)}"


def test_settings_py_has_extensions(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "demo"])
    assert result.exit_code == 0, result.output

    settings_text = (chdir / "demo" / "demo" / "settings.py").read_text()
    assert "EXTENSIONS = [" in settings_text
    assert '"demo.jobs"' in settings_text
    assert '"demo.hooks"' in settings_text


def test_env_example_contains_settings_module(chdir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "demo"])
    assert result.exit_code == 0, result.output

    env = (chdir / "demo" / ".env.example").read_text()
    assert "SUPYTHON_SETTINGS_MODULE=demo.settings" in env
