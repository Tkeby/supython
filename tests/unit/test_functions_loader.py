"""Tests for the functions filesystem loader (FunctionRegistry).

Pure unit tests — no database, no HTTP client.  They operate on a
temporary copy of ``tests/fixtures/functions/`` so writes do not mutate
the fixture tree.
"""

import logging
import os
import shutil
from pathlib import Path

import pytest

from supython.functions.loader import FunctionLoadError, FunctionRegistry

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "functions"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fn_root(tmp_path) -> Path:
    """A writable copy of the fixture functions directory."""
    root = tmp_path / "functions"
    shutil.copytree(FIXTURES, root)
    return root


@pytest.fixture
def reg(fn_root) -> FunctionRegistry:
    """Hot-reload registry pre-loaded from fn_root."""
    r = FunctionRegistry(fn_root, hot_reload=True)
    r.discover()
    return r


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discover_finds_expected_functions(reg):
    names = {m.name for m in reg.list()}
    assert "hello" in names
    assert "me" in names
    assert "nested/inner" in names


def test_discover_ignores_underscore_prefixed_files(reg):
    names = {m.name for m in reg.list()}
    assert "_hidden" not in names


def test_discover_skips_bad_handler_in_hot_reload_mode(fn_root, caplog):
    """bad_handler.py (no async handler) must be skipped, never raised."""
    with caplog.at_level(logging.WARNING):
        r = FunctionRegistry(fn_root, hot_reload=True)
        r.discover()
    assert "bad_handler" not in {m.name for m in r.list()}
    # The warning should mention the problematic file
    assert any("bad_handler" in rec.message for rec in caplog.records)


def test_bad_handler_raises_at_startup_when_hot_reload_false(fn_root):
    """In production mode (hot_reload=False) an invalid module is fatal."""
    r = FunctionRegistry(fn_root, hot_reload=False)
    with pytest.raises(FunctionLoadError):
        r.discover()


def test_nonexistent_root_is_silently_skipped(tmp_path):
    r = FunctionRegistry(tmp_path / "does_not_exist", hot_reload=True)
    r.discover()
    assert r.list() == []


# ---------------------------------------------------------------------------
# Module attributes
# ---------------------------------------------------------------------------


def test_methods_attribute_honored(reg):
    hello = reg.get("hello")
    assert hello is not None
    assert set(hello.methods) == {"GET", "POST"}


def test_auth_anon_honored(reg):
    hello = reg.get("hello")
    assert hello is not None
    assert hello.auth == "anon"


def test_auth_authenticated_is_default(reg):
    me = reg.get("me")
    assert me is not None
    assert me.auth == "authenticated"


def test_default_method_is_post(reg):
    me = reg.get("me")
    assert me is not None
    assert me.methods == ["POST"]


def test_nested_route_resolved_correctly(reg):
    inner = reg.get("nested/inner")
    assert inner is not None
    assert inner.name == "nested/inner"
    assert set(inner.methods) == {"GET", "POST"}


# ---------------------------------------------------------------------------
# Hot reload — mtime change triggers module reload
# ---------------------------------------------------------------------------


async def test_hot_reload_detects_mtime_change(tmp_path):
    """Bumping mtime causes the registry to reload the module on next get()."""
    root = tmp_path / "fn"
    root.mkdir()
    fn = root / "greet.py"
    fn.write_text(
        'auth = "anon"\nmethods = ["GET"]\n\nasync def handler(req, ctx):\n    return {"v": 1}\n'
    )

    r = FunctionRegistry(root, hot_reload=True)
    r.discover()

    meta1 = r.get("greet")
    assert meta1 is not None
    assert await meta1.handler(None, None) == {"v": 1}

    fn.write_text(
        'auth = "anon"\nmethods = ["GET"]\n\nasync def handler(req, ctx):\n    return {"v": 2}\n'
    )
    # Nudge mtime forward so stat() sees a change even on fast filesystems.
    new_mtime = fn.stat().st_mtime + 1
    os.utime(fn, (new_mtime, new_mtime))

    meta2 = r.get("greet")
    assert meta2 is not None
    assert await meta2.handler(None, None) == {"v": 2}


async def test_hot_reload_file_deleted_returns_none(tmp_path):
    """If the file disappears between calls, get() returns None."""
    root = tmp_path / "fn"
    root.mkdir()
    fn = root / "ephemeral.py"
    fn.write_text(
        'auth = "anon"\nmethods = ["GET"]\n\nasync def handler(req, ctx):\n    return {}\n'
    )

    r = FunctionRegistry(root, hot_reload=True)
    r.discover()
    assert r.get("ephemeral") is not None

    fn.unlink()
    assert r.get("ephemeral") is None


# ---------------------------------------------------------------------------
# Hot reload — new file discovery via debounce rescan
# ---------------------------------------------------------------------------


async def test_new_file_picked_up_after_debounce_reset(tmp_path):
    """A file dropped after initial discover appears once debounce clears."""
    root = tmp_path / "fn"
    root.mkdir()
    _ANON_HANDLER = (
        'auth = "anon"\nmethods = ["GET"]\n\n'
        "async def handler(req, ctx):\n    return {}"
        '\n'
    )
    existing = root / "existing.py"
    existing.write_text(_ANON_HANDLER)

    r = FunctionRegistry(root, hot_reload=True)
    r.discover()
    assert r.get("existing") is not None
    assert r.get("newfile") is None

    (root / "newfile.py").write_text(_ANON_HANDLER)
    # Reset debounce so the next get() triggers a full rescan.
    r._last_rescan = 0.0
    assert r.get("newfile") is not None
