"""Unit tests for ``supython.extensions.load_extensions`` — pure Python, no DB.

Covers package autodiscovery: a package listed in ``EXTENSIONS`` must import all
its non-underscore submodules so that ``@job`` / ``@cron`` / ``@on`` decorators
spread across several files all register.
"""

import sys
import textwrap
from pathlib import Path

import pytest

from supython.extensions import load_extensions

_PKG = "demopkg"


def _write(root: Path, rel: str, body: str = "") -> None:
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(textwrap.dedent(body))


def _purge() -> None:
    for mod in [m for m in sys.modules if m == _PKG or m.startswith(_PKG + ".")]:
        del sys.modules[mod]


@pytest.fixture
def importable(tmp_path: Path, monkeypatch):
    """Make *tmp_path* importable and guarantee a clean import state."""
    monkeypatch.syspath_prepend(str(tmp_path))
    _purge()
    try:
        yield tmp_path
    finally:
        _purge()


def test_package_extension_imports_all_non_underscore_submodules(importable: Path):
    _write(importable, f"{_PKG}/__init__.py")
    _write(importable, f"{_PKG}/jobs/__init__.py", "loaded = []")
    _write(importable, f"{_PKG}/jobs/a.py", f"import {_PKG}.jobs as j; j.loaded.append('a')")
    _write(importable, f"{_PKG}/jobs/b.py", f"import {_PKG}.jobs as j; j.loaded.append('b')")
    _write(
        importable,
        f"{_PKG}/jobs/_private.py",
        f"import {_PKG}.jobs as j; j.loaded.append('_private')",
    )

    load_extensions([f"{_PKG}.jobs"])

    jobs = sys.modules[f"{_PKG}.jobs"]
    assert sorted(jobs.loaded) == ["a", "b"]
    assert "_private" not in jobs.loaded


def test_plain_module_extension_still_imports(importable: Path):
    _write(importable, f"{_PKG}/__init__.py")
    _write(importable, f"{_PKG}/single.py", "marker = 'ok'")

    load_extensions([f"{_PKG}.single"])

    assert sys.modules[f"{_PKG}.single"].marker == "ok"


def test_empty_package_is_a_noop(importable: Path):
    _write(importable, f"{_PKG}/__init__.py")
    _write(importable, f"{_PKG}/jobs/__init__.py")

    load_extensions([f"{_PKG}.jobs"])  # must not raise

    assert f"{_PKG}.jobs" in sys.modules


def test_missing_extension_raises_clear_error(importable: Path):
    with pytest.raises(ImportError, match="could not be imported"):
        load_extensions([f"{_PKG}.does_not_exist"])


def test_empty_entries_are_skipped(importable: Path):
    load_extensions([""])  # must not raise
