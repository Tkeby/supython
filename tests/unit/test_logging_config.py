import json
import logging

import pytest

from supython.logging_config import (
    JsonFormatter,
    RequestIdMiddleware,
    RequestLoggingMiddleware,
    configure_logging,
    get_request_id,
    request_id,
    _REQUEST_LOG_MAX_BODY_BYTES,
)


def _make_record(msg: str = "hello", **kwargs: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for k, v in kwargs.items():
        setattr(record, k, v)
    return record


def test_json_formatter_outputs_valid_json():
    fmt = JsonFormatter()
    record = _make_record("test message")
    output = fmt.format(record)
    data = json.loads(output)
    assert data["message"] == "test message"
    assert data["level"] == "INFO"
    assert data["logger"] == "test"
    assert "timestamp" in data


def test_json_formatter_includes_request_id():
    token = request_id.set("abc-123")
    try:
        fmt = JsonFormatter()
        record = _make_record("with request id")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["request_id"] == "abc-123"
    finally:
        request_id.reset(token)


def test_json_formatter_omits_request_id_when_unset():
    fmt = JsonFormatter()
    record = _make_record("no request id")
    output = fmt.format(record)
    data = json.loads(output)
    assert "request_id" not in data


def test_json_formatter_includes_exc_info():
    fmt = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        exc_info = sys.exc_info()
    record = _make_record("error", exc_info=exc_info)
    output = fmt.format(record)
    data = json.loads(output)
    assert "exc_info" in data
    assert "ValueError: boom" in data["exc_info"]


def test_get_request_id_returns_none_by_default():
    assert get_request_id() is None


def test_get_request_id_returns_value():
    token = request_id.set("xyz")
    try:
        assert get_request_id() == "xyz"
    finally:
        request_id.reset(token)


def test_configure_logging_sets_root_level():
    root = logging.getLogger()
    configure_logging("WARNING", json_format=False)
    assert root.level == logging.WARNING
    configure_logging("INFO", json_format=True)
    assert root.level == logging.INFO


@pytest.mark.asyncio
async def test_request_id_middleware_sets_context():
    captured_id: str | None = None

    async def inner_app(scope, receive, send):
        nonlocal captured_id
        captured_id = get_request_id()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestIdMiddleware(inner_app)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
    }

    response_started = False

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(msg):
        nonlocal response_started
        if msg["type"] == "http.response.start":
            response_started = True

    await middleware(scope, receive, send)
    assert response_started
    assert captured_id is not None
    assert len(captured_id) == 32


@pytest.mark.asyncio
async def test_request_id_middleware_uses_header():
    captured_id: str | None = None

    async def inner_app(scope, receive, send):
        nonlocal captured_id
        captured_id = get_request_id()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestIdMiddleware(inner_app)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-request-id", b"my-custom-id")],
    }

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(msg):
        pass

    await middleware(scope, receive, send)
    assert captured_id == "my-custom-id"


@pytest.mark.asyncio
async def test_request_id_propagates_to_create_task():
    import asyncio

    task_id: str | None = None

    async def child():
        nonlocal task_id
        task_id = get_request_id()

    token = request_id.set("task-propagation-test")
    try:
        task = asyncio.create_task(child())
        await task
        assert task_id == "task-propagation-test"
    finally:
        request_id.reset(token)


@pytest.mark.asyncio
async def test_request_id_middleware_passes_through_non_http():
    called = False

    async def inner_app(scope, receive, send):
        nonlocal called
        called = True

    middleware = RequestIdMiddleware(inner_app)
    scope = {"type": "lifespan", "headers": []}

    async def receive():
        return {"type": "lifespan.start"}

    async def send(msg):
        pass

    await middleware(scope, receive, send)
    assert called


# ---------------------------------------------------------------------------
# RequestLoggingMiddleware tests
# ---------------------------------------------------------------------------


def _make_http_scope(
    method: str = "GET",
    path: str = "/test",
    headers: list[tuple[bytes, bytes]] | None = None,
    query_string: bytes = b"",
) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query_string,
        "headers": headers or [],
    }


async def _run_asgi(
    middleware_cls,
    inner_app,
    scope,
    body: bytes = b"",
):
    captured: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = captured.append  # type: ignore[attr-defined]
    logger = logging.getLogger("supython.access")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        mw = middleware_cls(inner_app)

        async def _send(msg):
            pass

        async def _receive():
            return {"type": "http.request", "body": body, "more_body": False}

        await mw(scope, _receive, _send)
    finally:
        logger.removeHandler(handler)
    return captured


