"""Eager-import dotted module paths so user-side decorators register.

Called from ``create_app()`` before FastAPI() construction, and from the
``supython worker run`` CLI command before ``Worker(settings)`` is
constructed. Intentionally fail-loud — silent failures here mean the
user's ``@job`` / ``@cron`` / ``@on`` decorators never ran, which is far
worse than a clear error at boot.
"""

import importlib
import logging
from collections.abc import Sequence

logger = logging.getLogger(__name__)


def load_extensions(modules: Sequence[str]) -> None:
    """Import each module by dotted path.

    Empty strings are skipped. Duplicate entries are collapsed via
    ``importlib.import_module``'s own caching (sys.modules), so re-listing
    a module is safe but wasteful — keep the env clean.

    Raises ``ImportError`` with a clear message on first missing module.
    """
    for name in modules:
        if not name:
            continue
        try:
            importlib.import_module(name)
        except ImportError as exc:
            raise ImportError(
                f"extension {name!r} could not be imported. "
                f"Set EXTENSIONS to comma-separated importable module paths."
            ) from exc
        logger.info("extension loaded: %s", name)
