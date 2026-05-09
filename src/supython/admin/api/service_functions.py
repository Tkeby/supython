"""Admin service for the functions surface.

Three responsibilities:

1. Enumerate routes the running registry has discovered.
2. Read a function's source from disk (only for files registered as routes).
3. Invoke a function under ``service_role`` on behalf of the operator —
   never minting an end-user JWT (Story 9.2 v1.1.3 contract).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.requests import Request

from ... import db
from ...functions.loader import get_registry
from ...functions.schemas import FunctionMeta
from ...settings import get_settings
from ..errors import AdminError
from ..schemas import (
    FunctionInvokeRequest,
    FunctionInvokeResponse,
    FunctionRoute,
    FunctionSourceResponse,
)

logger = logging.getLogger(__name__)


_MAX_SOURCE_BYTES = 1_000_000


def list_routes() -> list[FunctionRoute]:
    return [
        FunctionRoute(
            name=meta.name,
            path=str(meta.path),
            methods=list(meta.methods),
            auth=meta.auth,
        )
        for meta in get_registry().list()
    ]


def _resolve_meta(name: str) -> FunctionMeta:
    meta = get_registry().get(name)
    if meta is None:
        raise AdminError("function_not_found", f"function {name!r} not found", 404)
    return meta


def read_source(name: str) -> FunctionSourceResponse:
    meta = _resolve_meta(name)
    try:
        size = meta.path.stat().st_size
    except OSError as exc:
        raise AdminError(
            "function_source_unreadable",
            f"could not stat function source: {exc}",
            500,
        ) from exc
    if size > _MAX_SOURCE_BYTES:
        raise AdminError(
            "function_source_too_large",
            f"source exceeds {_MAX_SOURCE_BYTES} bytes",
            413,
        )
    try:
        text = meta.path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AdminError(
            "function_source_unreadable",
            f"could not read function source: {exc}",
            500,
        ) from exc
    return FunctionSourceResponse(
        name=meta.name,
        path=str(meta.path),
        source=text,
        size=size,
    )


def _build_request(
    name: str,
    method: str,
    headers: dict[str, str],
    body: bytes,
    query: str | None,
) -> Request:
    """Build a Starlette Request that mirrors a real /functions/{name} call."""
    raw_headers: list[tuple[bytes, bytes]] = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in headers.items()
    ]
    has_content_length = any(k == b"content-length" for k, _ in raw_headers)
    if not has_content_length:
        raw_headers.append((b"content-length", str(len(body)).encode("latin-1")))

    path = f"/functions/{name}"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "server": ("admin-invoke", 80),
        "client": ("127.0.0.1", 0),
        "root_path": "",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": (query or "").encode("latin-1"),
        "headers": raw_headers,
    }

    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return Request(scope, receive=receive)


def _translate(result: Any) -> Response:
    """Same translation contract as functions/router.py — kept local to avoid
    importing a private symbol across modules."""
    if isinstance(result, Response):
        return result
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], int):
        status_code, payload = result
        inner = _translate(payload)
        inner.status_code = status_code
        return inner
    if isinstance(result, BaseModel):
        return JSONResponse(content=result.model_dump(mode="json"))
    if isinstance(result, (dict, list)) or result is None:
        return JSONResponse(content=result)
    if isinstance(result, (str, int, bool)):
        return JSONResponse(content=result)
    if isinstance(result, bytes):
        return Response(content=result, media_type="application/octet-stream")
    raise AdminError(
        "function_invalid_return",
        f"handler returned unsupported type {type(result).__name__!r}",
        500,
    )


def _serialize_response(response: Response, elapsed_ms: float) -> FunctionInvokeResponse:
    raw_body = getattr(response, "body", b"") or b""
    if isinstance(raw_body, memoryview):
        raw_body = bytes(raw_body)
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        body_text = ""
    parsed: Any | None = None
    if body_text:
        try:
            parsed = json.loads(body_text)
        except (json.JSONDecodeError, ValueError):
            parsed = None
    headers: dict[str, str] = {}
    for key, value in response.headers.items():
        headers[key] = value
    return FunctionInvokeResponse(
        status=response.status_code,
        headers=headers,
        body=parsed,
        body_text=body_text,
        elapsed_ms=elapsed_ms,
    )


async def invoke_function(
    name: str,
    payload: FunctionInvokeRequest,
) -> FunctionInvokeResponse:
    """Invoke a discovered function under ``service_role``.

    The admin session never becomes an end-user JWT — claims set on the
    connection are informational (``role=service_role``) so audit/stamping
    helpers behave, but RLS is bypassed by ``service_role`` regardless.
    """
    meta = _resolve_meta(name)
    method = payload.method.upper()
    if method not in meta.methods:
        raise AdminError(
            "method_not_allowed",
            f"function {name!r} does not allow {method}",
            405,
        )

    if payload.body is None:
        body_bytes = b""
    elif isinstance(payload.body, (dict, list)):
        body_bytes = json.dumps(payload.body).encode("utf-8")
    elif isinstance(payload.body, str):
        body_bytes = payload.body.encode("utf-8")
    else:
        body_bytes = json.dumps(payload.body).encode("utf-8")

    headers = dict(payload.headers or {})
    has_content_type = any(k.lower() == "content-type" for k in headers)
    if body_bytes and not has_content_type and isinstance(payload.body, (dict, list)):
        headers["content-type"] = "application/json"

    request = _build_request(meta.name, method, headers, body_bytes, payload.query)

    settings = get_settings()
    handler = meta.handler
    assert handler is not None  # validated at load

    from ...functions.context import build_ctx  # local import: avoid cycles

    started = time.monotonic()
    try:
        async with db.as_service_role(claims={"role": "service_role"}) as conn:
            ctx = build_ctx(
                conn=conn,
                user=None,
                request=request,
                raw_jwt=None,
                settings=settings,
            )
            try:
                result = await asyncio.wait_for(
                    handler(request, ctx),
                    timeout=settings.functions_max_handler_seconds,
                )
            finally:
                try:
                    await ctx.postgrest.aclose()
                except Exception:
                    logger.warning(
                        "admin.functions: postgrest close failed for %s",
                        meta.name,
                        exc_info=True,
                    )
    except TimeoutError:
        elapsed = (time.monotonic() - started) * 1000.0
        return FunctionInvokeResponse(
            status=status.HTTP_504_GATEWAY_TIMEOUT,
            headers={"content-type": "application/json"},
            body={
                "code": "function_timeout",
                "message": (
                    f"function exceeded {settings.functions_max_handler_seconds}s"
                ),
            },
            body_text="",
            elapsed_ms=elapsed,
        )
    except AdminError:
        raise
    except Exception as exc:
        logger.warning(
            "admin.functions: handler %s raised", meta.name, exc_info=True
        )
        elapsed = (time.monotonic() - started) * 1000.0
        return FunctionInvokeResponse(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers={"content-type": "application/json"},
            body={
                "code": "function_error",
                "message": str(exc) or "function raised an unhandled exception",
            },
            body_text="",
            elapsed_ms=elapsed,
        )

    elapsed = (time.monotonic() - started) * 1000.0
    response = _translate(result)
    return _serialize_response(response, elapsed)
