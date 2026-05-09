"""FastAPI WebSocket route for ``/realtime/v1/websocket``.

This module is the only place where Phoenix Channels framing meets
Starlette's WebSocket transport.  The routing surface is a single
endpoint::

    ws://<host>/realtime/v1/websocket?apikey=<jwt>&vsn=1.0.0

All framing, encode/decode, ref counters, and heartbeat timing live in
:mod:`.protocol`.  Broker state (subscriptions, presence, fan-out) lives
in :mod:`.broker`.  This module only:

* extracts the JWT (query string ``?apikey=`` or
  ``Sec-WebSocket-Protocol: bearer, <jwt>`` subprotocol — both paths
  used by the official Supabase SDKs);
* runs three concurrent tasks per connection (reader, writer, heartbeat
  watchdog) using :class:`asyncio.TaskGroup`;
* dispatches incoming frames to the right broker call;
* maps domain errors to ``phx_reply`` ``status="error"``.

Token decoding goes through :func:`tokens.decode_access_token` so RS256
support (deferred to v1.0) lights up automatically when the auth module
ships it.
"""

import asyncio
import logging
from typing import Any

import jwt
from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect, WebSocketState

from .. import tokens
from ..settings import get_settings
from .broker import Broker, BrokerError, Connection, get_broker
from .protocol import (
    EVENT_ACCESS_TOKEN,
    EVENT_BROADCAST,
    EVENT_HEARTBEAT,
    EVENT_PHX_CLOSE,
    EVENT_PHX_ERROR,
    EVENT_PHX_JOIN,
    EVENT_PHX_LEAVE,
    EVENT_POSTGRES_CHANGES,  # noqa: F401  (re-exported for completeness)
    EVENT_PRESENCE,
    STATUS_ERROR,
    STATUS_OK,
    TOPIC_PHOENIX,
    HeartbeatTimeout,
    ProtocolError,
    decode,
    encode,
    make_reply,
    make_server_push,
)
from .schemas import Frame, JoinReplyResponse, PhxJoinPayload
from .topics import (
    FilterError,
    TopicError,
    assign_subscription_ids,
    resolved_to_subscription_schema,
    validate_topic,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Close codes (RFC 6455 + Supabase conventions)
# ---------------------------------------------------------------------------

_WS_CLOSE_NORMAL = 1000
_WS_CLOSE_GOING_AWAY = 1001  # used for heartbeat timeout
_WS_CLOSE_POLICY_VIOLATION = 1008  # used for auth failure
_WS_CLOSE_TRY_AGAIN_LATER = 1013  # broker over capacity / writer back-pressure
_WS_CLOSE_INTERNAL_ERROR = 1011

_ANON_CLAIMS: dict[str, Any] = {"role": "anon"}


router = APIRouter(prefix="/realtime/v1", tags=["realtime"])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _extract_token(ws: WebSocket) -> tuple[str | None, str | None]:
    """Pull the JWT off either the query string or the bearer subprotocol.

    Returns ``(token, subprotocol_to_echo)``.  ``subprotocol_to_echo`` is
    ``"bearer"`` if the client used the subprotocol path (so we have to
    accept with that subprotocol to satisfy the RFC 6455 handshake) and
    ``None`` otherwise.
    """
    token = ws.query_params.get("apikey") or ws.query_params.get("access_token")
    if token is not None:
        return token, None
    subprotos = ws.scope.get("subprotocols") or []
    if (
        len(subprotos) >= 2
        and subprotos[0].lower() == "bearer"
        and subprotos[1]
    ):
        return subprotos[1], "bearer"
    return None, None


def _decode_or_anon(token: str | None) -> tuple[str, dict[str, Any]]:
    """Decode *token* into ``(role, claims)``.

    No token → ``("anon", {"role": "anon"})``.  An invalid token raises
    :class:`jwt.InvalidTokenError` which the caller turns into a
    1008 (policy violation) close.
    """
    if not token:
        return "anon", dict(_ANON_CLAIMS)
    claims = tokens.decode_access_token(token)
    role = str(claims.get("role") or "authenticated")
    return role, claims


# ---------------------------------------------------------------------------
# Frame send helpers
# ---------------------------------------------------------------------------


async def _send_frame(ws: WebSocket, frame: Frame) -> None:
    if ws.client_state is not WebSocketState.CONNECTED:
        return
    try:
        await ws.send_text(encode(frame))
    except (WebSocketDisconnect, RuntimeError):
        # Writer races with disconnect; the reader / cleanup path will
        # close the broker registration shortly.
        return


async def _reply_ok(
    ws: WebSocket,
    *,
    join_ref: str | None,
    ref: str | None,
    topic: str,
    response: dict[str, Any] | None = None,
) -> None:
    await _send_frame(
        ws,
        make_reply(
            join_ref=join_ref,
            ref=ref,
            topic=topic,
            status=STATUS_OK,
            response=response,
        ),
    )


async def _reply_error(
    ws: WebSocket,
    *,
    join_ref: str | None,
    ref: str | None,
    topic: str,
    reason: str,
) -> None:
    await _send_frame(
        ws,
        make_reply(
            join_ref=join_ref,
            ref=ref,
            topic=topic,
            status=STATUS_ERROR,
            response={"reason": reason},
        ),
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.websocket("/websocket")
async def realtime_websocket(ws: WebSocket) -> None:
    """Phoenix-channels WebSocket endpoint speaking ``vsn=1.0.0`` JSON."""
    settings = get_settings()
    if not settings.realtime_enabled:
        # Refuse upgrade — no accept = HTTP 403 to the WS handshake.
        await ws.close(code=_WS_CLOSE_INTERNAL_ERROR, reason="realtime disabled")
        return

    token, subprotocol_echo = _extract_token(ws)
    try:
        role, claims = _decode_or_anon(token)
    except jwt.InvalidTokenError as exc:
        logger.warning("realtime: rejecting connection — invalid JWT: %s", exc)
        await ws.close(code=_WS_CLOSE_POLICY_VIOLATION, reason="invalid token")
        return

    await ws.accept(subprotocol=subprotocol_echo)

    broker = get_broker()
    try:
        conn = await broker.register(role=role, claims=claims)
    except BrokerError as exc:
        logger.warning("realtime: rejecting connection — %s", exc)
        await ws.close(code=_WS_CLOSE_TRY_AGAIN_LATER, reason=str(exc))
        return

    heartbeat = HeartbeatTimeout(float(settings.realtime_heartbeat_timeout_seconds))
    max_subs = settings.realtime_max_subs_per_conn
    timed_out = False

    async def _drain() -> None:
        """Writer task: pull frames off the broker outbound queue and send."""
        while True:
            frame = await conn.outbound.get()
            await _send_frame(ws, frame)

    async def _read() -> None:
        """Reader task: parse frames and dispatch to the broker."""
        while True:
            raw = await ws.receive_text()
            heartbeat.touch()
            try:
                frame = decode(raw)
            except ProtocolError as exc:
                logger.debug("realtime: dropped malformed frame: %s", exc)
                continue
            await _dispatch(ws, broker, conn, frame, max_subs=max_subs)

    async def _watchdog() -> None:
        """Heartbeat watchdog: close socket on idle deadline."""
        nonlocal timed_out
        await heartbeat.wait_for_timeout()
        timed_out = True
        # The reader's blocking ws.receive_text() will raise as soon as the
        # socket is closed, unwinding the TaskGroup.
        with _suppress_disconnect():
            await ws.close(code=_WS_CLOSE_GOING_AWAY, reason="heartbeat timeout")

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_read(), name=f"realtime-ws-{conn.id}-read")
            tg.create_task(_drain(), name=f"realtime-ws-{conn.id}-write")
            tg.create_task(_watchdog(), name=f"realtime-ws-{conn.id}-watchdog")
    except* WebSocketDisconnect:
        pass
    except* Exception:  # noqa: BLE001
        logger.exception("realtime: unhandled error on conn=%s", conn.id)
    finally:
        await broker.unregister(conn)
        if ws.client_state is not WebSocketState.DISCONNECTED:
            with _suppress_disconnect():
                await ws.close(code=_WS_CLOSE_NORMAL if not timed_out else _WS_CLOSE_GOING_AWAY)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


async def _dispatch(
    ws: WebSocket,
    broker: Broker,
    conn: Connection,
    frame: Frame,
    *,
    max_subs: int,
) -> None:
    topic = frame.topic
    event = frame.event

    if topic == TOPIC_PHOENIX:
        if event == EVENT_HEARTBEAT:
            await _reply_ok(ws, join_ref=frame.join_ref, ref=frame.ref, topic=topic)
        else:
            logger.debug(
                "realtime: ignoring unsupported phoenix event %r on conn=%s",
                event,
                conn.id,
            )
        return

    # All other events live on a realtime:* channel.
    try:
        validate_topic(topic)
    except TopicError as exc:
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=topic,
            reason=str(exc),
        )
        return

    if event == EVENT_PHX_JOIN:
        await _handle_join(ws, broker, conn, frame, max_subs=max_subs)
        return
    if event == EVENT_PHX_LEAVE:
        await _handle_leave(ws, broker, conn, frame)
        return
    if event == EVENT_ACCESS_TOKEN:
        await _handle_access_token(ws, broker, conn, frame)
        return
    if event == EVENT_BROADCAST:
        await _handle_broadcast(ws, broker, conn, frame)
        return
    if event == EVENT_PRESENCE:
        await _handle_presence(ws, broker, conn, frame)
        return

    logger.debug(
        "realtime: ignoring unknown event %r on topic %r conn=%s",
        event,
        topic,
        conn.id,
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _handle_join(
    ws: WebSocket,
    broker: Broker,
    conn: Connection,
    frame: Frame,
    *,
    max_subs: int,
) -> None:
    try:
        payload = PhxJoinPayload.model_validate(frame.payload)
    except ValidationError as exc:
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=frame.topic,
            reason=f"invalid join config: {exc.errors()[0]['msg']}",
        )
        return

    # Rotate JWT if the join carries one.  Failure here is a hard reject —
    # joining with a bad token would let the client believe it is
    # authenticated when it is not.
    if payload.access_token:
        try:
            role, claims = _decode_or_anon(payload.access_token)
        except jwt.InvalidTokenError as exc:
            await _reply_error(
                ws,
                join_ref=frame.join_ref,
                ref=frame.ref,
                topic=frame.topic,
                reason=f"invalid access_token: {exc}",
            )
            return
        broker.update_claims(conn, role=role, claims=claims)

    # Per-connection subscription cap.  Counts each filter as one
    # subscription so a client that joins 100 channels with 100 filters
    # each does not silently swamp the registry.
    new_total = sum(
        len(s.postgres_changes) for s in conn.subscriptions.values()
    ) + len(payload.config.postgres_changes)
    if new_total > max_subs:
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=frame.topic,
            reason=f"per-connection subscription cap reached ({max_subs})",
        )
        return

    try:
        resolved = assign_subscription_ids(payload.config)
    except FilterError as exc:
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=frame.topic,
            reason=str(exc),
        )
        return

    sub = await broker.subscribe(
        conn,
        topic=frame.topic,
        join_ref=frame.join_ref,
        postgres_changes=resolved,
        broadcast_self=payload.config.broadcast.self_echo,
        presence_key=payload.config.presence.key,
    )

    response = JoinReplyResponse(
        postgres_changes=[resolved_to_subscription_schema(r) for r in sub.postgres_changes],
    )
    await _reply_ok(
        ws,
        join_ref=frame.join_ref,
        ref=frame.ref,
        topic=frame.topic,
        response=response.model_dump(by_alias=True),
    )

    await broker.push_presence_state(conn, frame.topic)


