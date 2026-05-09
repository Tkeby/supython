"""Unit tests for input size guards (v0.7 security round 2):

- ``BodySizeLimitMiddleware`` enforces the global ``security_max_body_bytes``
  cap on write methods, exempts streaming routes by path prefix, and
  short-circuits with 413 before the inner app is invoked.
- Auth pydantic schemas reject oversized email / password / token fields
  with 422 — the per-field guard that stops absurd inputs from reaching
  argon2 in particular.

The end-to-end smoke tests that drive the same checks through the live
ASGI app live in `tests/integration/test_input_size_guards.py`.
"""

import json

import pytest
from pydantic import ValidationError

from supython.auth.schemas import (
    MAX_EMAIL_LEN,
    MAX_PASSWORD_LEN,
    MAX_TOKEN_LEN,
    RecoverVerifyRequest,
    RefreshRequest,
    SignUpRequest,
    TokenRequest,
)
from supython.body_size import ERR_BODY_TOO_LARGE, BodySizeLimitMiddleware
from supython.settings import Settings


# ---------------------------------------------------------------------------
# ASGI test harness
# ---------------------------------------------------------------------------


def _http_scope(
    method: str = "POST",
    path: str = "/auth/v1/signup",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
    }


async def _run_middleware(
    middleware,
    scope,
    body_chunks: list[bytes] | None = None,
):
    """Drive a single ASGI request through ``middleware`` with a no-op app
    that records whether it was invoked, and returns the captured response
    messages."""
    app_called = False
    received_body = b""

    async def inner_app(scope, receive, send):
        nonlocal app_called, received_body
        app_called = True
        while True:
            msg = await receive()
            if msg["type"] != "http.request":
                break
            received_body += msg.get("body", b"")
            if not msg.get("more_body", False):
                break
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"ok":true}',
                "more_body": False,
            }
        )

    middleware.app = inner_app

    chunks = list(body_chunks or [])

    async def receive():
        if chunks:
            chunk = chunks.pop(0)
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": bool(chunks),
            }
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[dict] = []

    async def send(msg):
        sent.append(msg)

    await middleware(scope, receive, send)
    return sent, app_called, received_body


def _status(messages: list[dict]) -> int:
    for m in messages:
        if m["type"] == "http.response.start":
            return m["status"]
    raise AssertionError("no response.start in messages")


def _body(messages: list[dict]) -> bytes:
    return b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )


# ---------------------------------------------------------------------------
# Body-size middleware unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passthrough_when_under_limit():
    settings = Settings(security_max_body_bytes=1024)
    mw = BodySizeLimitMiddleware(app=None, settings=settings)
    scope = _http_scope(headers=[(b"content-length", b"10")])
    messages, called, received = await _run_middleware(
        mw, scope, body_chunks=[b'{"x":"y"}']
    )

    assert called is True
    assert _status(messages) == 200
    assert received == b'{"x":"y"}'


@pytest.mark.asyncio
async def test_rejects_oversized_content_length():
    settings = Settings(security_max_body_bytes=100)
    mw = BodySizeLimitMiddleware(app=None, settings=settings)
    scope = _http_scope(headers=[(b"content-length", b"500")])
    messages, called, _ = await _run_middleware(mw, scope)

    assert called is False, "inner app must not be invoked"
    assert _status(messages) == 413
    payload = json.loads(_body(messages))
    assert payload["detail"]["code"] == ERR_BODY_TOO_LARGE


@pytest.mark.asyncio
async def test_rejects_malformed_content_length():
    settings = Settings(security_max_body_bytes=100)
    mw = BodySizeLimitMiddleware(app=None, settings=settings)
    scope = _http_scope(headers=[(b"content-length", b"not-a-number")])
    messages, called, _ = await _run_middleware(mw, scope)

    assert called is False
    assert _status(messages) == 413


@pytest.mark.asyncio
async def test_rejects_oversized_streamed_body_without_content_length():
    settings = Settings(security_max_body_bytes=10)
    mw = BodySizeLimitMiddleware(app=None, settings=settings)
    scope = _http_scope()
    messages, called, _ = await _run_middleware(
        mw,
        scope,
        body_chunks=[b"a" * 5, b"b" * 5, b"c" * 5],
    )

    assert called is True, (
        "streamed receiver must be hooked, even though we cancel mid-stream"
    )
    assert _status(messages) == 413


