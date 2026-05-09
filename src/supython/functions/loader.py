"""Discovery + hot-reload of user functions on disk.

Walks ``settings.functions_dir`` and turns every valid ``*.py`` into a
:class:`~.schemas.FunctionMeta` keyed by its route name (the relative path
minus the ``.py`` suffix).

Naming rules per path segment: ``[a-z0-9][a-z0-9_-]*``. Anything starting
with ``_`` (e.g. ``__init__.py``, ``_helpers.py``) and ``__pycache__`` are
ignored — handlers don't need to be importable as a package, only walkable
as files.

Each module imported under a synthetic ``supython._functions.<dotted>``
package via ``importlib.util.spec_from_file_location`` so user code does not
need to be on ``sys.path``. In hot-reload mode every ``get(name)`` ``stat()``s
the file and ``importlib.reload()``s if the mtime moved — no watcher
threads, deterministic in tests.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import re
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import Any

from .schemas import ALLOWED_METHODS, AuthMode, FunctionMeta

logger = logging.getLogger(__name__)


_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SYNTHETIC_PKG = "supython._functions"
# How often a hot-reload `get()` may rescan the tree for *new* files.
_RESCAN_DEBOUNCE_S = 1.0


class FunctionLoadError(Exception):
    """Raised at startup (when hot reload is off) for a malformed module."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_synthetic_pkg() -> None:
    """Make ``supython._functions`` resolvable without it existing on disk."""
    if _SYNTHETIC_PKG in sys.modules:
        return
    spec = importlib.util.spec_from_loader(_SYNTHETIC_PKG, loader=None)
    pkg = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    pkg.__path__ = []  # marks it as a package
    sys.modules[_SYNTHETIC_PKG] = pkg


def _route_name_for(root: Path, file: Path) -> str | None:
    """Return the route name for ``file`` under ``root``, or None if invalid."""
    rel = file.relative_to(root).with_suffix("")
    parts = rel.parts
    if not parts:
        return None
    for seg in parts:
        if seg.startswith("_") or seg == "__pycache__":
            return None
        if not _SEGMENT_RE.match(seg):
            return None
    return "/".join(parts)


def _module_name_for(name: str) -> str:
    safe = name.replace("/", ".").replace("-", "_")
    return f"{_SYNTHETIC_PKG}.{safe}"


def _validate_module(mod: ModuleType, file: Path) -> tuple[list[str], AuthMode]:
    handler = getattr(mod, "handler", None)
    if handler is None or not inspect.iscoroutinefunction(handler):
        raise FunctionLoadError(
            f"{file}: must define `async def handler(req, ctx)`"
        )

    raw_methods: Any = getattr(mod, "methods", None)
    methods: list[str]
    if raw_methods is None:
        methods = ["POST"]
    else:
        if not isinstance(raw_methods, Iterable) or isinstance(raw_methods, (str, bytes)):
            raise FunctionLoadError(
                f"{file}: `methods` must be a list of HTTP verbs"
            )
        upper = [str(m).upper() for m in raw_methods]
        unknown = [m for m in upper if m not in ALLOWED_METHODS]
        if unknown:
            raise FunctionLoadError(
                f"{file}: unsupported method(s) in `methods`: {unknown}"
            )
        if not upper:
            raise FunctionLoadError(f"{file}: `methods` must not be empty")
        methods = upper

    raw_auth: Any = getattr(mod, "auth", "authenticated")
    if raw_auth not in ("authenticated", "anon"):
        raise FunctionLoadError(
            f"{file}: `auth` must be 'authenticated' or 'anon', got {raw_auth!r}"
        )

    return methods, raw_auth  # type: ignore[return-value]