async def _handle_leave(
    ws: WebSocket,
    broker: Broker,
    conn: Connection,
    frame: Frame,
) -> None:
    await broker.unsubscribe(conn, frame.topic)
    await _reply_ok(ws, join_ref=frame.join_ref, ref=frame.ref, topic=frame.topic)
    # Phoenix follows the ack with a phx_close so the SDK can drop its
    # local channel state without a rejoin loop.
    await _send_frame(
        ws,
        make_server_push(topic=frame.topic, event=EVENT_PHX_CLOSE, payload={}),
    )


async def _handle_access_token(
    ws: WebSocket,
    broker: Broker,
    conn: Connection,
    frame: Frame,
) -> None:
    raw = frame.payload.get("access_token") if isinstance(frame.payload, dict) else None
    if not isinstance(raw, str) or not raw:
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=frame.topic,
            reason="missing access_token",
        )
        return
    try:
        role, claims = _decode_or_anon(raw)
    except jwt.InvalidTokenError as exc:
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=frame.topic,
            reason=f"invalid access_token: {exc}",
        )
        # An invalid rotation should not nuke the existing claims; the
        # client may simply have shipped a malformed retry.
        return
    broker.update_claims(conn, role=role, claims=claims)
    await _reply_ok(ws, join_ref=frame.join_ref, ref=frame.ref, topic=frame.topic)


