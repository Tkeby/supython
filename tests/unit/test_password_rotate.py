"""Unit tests for ``supython password rotate``."""

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from supython import settings
from supython.cli import app


@pytest.fixture
def chdir(tmp_path: Path):
    prev = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(prev)


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://supython:supython@localhost:54322/supython")
    settings.get_settings.cache_clear()
    yield
    settings.get_settings.cache_clear()


def test_password_rotate_alters_role(monkeypatch, chdir: Path):
    calls: list[tuple[str, str]] = []

    async def fake_rotate(conn, role, password):
        calls.append((role, password))

    monkeypatch.setattr("supython.cli.rotate_role_password", fake_rotate)
    monkeypatch.setattr("supython.cli.asyncpg.connect", AsyncMock())

    runner = CliRunner()
    result = runner.invoke(
        app, ["password", "rotate", "authenticator", "--password", "newsecret", "--no-confirm"]
    )

    assert result.exit_code == 0, result.output
    assert calls == [("authenticator", "newsecret")]


def test_password_rotate_updates_dotenv_for_authenticator(monkeypatch, chdir: Path):
    env_path = chdir / ".env"
    env_path.write_text("AUTHENTICATOR_PASSWORD=old\nDATABASE_URL=postgresql://u:p@h/d\n")

    async def fake_rotate(conn, role, password):
        pass

    monkeypatch.setattr("supython.cli.rotate_role_password", fake_rotate)
    monkeypatch.setattr("supython.cli.asyncpg.connect", AsyncMock())

    runner = CliRunner()
    result = runner.invoke(
        app, ["password", "rotate", "authenticator", "--password", "newsecret", "--no-confirm"]
    )

    assert result.exit_code == 0, result.output
    updated = env_path.read_text()
    assert "AUTHENTICATOR_PASSWORD=newsecret" in updated


def test_password_rotate_generates_strong_password_by_default(monkeypatch, chdir: Path):
    async def fake_rotate(conn, role, password):
        pass

    monkeypatch.setattr("supython.cli.rotate_role_password", fake_rotate)
    monkeypatch.setattr("supython.cli.asyncpg.connect", AsyncMock())

    runner = CliRunner()
    result = runner.invoke(app, ["password", "rotate", "authenticator", "--no-confirm"])

    assert result.exit_code == 0, result.output
    # The generated password should be printed
    lines = [l for l in result.output.splitlines() if l and not l.startswith(("rotated", "warn", "reminder"))]
    assert any(len(l) >= 32 for l in lines)


def test_password_rotate_accepts_explicit_password(monkeypatch, chdir: Path):
    async def fake_rotate(conn, role, password):
        pass

    monkeypatch.setattr("supython.cli.rotate_role_password", fake_rotate)
    monkeypatch.setattr("supython.cli.asyncpg.connect", AsyncMock())

    runner = CliRunner()
    result = runner.invoke(
        app, ["password", "rotate", "authenticator", "--password", "my-custom-pw", "--no-confirm"]
    )

    assert result.exit_code == 0, result.output
    assert "my-custom-pw" in result.output


def test_password_rotate_requires_confirmation(monkeypatch, chdir: Path):
    async def fake_rotate(conn, role, password):
        pass

    monkeypatch.setattr("supython.cli.rotate_role_password", fake_rotate)
    monkeypatch.setattr("supython.cli.asyncpg.connect", AsyncMock())

    runner = CliRunner()
    result = runner.invoke(app, ["password", "rotate", "authenticator"])

    assert result.exit_code != 0
    # typer.confirm aborts when not confirmed in non-interactive mode
    assert "Aborted" in result.output or result.exit_code == 1
