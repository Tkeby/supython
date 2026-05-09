"""Unit tests for ``supython.settings_module``."""

import sys
from pathlib import Path

import pytest

from supython.settings_module import UserSettings, _resolve, load_user_settings


def test_load_user_settings_minimal() -> None:
    user = load_user_settings("tests.fixtures.settings_modules.minimal")
    assert user.extensions == ["pkg.x"]
    assert user.extra_routers == []
    assert user.extra_middleware == []


def test_load_user_settings_extra_routers() -> None:
    user = load_user_settings("tests.fixtures.settings_modules.with_router")
    assert user.extensions == []
    assert len(user.extra_routers) == 1
    from fastapi import APIRouter

    assert isinstance(user.extra_routers[0], APIRouter)


def test_load_user_settings_bad_spec() -> None:
    with pytest.raises(ValueError, match="expected 'module.path:symbol'"):
        _resolve("not.colon.spec")


def test_load_user_settings_missing_symbol() -> None:
    with pytest.raises(ImportError, match="is not in"):
        _resolve("tests.fixtures.routers:nope")


def test_load_user_settings_missing_module() -> None:
    with pytest.raises(ImportError, match="could not be imported"):
        load_user_settings("nonexistent.module.path")


def test_user_settings_default() -> None:
    u = UserSettings()
    assert u.extensions == []
    assert u.extra_routers == []
    assert u.extra_middleware == []


def test_load_user_settings_imports_from_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror a scaffolded project: package under CWD, not on PYTHONPATH.

    Reproduces the `supython dev` failure where the installed console script
    runs with sys.path[0] = venv/bin and the user's package is not importable.
    """
    pkg = tmp_path / "myproj"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "settings.py").write_text("EXTENSIONS = ['only.this']\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p not in ("", str(tmp_path))])
    monkeypatch.delitem(sys.modules, "myproj", raising=False)
    monkeypatch.delitem(sys.modules, "myproj.settings", raising=False)

    user = load_user_settings("myproj.settings")
    assert user.extensions == ["only.this"]
