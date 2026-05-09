"""Filesystem-loaded edge functions.

Layout: every ``*.py`` under ``settings.functions_dir`` becomes a route at
``/functions/<relative path without .py>``. See :mod:`.loader` for discovery
rules and :mod:`.router` for the dispatcher contract.
"""

from .context import Ctx, FunctionUser, PostgrestClient, StorageClient
from .loader import FunctionRegistry
from .schemas import FunctionMeta

__all__ = [
    "Ctx",
    "FunctionUser",
    "FunctionMeta",
    "FunctionRegistry",
    "PostgrestClient",
    "StorageClient",
]
