"""HTTP control plane for the realtime module.

Exposes three REST endpoints under ``/realtime/v1`` and mounts the
WebSocket route from :mod:`.websocket` onto the same router so that a
single ``app.include_router(realtime.router)`` call wires up both the
REST surface and the channel transport:

``POST /realtime/v1/enable``
    Service-role only.  Opt a table into change-event fan-out.  Wraps
    :func:`service.enable_table`.

``GET /realtime/v1/info``
    List the contents of ``realtime.enabled_tables`` under the caller's
    role (RLS still applies).

``POST /realtime/v1/broadcast/{topic}``
    Service-role only.  Push a Phoenix ``broadcast`` frame to every
    subscriber of ``topic``.  Useful for server-to-client pushes from
    edge functions and cron jobs that don't want to hold a WebSocket.

``WS  /realtime/v1/websocket``
    The actual channel transport — see :mod:`.websocket`.
"""

from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status

from .. import db, tokens
from . import service
from .broker import get_broker
from .schemas import (
    BroadcastRequest,
    BroadcastResponse,
    EnabledTable,
    EnableTableRequest,
)
from .topics import TopicError, validate_topic
from .websocket import realtime_websocket

router = APIRouter(prefix="/realtime/v1", tags=["realtime"])


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


def _realtime_error(exc: service.RealtimeError) -> HTTPException:
    return HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": exc.message},
    )


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------


async def _current_claims(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Decode the bearer JWT and return its claims."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        return tokens.decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}"
        ) from exc


def _claims_role(claims: dict[str, Any]) -> str:
    role = claims.get("role")
    if not isinstance(role, str) or not role:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing role claim")
    return role


def _require_service_role(claims: dict[str, Any]) -> None:
    if _claims_role(claims) != "service_role":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "forbidden",
                "message": "service_role required",
            },
        )


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.post("/enable", response_model=EnabledTable, status_code=201)
async def enable_table(
    payload: EnableTableRequest,
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
) -> EnabledTable:
    """Opt a table into realtime change events.

    Only callable with a ``service_role`` JWT.  Returns the freshly
    written :class:`EnabledTable` row so the caller can echo it back to
    the user.
    """
    _require_service_role(claims)
    try:
        async with db.as_service_role(claims=claims) as conn:
            return await service.enable_table(conn, payload)
    except service.RealtimeError as exc:
        raise _realtime_error(exc) from exc


@router.get("/info", response_model=list[EnabledTable])
async def list_info(
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
) -> list[EnabledTable]:
    """List every row of ``realtime.enabled_tables`` visible to the caller.

    The registry has its own RLS policy granting ``select`` to ``anon``,
    ``authenticated``, and ``service_role`` (see migration 0006), so all
    callers see the same rows in v0.4 — but reads still go through a
    role-scoped connection so future per-row policies are honoured
    without changes here.
    """
    role = _claims_role(claims)
    if role == "service_role":
        async with db.as_service_role(claims=claims) as conn:
            return await service.list_enabled(conn)
    try:
        async with db.as_role(role, claims) as conn:
            return await service.list_enabled(conn)
    except ValueError as exc:
        # Role decoded from the JWT is not in db_allowed_roles.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": str(exc)},
        ) from exc


@router.post(
    "/broadcast/{topic}",
    response_model=BroadcastResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def broadcast(
    topic: str,
    payload: BroadcastRequest,
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
) -> BroadcastResponse:
    """Fan a Phoenix ``broadcast`` frame out to every subscriber of *topic*.

    Service-role only.  REST-initiated broadcasts have no sender id, so
    the sender-exclusion logic is a no-op — every subscriber receives
    the frame.
    """
    _require_service_role(claims)
    try:
        validate_topic(topic)
    except TopicError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_topic", "message": str(exc)},
        ) from exc
    delivered = get_broker().broadcast(
        topic=topic,
        event=payload.event,
        payload=payload.payload,
        sender_id=None,
    )
    return BroadcastResponse(topic=topic, delivered=delivered)


# ---------------------------------------------------------------------------
# WebSocket transport — same prefix, same router
# ---------------------------------------------------------------------------


router.add_api_websocket_route("/websocket", realtime_websocket)