def _import_file(module_name: str, file: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file)
    if spec is None or spec.loader is None:
        raise FunctionLoadError(f"{file}: could not build import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class FunctionRegistry:
    """In-process registry of discovered functions.

    Construct once per app (the ``db.lifespan`` extension calls ``discover``
    after ``init_pool``). In hot-reload mode ``get`` is the per-request entry
    point; otherwise the snapshot taken at ``discover`` time is final.
    """

    def __init__(self, root: Path, *, hot_reload: bool = True) -> None:
        self._root = Path(root)
        self._hot_reload = hot_reload
        self._metas: dict[str, FunctionMeta] = {}
        self._last_rescan: float = 0.0

    # ------------------------------------------------------------------ public

    @property
    def root(self) -> Path:
        return self._root

    @property
    def hot_reload(self) -> bool:
        return self._hot_reload

    def discover(self) -> None:
        """Walk the tree once. Safe to call repeatedly; idempotent."""
        _ensure_synthetic_pkg()
        if not self._root.exists():
            logger.info("functions: directory %s does not exist; skipping", self._root)
            self._metas = {}
            return

        seen: set[str] = set()
        for file in sorted(self._root.rglob("*.py")):
            name = _route_name_for(self._root, file)
            if name is None:
                continue
            seen.add(name)
            self._load_or_skip(name, file)

        # Drop entries whose files vanished between discoveries.
        for stale in set(self._metas) - seen:
            self._drop(stale)
        self._last_rescan = time.monotonic()

    def get(self, name: str) -> FunctionMeta | None:
        """Return meta for ``name``, applying hot-reload if enabled.

        Returns ``None`` if the function is not (or no longer) registered.
        Validation errors during reload demote to None and log; this matches
        dev ergonomics — a broken save shouldn't kill unrelated routes.
        """
        if self._hot_reload:
            self._maybe_rescan_for_new_files()

        meta = self._metas.get(name)
        if meta is None:
            return None

        if not self._hot_reload:
            return meta

        try:
            stat = meta.path.stat()
        except FileNotFoundError:
            self._drop(name)
            return None

        if stat.st_mtime > meta.mtime:
            try:
                self._reload(meta)
            except FunctionLoadError as exc:
                logger.warning("functions: reload failed for %s: %s", name, exc)
                self._drop(name)
                return None
        return self._metas.get(name)

    def list(self) -> list[FunctionMeta]:
        return sorted(self._metas.values(), key=lambda m: m.name)

    # ---------------------------------------------------------------- internal

    def _maybe_rescan_for_new_files(self) -> None:
        now = time.monotonic()
        if now - self._last_rescan < _RESCAN_DEBOUNCE_S:
            return
        self._last_rescan = now
        if not self._root.exists():
            return
        for file in self._root.rglob("*.py"):
            name = _route_name_for(self._root, file)
            if name is None or name in self._metas:
                continue
            self._load_or_skip(name, file)

    def _load_or_skip(self, name: str, file: Path) -> None:
        try:
            self._load(name, file)
        except FunctionLoadError as exc:
            if self._hot_reload:
                logger.warning("functions: skipping %s: %s", name, exc)
                return
            raise

    def _load(self, name: str, file: Path) -> None:
        module_name = _module_name_for(name)
        # Drop any stale module entry so re-import from the file actually runs.
        sys.modules.pop(module_name, None)
        module = _import_file(module_name, file)
        methods, auth = _validate_module(module, file)
        self._metas[name] = FunctionMeta(
            name=name,
            path=file.resolve(),
            module_name=module_name,
            methods=methods,
            auth=auth,
            mtime=file.stat().st_mtime,
            handler=module.handler,
        )

    def _reload(self, meta: FunctionMeta) -> None:
        # importlib.reload() cannot locate modules under the synthetic package
        # via _find_spec; always use the pop-then-reimport pattern instead.
        sys.modules.pop(meta.module_name, None)
        module = _import_file(meta.module_name, meta.path)
        methods, auth = _validate_module(module, meta.path)
        self._metas[meta.name] = FunctionMeta(
            name=meta.name,
            path=meta.path,
            module_name=meta.module_name,
            methods=methods,
            auth=auth,
            mtime=meta.path.stat().st_mtime,
            handler=module.handler,
        )

    def _drop(self, name: str) -> None:
        meta = self._metas.pop(name, None)
        if meta is not None:
            sys.modules.pop(meta.module_name, None)


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------


_registry: FunctionRegistry | None = None


def get_registry() -> FunctionRegistry:
    """Return the process-wide registry (built lazily from settings)."""
    from ..settings import get_settings

    global _registry
    if _registry is None:
        s = get_settings()
        _registry = FunctionRegistry(
            Path(s.functions_dir),
            hot_reload=s.functions_hot_reload,
        )
    return _registry


def set_registry(registry: FunctionRegistry | None) -> None:
    """Override the singleton (tests use this; lifespan calls with a fresh one)."""
    global _registry
    _registry = registry


def reset_registry() -> None:
    set_registry(None)