@pytest.mark.asyncio
async def test_request_logging_emits_info_on_200():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    rid_token = request_id.set("test-rid-123")
    try:
        records = await _run_asgi(
            RequestLoggingMiddleware,
            app,
            _make_http_scope(headers=[(b"user-agent", b"pytest")]),
        )
    finally:
        request_id.reset(rid_token)

    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.INFO
    fields = rec.extra_fields
    assert fields["status"] == 200
    assert fields["method"] == "GET"
    assert fields["path"] == "/test"
    assert fields["request_id"] == "test-rid-123"
    assert fields["user_agent"] == "pytest"
    assert fields["response_size"] == 2
    assert isinstance(fields["duration_ms"], float)
    assert "traceback" not in fields
    assert "request_body" not in fields


@pytest.mark.asyncio
async def test_request_logging_emits_error_on_500():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 500, "headers": []})
        await send({"type": "http.response.body", "body": b"error"})

    records = await _run_asgi(
        RequestLoggingMiddleware,
        app,
        _make_http_scope(),
        body=b'{"input": "bad"}',
    )

    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.ERROR
    fields = rec.extra_fields
    assert fields["status"] == 500
    assert fields["request_body"] == '{"input": "bad"}'
    assert "traceback" not in fields


@pytest.mark.asyncio
async def test_request_logging_captures_traceback_on_exception():
    async def app(scope, receive, send):
        raise RuntimeError("boom")

    records = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[attr-defined]
    logger = logging.getLogger("supython.access")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    async def _send(msg):
        pass

    try:
        mw = RequestLoggingMiddleware(app)

        async def _receive():
            return {
                "type": "http.request",
                "body": b"some-body",
                "more_body": False,
            }

        with pytest.raises(RuntimeError, match="boom"):
            await mw(
                _make_http_scope(),
                _receive,
                _send,
            )
    finally:
        logger.removeHandler(handler)

    assert len(records) == 1
    fields = records[0].extra_fields
    assert "traceback" in fields
    assert "RuntimeError: boom" in fields["traceback"]
    assert fields["request_body"] == "some-body"


@pytest.mark.asyncio
async def test_request_logging_redacts_authorization():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    records = await _run_asgi(
        RequestLoggingMiddleware,
        app,
        _make_http_scope(
            headers=[
                (b"authorization", b"Bearer secret-token"),
                (b"content-type", b"application/json"),
            ]
        ),
    )

    fields = records[0].extra_fields
    auth_header = [h for h in fields["headers"] if h[0] == "authorization"]
    assert len(auth_header) == 1
    assert auth_header[0][1] == "***REDACTED***"
    ct_header = [h for h in fields["headers"] if h[0] == "content-type"]
    assert ct_header[0][1] == "application/json"


@pytest.mark.asyncio
async def test_request_logging_passes_through_websocket():
    called = False

    async def inner_app(scope, receive, send):
        nonlocal called
        called = True

    mw = RequestLoggingMiddleware(inner_app)
    scope = {"type": "websocket", "path": "/ws", "headers": []}
    await mw(scope, lambda: {"type": "websocket.connect"}, lambda msg: None)
    assert called


@pytest.mark.asyncio
async def test_request_logging_body_truncation():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 500, "headers": []})
        await send({"type": "http.response.body", "body": b"err"})

    big_body = b"x" * (_REQUEST_LOG_MAX_BODY_BYTES + 1000)
    records = await _run_asgi(
        RequestLoggingMiddleware,
        app,
        _make_http_scope(),
        body=big_body,
    )

    fields = records[0].extra_fields
    assert fields["body_truncated"] is True
    assert len(fields["request_body"]) == _REQUEST_LOG_MAX_BODY_BYTES


@pytest.mark.asyncio
async def test_request_logging_missing_user_agent():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    records = await _run_asgi(
        RequestLoggingMiddleware,
        app,
        _make_http_scope(headers=[]),
    )

    fields = records[0].extra_fields
    assert fields["user_agent"] is None


@pytest.mark.asyncio
async def test_request_logging_accumulates_chunked_response():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"part1", "more_body": True})
        await send({"type": "http.response.body", "body": b"part2", "more_body": False})

    records = await _run_asgi(RequestLoggingMiddleware, app, _make_http_scope())
    fields = records[0].extra_fields
    assert fields["response_size"] == len(b"part1") + len(b"part2")
