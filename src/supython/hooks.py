"""Generic hook system for supython lifecycle events.

Provides ``on(event, fn)`` to register a handler and ``fire(event, *args)``
to invoke all registered handlers for that event in registration order.

The ``fn=None`` default on ``on()`` makes both ``@app.on_signup`` (bare)
and ``@app.on_signup()`` (called) work correctly.

``HookCtx`` / ``build_hook_ctx`` live here rather than in ``jobs/context.py``
so feature modules (auth, storage, realtime, jobs, ...) share one hook
contract. Keeping the type in ``hooks`` also breaks the ``auth → jobs``
import edge that would otherwise couple auth to the jobs package.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

    from .mailer import EmailBackend
    from .settings import Settings

logger = logging.getLogger(__name__)

_handlers: dict[str, list[Callable[..., Coroutine[Any, Any, None]]]] = defaultdict(list)


def on(
    event: str,
    fn: Callable[..., Coroutine[Any, Any, None]] | None = None,
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Register an async handler for *event*.

    Usage::

        @hooks.on("signup")
        async def on_signup(user, ctx):
            ...

    Or imperatively::

        hooks.on("signup", my_handler)
    """

    def _register(
        f: Callable[..., Coroutine[Any, Any, None]],
    ) -> Callable[..., Coroutine[Any, Any, None]]:
        _handlers[event].append(f)
        return f

    if fn is not None:
        return _register(fn)
    return _register


async def fire(event: str, *args: Any, **kwargs: Any) -> None:
    """Invoke all registered handlers for *event* in order.

    Exceptions are logged but do not prevent subsequent handlers from running.
    """
    for handler in _handlers.get(event, []):
        try:
            await handler(*args, **kwargs)
        except Exception:
            logger.exception("hooks.fire error in %r handler %r", event, handler)


def reset() -> None:
    _handlers.clear()


@dataclass
class HookCtx:
    """Value passed to hook handlers (e.g. ``on_signup``).

    Smaller than ``jobs.JobCtx`` and ``functions.Ctx`` on purpose: a hook
    fires inline on the request/worker path and should only reach for the
    things every lifecycle event is expected to need — the role-scoped DB
    connection, settings, a mailer, and a logger. Anything heavier belongs
    in an enqueued job.
    """

    db: asyncpg.Connection
    settings: Settings
    send_email: Callable[..., Awaitable[None]]
    logger: logging.Logger


def build_hook_ctx(
    *,
    conn: asyncpg.Connection,
    settings: Settings | None = None,
    mailer: EmailBackend | None = None,
) -> HookCtx:
    """Assemble a ``HookCtx`` from a role-scoped connection.

    The caller is expected to have entered ``db.as_role(...)`` already so
    that ``conn`` carries the intended RLS posture; this factory does not
    switch roles.
    """
    from .functions.context import _make_send_email
    from .mailer import get_mailer
    from .settings import get_settings

    s = settings or get_settings()
    return HookCtx(
        db=conn,
        settings=s,
        send_email=_make_send_email(mailer or get_mailer()),
        logger=logging.getLogger("supython.hooks"),
    )
