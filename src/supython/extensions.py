"""Eager-import dotted module paths so user-side decorators register.

Called from ``create_app()`` before FastAPI() construction, and from the
``supython worker run`` CLI command before ``Worker(settings)`` is
constructed. Intentionally fail-loud — silent failures here mean the
user's ``@job`` / ``@cron`` / ``@on`` decorators never ran, which is far
worse than a clear error at boot.

A dotted path may name a module *or* a package. When it names a package
(e.g. ``myapp.jobs``), every non-underscore submodule inside it is imported
too, so decorators spread across several files register without each file
being listed explicitly. Expansion is one level deep and only applies to the
packages named directly in ``EXTENSIONS`` — nested subpackages are not walked.
"""

import importlib
import logging
import pkgutil
from collections.abc import Sequence
from types import ModuleType

logger = logging.getLogger(__name__)


def load_extensions(modules: Sequence[str]) -> None:
    """Import each module by dotted path, expanding packages one level.

    Empty strings are skipped. Duplicate entries are collapsed via
    ``importlib.import_module``'s own caching (sys.modules), so re-listing
    a module is safe but wasteful — keep the env clean.

    Raises ``ImportError`` with a clear message on the first module (or
    package submodule) that cannot be imported.
    """
    for name in modules:
        if not name:
            continue
        mod = _import(name)
        logger.info("extension loaded: %s", name)
        for submodule in _package_submodules(name, mod):
            _import(submodule)
            logger.info("extension loaded: %s", submodule)


def _import(name: str) -> ModuleType:
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(
            f"extension {name!r} could not be imported. "
            f"Set EXTENSIONS to comma-separated importable module paths."
        ) from exc


def _package_submodules(name: str, mod: ModuleType) -> list[str]:
    """Immediate non-underscore submodule paths of *mod*, if it is a package.

    Returns an empty list for a plain module. Names are sorted for
    deterministic import order.
    """
    pkg_path = getattr(mod, "__path__", None)
    if pkg_path is None:
        return []
    return sorted(
        f"{name}.{info.name}"
        for info in pkgutil.iter_modules(pkg_path)
        if not info.name.startswith("_")
    )
