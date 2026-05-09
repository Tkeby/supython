"""Shared types for the functions subsystem.

Kept dependency-free so the loader and the dispatcher can both import from
here without cycling through ``context.py`` (which pulls in storage/mailer).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:  # pragma: no cover - only for type checking
    from fastapi import Request

    from .context import Ctx


HandlerFn = Callable[["Request", "Ctx"], Awaitable[Any]]

AuthMode = Literal["authenticated", "anon"]

ALLOWED_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


@dataclass
class FunctionMeta:
    """Everything the dispatcher needs to invoke one user function."""

    name: str  # route name, e.g. "payments/webhook"
    path: Path  # absolute file path on disk
    module_name: str  # synthetic dotted name under supython._functions
    methods: list[str] = field(default_factory=lambda: ["POST"])
    auth: AuthMode = "authenticated"
    mtime: float = 0.0
    handler: HandlerFn | None = None


# ---------------------------------------------------------------------------
# Error codes used by the dispatcher (kept here so tests can import them).
# ---------------------------------------------------------------------------

ERR_NOT_FOUND = "function_not_found"
ERR_METHOD_NOT_ALLOWED = "method_not_allowed"
ERR_BODY_TOO_LARGE = "body_too_large"
ERR_INVALID_TOKEN = "invalid_token"
ERR_INVALID_RETURN = "invalid_function_return"
ERR_FUNCTION_ERROR = "function_error"
ERR_FUNCTION_TIMEOUT = "function_timeout"
