"""Load a user-defined Python settings module (Django-style).

Conventional uppercase attributes read from the module:
    EXTENSIONS:        list[str]  — dotted module paths (additive on top of
                                    the env-driven ``EXTENSIONS`` list)
    EXTRA_ROUTERS:     list[str]  — ``"module.path:router_symbol"`` strings,
                                    resolved to FastAPI ``APIRouter`` instances
    EXTRA_MIDDLEWARE:  list[str]  — ``"module.path:ClassName"`` strings,
                                    resolved to ASGI middleware classes

The settings module is purely additive on top of env-driven Settings. It
never replaces Pydantic-managed values (DATABASE_URL, JWT keys, etc.) —
those continue to come from env / .env and are typed.
"""

import importlib
import logging
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _ensure_cwd_on_sys_path() -> None:
    """Make the current working directory importable.

    When supython is invoked through ``python manage.py``, Python prepends
    the script's directory (the project root) to ``sys.path`` automatically.
    When invoked through the installed ``supython`` console script, ``sys.path[0]``
    is the venv's bin directory instead, so the user's project package is not
    importable. Mirror Django/Flask convention by adding the CWD ourselves.
    """
    cwd = os.getcwd()
    if cwd not in sys.path and "" not in sys.path:
        sys.path.insert(0, cwd)


@dataclass
class UserSettings:
    """Resolved attributes from a user settings module."""

    extensions: list[str] = field(default_factory=list)
    extra_routers: list[Any] = field(default_factory=list)
    extra_middleware: list[type] = field(default_factory=list)


def load_user_settings(module_path: str) -> UserSettings:
    """Import the user's settings module and resolve the conventional names.

    Raises ``ImportError`` if the module itself cannot be imported, or if any
    referenced ``module.path:symbol`` cannot be resolved. Raises ``ValueError``
    if a referenced spec is malformed.
    """
    _ensure_cwd_on_sys_path()
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"settings module {module_path!r} could not be imported. "
            f"Set SUPYTHON_SETTINGS_MODULE to an importable dotted path."
        ) from exc

    extensions = list(_as_str_list(getattr(mod, "EXTENSIONS", []), "EXTENSIONS"))
    extra_routers = [
        _resolve(p) for p in _as_str_list(getattr(mod, "EXTRA_ROUTERS", []), "EXTRA_ROUTERS")
    ]
    extra_middleware = [
        _resolve(p)
        for p in _as_str_list(getattr(mod, "EXTRA_MIDDLEWARE", []), "EXTRA_MIDDLEWARE")
    ]

    logger.info(
        "settings module loaded: %s (extensions=%d routers=%d middleware=%d)",
        module_path,
        len(extensions),
        len(extra_routers),
        len(extra_middleware),
    )
    return UserSettings(
        extensions=extensions,
        extra_routers=extra_routers,
        extra_middleware=extra_middleware,
    )


def _as_str_list(value: object, name: str) -> Sequence[str]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a list of strings, got {type(value).__name__}")
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{name} entries must be strings, got {type(item).__name__}")
    return list(value)


def _resolve(spec: str) -> Any:
    """Resolve ``module.path:symbol`` to the imported object."""
    if ":" not in spec:
        raise ValueError(
            f"expected 'module.path:symbol', got {spec!r}. Use a colon to "
            f"separate the module path from the attribute name."
        )
    mod_path, _, symbol = spec.partition(":")
    try:
        mod = importlib.import_module(mod_path)
    except ImportError as exc:
        raise ImportError(
            f"settings module references {spec!r} but {mod_path!r} could not be imported."
        ) from exc
    try:
        return getattr(mod, symbol)
    except AttributeError as exc:
        raise ImportError(
            f"settings module references {spec!r} but {symbol!r} is not in {mod_path!r}."
        ) from exc
