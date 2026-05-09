"""Reject oversized request bodies before they reach the app.

The cap is the first line of defense for routes that accept JSON/form
payloads — auth, jobs control plane, realtime control, etc. Anything that
genuinely streams (storage uploads, functions) is exempted via path
prefix and governed by its own per-feature setting.

The motivation is concrete: argon2 hashes the entire submitted password,
so a multi-megabyte password DoS-es a worker. Bound the body, the worry
goes away.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .settings import Settings, get_settings

logger = logging.getLogger(__name__)

ERR_BODY_TOO_LARGE = "body_too_large"

# Methods that may carry a body. We don't gate GET/HEAD/OPTIONS — even if
# a curious client attaches one, FastAPI ignores it for those methods.
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class _BodyTooLargeError(Exception):
    """Raised by the wrapped ASGI receive() once the cap is exceeded.

    Propagates out of FastAPI's body-parsing code (``request.body()`` /
    ``request.json()``) and is caught by ``BodySizeLimitMiddleware``,
    which converts it into a 413 response. Custom class so we don't
    accidentally swallow legitimate exceptions from the inner app.
    """


def _path_matches(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == p or path.startswith(p + "/") for p in prefixes)


class BodySizeLimitMiddleware:
    """ASGI middleware that enforces ``security_max_body_bytes``.

    Two-layer defense:

    1. *Cheap path*: reject up-front when ``Content-Length`` declares a
       body larger than the cap. The inner app is never invoked.
    2. *Streaming path*: forward chunks to the inner app as they arrive
       while counting bytes. As soon as the cap is exceeded, the wrapped
       receive() raises :class:`_BodyTooLargeError`, which propagates out
       of the route handler and is caught here. The middleware then sends
       a 413 — provided the inner app hasn't already started a response.

    Streaming (rather than buffering) keeps memory bounded and lets
    routes that *do* legitimately stream (storage, functions, exempt by
    path prefix) operate without a copy.
    """

    def __init__(self, app: Any, settings: Settings | None = None) -> None:
        self.app = app
        self._settings = settings or get_settings()
        self._max_bytes = self._settings.security_max_body_bytes
        self._exempt = tuple(
            p.strip()
            for p in self._settings.security_body_limit_exempt_paths.split(",")
            if p.strip()
        )

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http" or self._max_bytes <= 0:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "").upper()
        if method not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return

        if _path_matches(scope.get("path", ""), self._exempt):
            await self.app(scope, receive, send)
            return

        if not await self._content_length_ok(scope, send):
            return

        await self._enforce_streaming(scope, receive, send)

    async def _content_length_ok(
        self,
        scope: dict[str, Any],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> bool:
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    await self._send_413(send, "Malformed Content-Length")
                    return False
                if declared > self._max_bytes:
                    await self._send_413(send)
                    return False
                break
        return True

    async def _enforce_streaming(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        received = 0
        response_started = False

        async def _bounded_receive() -> dict[str, Any]:
            nonlocal received
            msg = await receive()
            if msg.get("type") == "http.request":
                received += len(msg.get("body", b""))
                if received > self._max_bytes:
                    raise _BodyTooLargeError()
            return msg

        async def _send_wrapper(msg: dict[str, Any]) -> None:
            nonlocal response_started
            if msg["type"] == "http.response.start":
                response_started = True
            await send(msg)

        try:
            await self.app(scope, _bounded_receive, _send_wrapper)
        except _BodyTooLargeError:
            if not response_started:
                await self._send_413(send)
            else:
                # The app already committed to a response before we
                # noticed the overflow. We can't change the status — the
                # bytes have left the building — but we should make this
                # visible: the request was incomplete from our side.
                logger.warning(
                    "body-size: cap exceeded after response started "
                    "(path=%s); response delivered but body was truncated",
                    scope.get("path", ""),
                )

    async def _send_413(
        self,
        send: Callable[[dict[str, Any]], Awaitable[None]],
        message: str | None = None,
    ) -> None:
        msg = message or (
            f"Request body exceeds maximum size of {self._max_bytes} bytes"
        )
        body = (
            b'{"detail":{"code":"'
            + ERR_BODY_TOO_LARGE.encode("ascii")
            + b'","message":"'
            + msg.encode("utf-8").replace(b'"', b'\\"')
            + b'"}}'
        )
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"connection", b"close"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
                "more_body": False,
            }
        )
