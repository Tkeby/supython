import contextvars
import json
import logging
import sys
import time
import traceback
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id")


def get_request_id() -> str | None:
    return request_id.get(None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = get_request_id()
        if rid is not None:
            entry["request_id"] = rid
        if record.exc_info and record.exc_info[1] is not None:
            entry["exc_info"] = "".join(traceback.format_exception(*record.exc_info))
        if hasattr(record, "extra_fields"):
            entry.update(record.extra_fields)
        return json.dumps(entry, default=str)


_PLAIN_FORMAT = "%(levelname)s %(name)s %(message)s"


class BoundedLogRingHandler(logging.Handler):
    """In-memory ring buffer of structured log records.

    Each entry is a dict with 'timestamp', 'level', 'logger', 'message',
    and optionally 'request_id' and 'exc_info'.  The buffer is bounded so
    it never grows without limit.

    Access the buffer via the module-level ``log_ring`` tuple:

        from supython.logging_config import log_ring
        entries = log_ring.get()  # list[dict[str, Any]]
    """

    def __init__(self, capacity: int = 5000) -> None:
        super().__init__()
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = get_request_id()
        if rid is not None:
            entry["request_id"] = rid
        if record.exc_info and record.exc_info[1] is not None:
            entry["exc_info"] = "".join(traceback.format_exception(*record.exc_info))
        if hasattr(record, "extra_fields"):
            entry.update(record.extra_fields)  # type: ignore[attr-defined]
        self._buffer.append(entry)

    def get(self) -> list[dict[str, Any]]:
        return list(self._buffer)


# Module-level ring buffer instance — populated by configure_logging() below.
_log_ring_handler: BoundedLogRingHandler | None = None


def get_log_ring() -> list[dict[str, Any]]:
    """Return a snapshot of the in-memory log ring buffer.

    Returns an empty list before ``configure_logging()`` has been called.
    """
    if _log_ring_handler is None:
        return []
    return _log_ring_handler.get()


def configure_logging(level: str = "INFO", *, json_format: bool = True) -> None:
    global _log_ring_handler

    root = logging.getLogger()
    numeric = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric)

    # Stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    if json_format:
        stdout_handler.setFormatter(JsonFormatter())
    else:
        stdout_handler.setFormatter(logging.Formatter(_PLAIN_FORMAT))

    # Ring-buffer handler (always structured, regardless of json_format)
    ring_handler = BoundedLogRingHandler(capacity=5000)
    ring_handler.setLevel(numeric)

    root.handlers = [
        h
        for h in root.handlers
        if not isinstance(h, (logging.StreamHandler, BoundedLogRingHandler))
    ]
    root.addHandler(stdout_handler)
    root.addHandler(ring_handler)
    _log_ring_handler = ring_handler


class RequestIdMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        req_id: str | None = None
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                req_id = value.decode("ascii", errors="replace")
                break
        if not req_id:
            req_id = uuid.uuid4().hex

        token = request_id.set(req_id)
        try:
            await self.app(scope, receive, send)
        finally:
            request_id.reset(token)


_REQUEST_LOG_MAX_BODY_BYTES = 10 * 1024
_AUTH_HEADER = b"authorization"
_REDACTED = "***REDACTED***"

_access_logger = logging.getLogger("supython.access")


class RequestLoggingMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        method = scope.get("method", "")
        path = scope.get("path", "")

        user_agent: str | None = None
        for name, value in scope.get("headers", []):
            if name == b"user-agent":
                user_agent = value.decode("utf-8", errors="replace")
                break

        rid = get_request_id()

        # Capture a bounded prefix of the request body for diagnostic logging
        # WITHOUT altering the byte stream the inner app receives. Each ASGI
        # message is forwarded through untouched while up to
        # _REQUEST_LOG_MAX_BODY_BYTES is copied aside for the log record.
        #
        # This must never pre-read or rewrite the body. The previous approach
        # eagerly drained the whole request, kept only the first
        # _REQUEST_LOG_MAX_BODY_BYTES, then replayed *that truncated buffer* to
        # the app — silently corrupting every request whose body exceeded the
        # cap (multipart file uploads, large JSON payloads: the trailing bytes,
        # and with them the multipart closing boundary, never reached the
        # handler). Teeing keeps the stream intact, preserves true streaming
        # (storage/functions are never buffered whole), and still forwards
        # http.disconnect so streaming responses can detect client hangups.
        body_chunks: list[bytes] = []
        body_size = 0
        body_truncated = False

        async def _receive() -> dict[str, Any]:
            nonlocal body_size, body_truncated
            msg = await receive()
            if msg["type"] == "http.request":
                chunk = msg.get("body", b"")
                if chunk and body_size < _REQUEST_LOG_MAX_BODY_BYTES:
                    space = _REQUEST_LOG_MAX_BODY_BYTES - body_size
                    if len(chunk) > space:
                        body_chunks.append(chunk[:space])
                        body_size += space
                        body_truncated = True
                    else:
                        body_chunks.append(chunk)
                        body_size += len(chunk)
            return msg

        status_code: int = 0
        response_size: int = 0

        async def _send(message: dict[str, Any]) -> None:
            nonlocal status_code, response_size
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            elif message["type"] == "http.response.body":
                response_size += len(message.get("body", b""))
            await send(message)

        exc_info: tuple[type, BaseException, Any] | None = None
        try:
            await self.app(scope, _receive, _send)
        except Exception:
            exc_info = sys.exc_info()
            raise
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 2)

            redacted_headers: list[list[str]] = []
            for name, value in scope.get("headers", []):
                if name == _AUTH_HEADER:
                    redacted_headers.append([name.decode("ascii", errors="replace"), _REDACTED])
                else:
                    redacted_headers.append(
                        [
                            name.decode("ascii", errors="replace"),
                            value.decode("utf-8", errors="replace"),
                        ]
                    )

            fields: dict[str, Any] = {
                "duration_ms": duration_ms,
                "status": status_code,
                "method": method,
                "path": path,
                "request_id": rid,
                "user_agent": user_agent,
                "response_size": response_size,
                "headers": redacted_headers,
            }

            is_server_error = 500 <= status_code < 600 or exc_info is not None

            if is_server_error:
                # The bounded prefix the app actually consumed (see the tee in
                # _receive above); empty if the handler errored before reading.
                full_body = b"".join(body_chunks)
                fields["request_body"] = full_body.decode("utf-8", errors="replace")
                if body_truncated:
                    fields["body_truncated"] = True
                if exc_info is not None and exc_info[1] is not None:
                    fields["traceback"] = "".join(traceback.format_exception(*exc_info))

            level = logging.ERROR if is_server_error else logging.INFO
            record = logging.LogRecord(
                name="supython.access",
                level=level,
                pathname=__file__,
                lineno=0,
                msg="request completed",
                args=(),
                exc_info=None,
            )
            record.extra_fields = fields  # type: ignore[attr-defined]

            _access_logger.handle(record)