@pytest.mark.asyncio
async def test_buffers_and_replays_streamed_body_under_limit():
    settings = Settings(security_max_body_bytes=100)
    mw = BodySizeLimitMiddleware(app=None, settings=settings)
    scope = _http_scope()
    messages, called, received = await _run_middleware(
        mw, scope, body_chunks=[b"abc", b"def", b"ghi"]
    )

    assert called is True
    assert received == b"abcdefghi"
    assert _status(messages) == 200


@pytest.mark.asyncio
async def test_skips_get_requests():
    settings = Settings(security_max_body_bytes=10)
    mw = BodySizeLimitMiddleware(app=None, settings=settings)
    scope = _http_scope(method="GET", headers=[(b"content-length", b"500")])
    messages, called, _ = await _run_middleware(mw, scope)

    assert called is True
    assert _status(messages) == 200


@pytest.mark.asyncio
async def test_skips_exempt_storage_path():
    settings = Settings(
        security_max_body_bytes=10,
        security_body_limit_exempt_paths="/storage/v1/object,/functions",
    )
    mw = BodySizeLimitMiddleware(app=None, settings=settings)
    scope = _http_scope(
        path="/storage/v1/object/upload",
        headers=[(b"content-length", b"500")],
    )
    messages, called, _ = await _run_middleware(mw, scope)

    assert called is True
    assert _status(messages) == 200


@pytest.mark.asyncio
async def test_skips_exempt_functions_path():
    settings = Settings(
        security_max_body_bytes=10,
        security_body_limit_exempt_paths="/storage/v1/object,/functions",
    )
    mw = BodySizeLimitMiddleware(app=None, settings=settings)
    scope = _http_scope(
        path="/functions/hello",
        headers=[(b"content-length", b"500")],
    )
    messages, called, _ = await _run_middleware(mw, scope)

    assert called is True
    assert _status(messages) == 200


@pytest.mark.asyncio
async def test_disabled_when_max_bytes_zero():
    settings = Settings(security_max_body_bytes=0)
    mw = BodySizeLimitMiddleware(app=None, settings=settings)
    scope = _http_scope(headers=[(b"content-length", b"500000")])
    messages, called, _ = await _run_middleware(mw, scope)

    assert called is True
    assert _status(messages) == 200


@pytest.mark.asyncio
async def test_passes_through_websocket_scope():
    settings = Settings(security_max_body_bytes=10)
    mw = BodySizeLimitMiddleware(app=None, settings=settings)

    inner_called = False

    async def inner_app(scope, receive, send):
        nonlocal inner_called
        inner_called = True

    mw.app = inner_app

    async def receive():
        return {"type": "websocket.connect"}

    async def send(msg):
        pass

    await mw({"type": "websocket", "path": "/ws", "headers": []}, receive, send)

    assert inner_called is True


# ---------------------------------------------------------------------------
# Per-field length caps
# ---------------------------------------------------------------------------


def test_signup_rejects_oversized_email():
    huge_email = "a" * (MAX_EMAIL_LEN + 1) + "@example.com"
    with pytest.raises(ValidationError):
        SignUpRequest(email=huge_email, password="password123")


def test_signup_rejects_oversized_password():
    with pytest.raises(ValidationError):
        SignUpRequest(
            email="alice@example.com",
            password="x" * (MAX_PASSWORD_LEN + 1),
        )


def test_signup_rejects_short_password():
    with pytest.raises(ValidationError):
        SignUpRequest(email="alice@example.com", password="short")


def test_token_request_rejects_oversized_password():
    with pytest.raises(ValidationError):
        TokenRequest(
            email="alice@example.com",
            password="x" * (MAX_PASSWORD_LEN + 1),
        )


def test_token_request_allows_short_password():
    # Login intentionally has no min_length; the credentials check fails
    # naturally for invalid passwords.
    req = TokenRequest(email="alice@example.com", password="short")
    assert req.password == "short"


def test_refresh_rejects_oversized_token():
    with pytest.raises(ValidationError):
        RefreshRequest(refresh_token="x" * (MAX_TOKEN_LEN + 1))


def test_recover_verify_rejects_oversized_token():
    with pytest.raises(ValidationError):
        RecoverVerifyRequest(
            email="alice@example.com",
            token="x" * (MAX_TOKEN_LEN + 1),
            password="password123",
        )
