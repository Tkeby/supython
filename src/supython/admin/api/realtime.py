"""Admin realtime control plane.

GET  /admin/api/v1/realtime/tables
    List every row in ``realtime.enabled_tables``.

GET  /admin/api/v1/realtime/inspect?topic=...
    SSE stream; subscribe to the broker under ``service_role`` and
    receive broadcast / postgres_changes events in real time.  1 000-event
    cap, then the stream closes cleanly (matches frontend ``useLiveTail``).

POST /admin/api/v1/realtime/broadcast
    Confirm-required broadcast to a topic.  Wraps the broker's
    ``broadcast()`` method.  Audit-logged.
"""

import asyncio
import ipaddress
import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from ... import db
from ...realtime import get_broker
from ...realtime.broker import BrokerError
from ...realtime.schemas import (
    BroadcastResponse,
    EnabledTable,
    JoinConfig,
    PostgresChangesFilter,
)
from ...realtime.topics import TopicError, assign_subscription_ids, validate_topic
from .. import audit
from ..deps import require_admin
from ..schemas import AdminBroadcastRequest
from . import service_realtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/v1/realtime", tags=["admin.realtime"])

# Maximum events pushed before the SSE inspect stream self-closes.
_INSPECT_EVENT_CAP = 1000


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    try:
        ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    return request.client.host


# ---------------------------------------------------------------------------
# GET /tables — list realtime-enabled tables
# ---------------------------------------------------------------------------


@router.get("/tables", response_model=list[EnabledTable])
async def list_tables(
    _: Annotated[UUID, Depends(require_admin)],
) -> list[EnabledTable]:
    """List every row in ``realtime.enabled_tables``."""
    async with db.as_service_role() as conn:
        return await service_realtime.list_enabled_tables(conn)


# ---------------------------------------------------------------------------
# GET /inspect — SSE broker subscriber
# ---------------------------------------------------------------------------


def _sse_event(event: str, data: dict) -> str:
    """Format a single SSE event."""
    payload = json.dumps(data, separators=(",", ":"), default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def _inspect_events(
    topic: str,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE frames from the broker for *topic*.

    Registers a virtual connection under ``service_role``, subscribes to
    *topic* with broadcast and all-tables postgres_changes, then drains
    the broker outbound queue.  Stops after ``_INSPECT_EVENT_CAP`` frames
    or when the client disconnects.
    """
    broker = get_broker()

    try:
        conn = await broker.register(
            role="service_role",
            claims={"role": "service_role"},
        )
    except BrokerError as exc:
        yield _sse_event("error", {"code": "broker_full", "message": str(exc)})
        return

    # Build postgres_changes subscriptions for every enabled table so the
    # admin sees all DB changes flowing through any channel on this topic.
    # Any failure between register and subscribe must unregister the
    # virtual connection so it does not leak a broker slot.
    try:
        async with db.as_service_role() as db_conn:
            enabled = await service_realtime.list_enabled_tables(db_conn)

        postgres_changes = [
            PostgresChangesFilter(
                event="*",
                schema=t.schema_name,
                table=t.table_name,
            )
            for t in enabled
        ]
        config = JoinConfig(postgres_changes=postgres_changes)
        resolved = assign_subscription_ids(config)

        await broker.subscribe(
            conn,
            topic=topic,
            join_ref=None,
            postgres_changes=resolved,
            broadcast_self=True,
            presence_key="",
        )
    except Exception as exc:
        await broker.unregister(conn)
        yield _sse_event(
            "error",
            {"code": "subscribe_failed", "message": str(exc)},
        )
        return

    sent = 0
    try:
        # Yield an initial "connected" event so the frontend knows the
        # subscription is live.
        yield _sse_event(
            "connected",
            {"topic": topic, "tables": len(enabled)},
        )

        while sent < _INSPECT_EVENT_CAP:
            try:
                frame = await asyncio.wait_for(conn.outbound.get(), timeout=30.0)
            except TimeoutError:
                # Heartbeat to keep the connection alive.
                yield _sse_event("heartbeat", {})
                continue

            yield _sse_event(
                frame.event,
                {
                    "topic": frame.topic,
                    "payload": frame.payload,
                },
            )
            sent += 1
    except asyncio.CancelledError:
        pass
    finally:
        try:
            await broker.unregister(conn)
        except Exception:
            logger.debug(
                "realtime inspect: unregister failed for topic=%s",
                topic,
                exc_info=True,
            )


@router.get("/inspect")
async def inspect(
    request: Request,
    _: Annotated[UUID, Depends(require_admin)],
    topic: Annotated[str, Query(description="realtime:<name> topic to subscribe to")],
) -> StreamingResponse:
    """Subscribe to the broker for *topic* and stream events as SSE.

    Events are pushed as ``text/event-stream``.  The stream self-closes
    after 1 000 events or 30 s of inactivity.  Every event carries an
    ``event:`` field matching the Phoenix frame event and a ``data:``
    field with ``{topic, payload}`` JSON.
    """
    try:
        validate_topic(topic)
    except TopicError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_topic", "message": str(exc)},
        ) from exc

    broker = get_broker()
    if not broker.is_healthy:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "broker_unhealthy",
                "message": "Realtime broker is not running",
            },
        )

    logger.debug("realtime inspect: admin subscribed to topic=%s", topic)

    async def _stream() -> AsyncGenerator[str, None]:
        async for chunk in _inspect_events(topic):
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /broadcast — confirm-required broadcast
# ---------------------------------------------------------------------------


@router.post(
    "/broadcast",
    response_model=BroadcastResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def broadcast(
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
    body: Annotated[AdminBroadcastRequest, Body()],
) -> BroadcastResponse:
    """Fan a broadcast frame out to every subscriber of *topic*.

    Confirm-required by the frontend (Story 10.3).  The confirmation
    dialog is presented in the UI before this endpoint is called; the
    backend simply executes the broadcast under ``service_role`` and
    logs an audit event.
    """
    try:
        validate_topic(body.topic)
    except TopicError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_topic", "message": str(exc)},
        ) from exc

    broker = get_broker()
    delivered = broker.broadcast(
        topic=body.topic,
        event=body.event,
        payload=body.payload,
        sender_id=None,
    )

    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    async with db.as_service_role() as conn:
        await audit.write(
            conn,
            admin_id=admin_id,
            action="realtime.broadcast",
            target=body.topic,
            payload={
                "event": body.event,
                "delivered": delivered,
            },
            ip=ip,
            ua=ua,
        )
    return BroadcastResponse(topic=body.topic, delivered=delivered)