async def _handle_broadcast(
    ws: WebSocket,
    broker: Broker,
    conn: Connection,
    frame: Frame,
) -> None:
    if frame.topic not in conn.subscriptions:
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=frame.topic,
            reason="not joined",
        )
        return
    if conn.is_token_expired and conn.role != "anon":
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=frame.topic,
            reason="access_token expired",
        )
        return
    payload = frame.payload if isinstance(frame.payload, dict) else {}
    inner_event = str(payload.get("event") or "")
    inner_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    broker.broadcast(
        topic=frame.topic,
        event=inner_event,
        payload=inner_payload,  # type: ignore[arg-type]
        sender_id=conn.id,
    )
    if frame.ref is not None:
        await _reply_ok(ws, join_ref=frame.join_ref, ref=frame.ref, topic=frame.topic)


async def _handle_presence(
    ws: WebSocket,
    broker: Broker,
    conn: Connection,
    frame: Frame,
) -> None:
    if frame.topic not in conn.subscriptions:
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=frame.topic,
            reason="not joined",
        )
        return
    if conn.is_token_expired and conn.role != "anon":
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=frame.topic,
            reason="access_token expired",
        )
        return
    payload = frame.payload if isinstance(frame.payload, dict) else {}
    presence_event = str(payload.get("event") or "")
    inner_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}

    try:
        if presence_event == "track":
            await broker.track_presence(conn, topic=frame.topic, meta=inner_payload or {})
        elif presence_event == "untrack":
            await broker.untrack_presence(conn, topic=frame.topic)
        else:
            await _reply_error(
                ws,
                join_ref=frame.join_ref,
                ref=frame.ref,
                topic=frame.topic,
                reason=f"unknown presence event {presence_event!r}",
            )
            return
    except BrokerError as exc:
        await _reply_error(
            ws,
            join_ref=frame.join_ref,
            ref=frame.ref,
            topic=frame.topic,
            reason=str(exc),
        )
        return

    if frame.ref is not None:
        await _reply_ok(ws, join_ref=frame.join_ref, ref=frame.ref, topic=frame.topic)


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


class _suppress_disconnect:
    """Tiny context manager: swallow ``WebSocketDisconnect`` and ``RuntimeError``.

    Closing or sending on an already-closed Starlette ``WebSocket`` raises
    one of these two; in cleanup paths we never want to hide the original
    failure behind a "WebSocket is not connected" wrapper.
    """

    def __enter__(self) -> "_suppress_disconnect":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return exc_type is not None and issubclass(
            exc_type, (WebSocketDisconnect, RuntimeError)
        )


__all__ = [
    "router",
    "EVENT_PHX_ERROR",  # re-exported for downstream convenience
]
