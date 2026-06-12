"""Tests for ``settings.export_env_file`` — exports ``.env`` into ``os.environ``.

pydantic-settings only fills the typed ``Settings`` model from ``.env``; it never
populates ``os.environ``. So dynamically-named secrets read via
``os.environ.get(<name>)`` (the ``secret_ref`` convention) are invisible under
``supython dev`` / ``worker run`` / CLI subcommands unless we export the file
ourselves. Pure Python, no DB.
"""

import os
from pathlib import Path

import pytest

from supython.settings import export_env_file

# Distinct prefix so the cleanup fixture can scrub anything load_dotenv writes
# straight into os.environ (which monkeypatch does not track).
PREFIX = "SUPYTHON_DOTENV_TEST_"
KEY = f"{PREFIX}SECRET"


@pytest.fixture(autouse=True)
def _scrub_test_env() -> None:
    yield
    for key in [k for k in os.environ if k.startswith(PREFIX)]:
        del os.environ[key]


def test_exports_values_into_environ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text(f"{KEY}=value123\n")
    monkeypatch.chdir(tmp_path)

    assert os.environ.get(KEY) is None
    export_env_file()
    assert os.environ.get(KEY) == "value123"


def test_real_env_wins_over_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``override=False``: an orchestrator's env var must beat the checked-in file."""
    (tmp_path / ".env").write_text(f"{KEY}=from-file\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(KEY, "from-real-env")

    export_env_file()
    assert os.environ[KEY] == "from-real-env"


def test_missing_file_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    export_env_file()  # must not raise
    assert os.environ.get(KEY) is None


def test_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text(f"{KEY}=once\n")
    monkeypatch.chdir(tmp_path)

    export_env_file()
    export_env_file()
    assert os.environ[KEY] == "once"


def test_create_app_exports_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ASGI / ``supython dev`` boot path runs the export before anything else."""
    import supython.app as app_module

    called = False

    def _spy() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(app_module, "export_env_file", _spy)
    app_module.create_app()
    assert called


def test_bootstrap_user_modules_exports_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI-subcommand boot path (cron list/sync, …) runs the export too."""
    import supython.cli as cli_module

    called = False

    def _spy() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(cli_module, "export_env_file", _spy)
    cli_module._bootstrap_user_modules()
    assert called
