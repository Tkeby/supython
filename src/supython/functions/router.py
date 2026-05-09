"""HTTP dispatcher for filesystem-loaded functions.

Single ``/functions/{name:path}`` route that:

1. Looks the function up in the registry (mtime-checked when hot reload is on).
2. Enforces ``methods`` and ``auth`` declared by the module.
3. Body-size guards via ``settings.functions_max_body_bytes`` (the cap is on
   what the dispatcher will eagerly buffer; handlers can still consume
   ``request.stream()`` directly for true streaming uploads).
4. Builds a :class:`~.context.Ctx` against a role-scoped connection from
   ``db.as_role`` and invokes the handler.
5. Translates the return value into a FastAPI response.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import jwt
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import db, tokens
from ..settings import get_settings
from ..storage import service as storage_service
from .context import FunctionUser, build_ctx
from .loader import get_registry
from .schemas import (
    ERR_BODY_TOO_LARGE,
    ERR_FUNCTION_ERROR,
    ERR_FUNCTION_TIMEOUT,
    ERR_INVALID_RETURN,
    ERR_INVALID_TOKEN,
    ERR_METHOD_NOT_ALLOWED,
    ERR_NOT_FOUND,
    FunctionMeta,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/functions", tags=["functions"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _err(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    return auth.split(" ", 1)[1].strip() or None


def _decode_or_none(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        return tokens.decode_access_token(raw)
    except jwt.PyJWTError:
        return None


def _enforce_body_limit(request: Request, max_bytes: int) -> None:
    cl = request.headers.get("content-length")
    if cl is None:
        return
    try:
        n = int(cl)
    except ValueError:
        return
    if n > max_bytes:
        raise _err(
            status.HTTP_413_CONTENT_TOO_LARGE,
            ERR_BODY_TOO_LARGE,
            f"Body exceeds {max_bytes} bytes",
        )


def _translate(result: Any) -> Response:
    """Map handler returns to a Response. Order matters — Response first."""
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
    raise _err(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ERR_INVALID_RETURN,
        f"Handler returned unsupported type {type(result).__name__!r}",
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


@router.api_route(
    "/{name:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def dispatch(name: str, request: Request) -> Response:
    meta = get_registry().get(name)
    if meta is None:
        raise _err(status.HTTP_404_NOT_FOUND, ERR_NOT_FOUND, name)
    if request.method not in meta.methods:
        raise _err(
            status.HTTP_405_METHOD_NOT_ALLOWED,
            ERR_METHOD_NOT_ALLOWED,
            request.method,
        )
    return await _invoke(meta, request)


async def _invoke(meta: FunctionMeta, request: Request) -> Response:
    settings = get_settings()
    _enforce_body_limit(request, settings.functions_max_body_bytes)

    raw_jwt = _extract_bearer(request)
    claims = _decode_or_none(raw_jwt)

    if meta.auth == "authenticated" and (raw_jwt is None or claims is None):
        raise _err(
            status.HTTP_401_UNAUTHORIZED,
            ERR_INVALID_TOKEN,
            "Missing or invalid bearer token",
        )

    if claims is not None:
        allowed = settings.db_allowed_roles
        role = claims.get("role") if isinstance(claims.get("role"), str) else "anon"

        if role not in allowed:
            raise _err(
                status.HTTP_401_UNAUTHORIZED,
                ERR_INVALID_TOKEN,
                f"Invalid role: {role!r}",
            )
        user: FunctionUser | None = FunctionUser.from_claims(claims)
        ctx_claims = claims
    else:
        role = "anon"
        user = None
        ctx_claims = {"role": "anon"}

    handler = meta.handler
    assert handler is not None  # validated at load time

    try:
        async with db.as_role(role, ctx_claims) as conn:
            ctx = build_ctx(
                conn=conn,
                user=user,
                request=request,
                raw_jwt=raw_jwt if meta.auth == "authenticated" or raw_jwt else None,
                settings=settings,
            )
            try:
                # wait_for wraps only the handler so a timeout cancels user
                # code while still letting `as_role`'s transaction roll back
                # cleanly on the way out.
                result = await asyncio.wait_for(
                    handler(request, ctx),
                    timeout=settings.functions_max_handler_seconds,
                )
            finally:
                try:
                    await ctx.postgrest.aclose()
                except Exception:
                    logger.warning("functions: postgrest close failed for %s", meta.name, exc_info=True)
    except HTTPException:
        raise
    except storage_service.StorageError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except TimeoutError:
        logger.warning(
            "functions: handler %s exceeded %.2fs timeout",
            meta.name,
            settings.functions_max_handler_seconds,
        )
        raise _err(
            status.HTTP_504_GATEWAY_TIMEOUT,
            ERR_FUNCTION_TIMEOUT,
            f"Function exceeded {settings.functions_max_handler_seconds}s",
        ) from None
    except (KeyboardInterrupt, SystemExit):
        # Lifecycle signals must reach the server, never become a 500.
        raise
    except asyncio.CancelledError:
        # Real client-disconnect / shutdown cancellation. wait_for converts
        # its internal cancellation to TimeoutError above, so this branch
        # only fires for cancellations originating outside the dispatcher.
        raise
    except Exception:
        logger.warning("functions: handler %s raised", meta.name, exc_info=True)
        raise _err(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ERR_FUNCTION_ERROR,
            "Function raised an unhandled exception",
        ) from None

    return _translate(result)
