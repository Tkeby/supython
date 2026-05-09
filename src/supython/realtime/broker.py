"""In-process realtime broker.

The broker is the heart of the realtime module:

* It owns a single dedicated ``asyncpg.Connection`` running
  ``LISTEN realtime:changes``.  When the trigger function in
  :file:`migrations/0006_realtime_schema.sql` fires ``pg_notify``, the
  payload lands here and is dispatched to in-process subscribers.

* It tracks every WebSocket connection and the channels each connection
  has joined.  Per-connection bounded queues provide back-pressure so a
  slow client cannot drown the process; on overflow we drop the oldest
  frame and increment a counter exposed for metrics.

* It performs the per-event RLS visibility check by acquiring a
  role-scoped connection (via :func:`db.as_role`) for the subscriber.
  ``service_role`` connections — used for server-side fan-out from edge
  functions — bypass the check, matching Postgres semantics.

* For ``DELETE`` events the row is gone, so the broker falls back to
  comparing ``old_record.<owner_column>`` against the subscriber's
  ``auth.uid()``.  If the table was registered with ``owner_column =
  null``, ``DELETE`` events are only delivered to ``service_role``
  subscribers.

* It maintains presence state (``dict[topic, dict[key, list[meta]]]``)
  in memory and emits ``presence_state`` / ``presence_diff`` frames.

The broker is a singleton.  ``get_broker()`` returns the lazily-created
instance; tests that need isolation can call ``reset_broker()`` between
runs or instantiate :class:`Broker` directly.
"""

import asyncio
import contextlib
import itertools
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import ValidationError

from .. import db
from ..settings import get_settings
from .protocol import (
    EVENT_BROADCAST,
    EVENT_POSTGRES_CHANGES,
    EVENT_PRESENCE_DIFF,
    EVENT_PRESENCE_STATE,
    make_server_push,
)
from .schemas import (
    EnabledTable,
    Frame,
    PostgresChangesData,
    PostgresChangesPush,
    PresenceDiff,
)
from .service import get_enabled, rls_check
from .topics import EqFilter, InFilter, ParsedFilter, ResolvedSubscription

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subscription bookkeeping
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ChannelSubscription:
    """A single channel join held by one WebSocket connection.

    Each connection may join multiple ``realtime:<name>`` channels.  Each
    join carries an ordered list of :class:`ResolvedSubscription` (the
    server-assigned ids / parsed filters for the join's
    ``config.postgres_changes`` entries), plus broadcast and presence
    config.
    """

    topic: str
    join_ref: str | None
    postgres_changes: list[ResolvedSubscription] = field(default_factory=list)
    broadcast_self: bool = False
    presence_key: str = ""


@dataclass(slots=True)
class Connection:
    """One WebSocket connection registered with the broker.

    ``role`` and ``claims`` reflect the *current* JWT — they may be
    updated mid-stream when the client sends an ``access_token`` event.
    The outbound queue is bounded; producers (the broker) drop the
    oldest frame on overflow rather than block, and the WS writer task
    drains it.
    """

    id: int
    role: str
    claims: dict[str, Any]
    outbound: asyncio.Queue[Frame]
    subscriptions: dict[str, ChannelSubscription] = field(default_factory=dict)
    dropped: int = 0
    closed: bool = False

    @property
    def is_token_expired(self) -> bool:
        """True when the JWT ``exp`` claim is in the past.

        ``anon`` connections (and any connection without an ``exp``
        claim) never expire.  Used by the broker to stop forwarding
        ``postgres_changes`` and by the WS layer to reject ``broadcast``
        / ``presence`` until a fresh ``access_token`` arrives.
        """
        exp = self.claims.get("exp")
        if exp is None:
            return False
        try:
            return time.time() >= float(exp)
        except (TypeError, ValueError):
            return False


# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------


class BrokerError(RuntimeError):
    """Raised when the broker is misused (e.g. unknown table, queue full)."""


class Broker:
    """In-process realtime fan-out engine.

    Lifecycle:

    * :meth:`start` — opens the dedicated listener connection and
      attaches the LISTEN callback.  Idempotent.
    * :meth:`stop` — detaches the listener and closes the connection.

    All other methods are safe to call only between ``start`` and
    ``stop``.
    """

    # Conservative ceiling for reconnect backoff.  Five minutes is long
    # enough that even a flapping pg_notify connection does not hot-loop,
    # short enough that a recovered DB is picked up before clients give up.
    _MAX_RECONNECT_BACKOFF_S = 300.0
    _INITIAL_RECONNECT_BACKOFF_S = 1.0

    def __init__(self) -> None:
        s = get_settings()
        self._channel: str = s.realtime_notify_channel
        self._queue_size: int = s.realtime_broker_queue_size
        self._rls_timeout: float = s.realtime_rls_check_timeout_s
        self._max_connections: int = s.realtime_max_connections
        self._database_url: str = s.database_url

        self._connections: dict[int, Connection] = {}
        # topic -> set of connection ids subscribed
        self._topics: dict[str, set[int]] = {}
        # topic -> presence key -> ordered list of (conn_id, meta) tuples.
        # We keep conn_id so we can clean up when a connection departs.
        self._presence: dict[str, dict[str, list[tuple[int, dict[str, Any]]]]] = {}
        # Cache for realtime.enabled_tables; populated lazily per (schema, table).
        # The cache is invalidated only on broker restart — calls to
        # realtime.enable() during a long-running process won't be picked up
        # without a restart, which is acceptable for v0.4.
        self._registry_cache: dict[tuple[str, str], EnabledTable | None] = {}

        self._conn_id_counter: itertools.count[int] = itertools.count(1)
        self._listener: asyncpg.Connection | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._stopping: bool = False
        self._lock = asyncio.Lock()

    # -- lifecycle ----------------------------------------------------------

    @property
    def is_healthy(self) -> bool:
        """True when the listener task is running and the connection is open."""
        if self._stopping:
            return False
        if self._listener_task is None or self._listener_task.done():
            return False
        return self._listener is not None and not self._listener.is_closed()

    @property
    def connection_count(self) -> int:
        """Number of registered realtime connections."""
        return len(self._connections)

    async def start(self) -> None:
        """Start the dedicated LISTEN connection in the background."""
        if self._listener_task is not None and not self._listener_task.done():
            return
        self._stopping = False
        self._listener_task = asyncio.create_task(
            self._listener_loop(), name="realtime-broker-listener"
        )

    async def stop(self) -> None:
        """Detach the listener and close the dedicated connection."""
        self._stopping = True
        if self._listener_task is not None:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        if self._listener is not None and not self._listener.is_closed():
            with contextlib.suppress(Exception):
                await self._listener.remove_listener(self._channel, self._on_notification)
            with contextlib.suppress(Exception):
                await self._listener.close()
            self._listener = None
        # Drain registered connections so test runs do not leak state.
        self._connections.clear()
        self._topics.clear()
        self._presence.clear()
        self._registry_cache.clear()

    # -- connection registry -----------------------------------------------

    async def register(
        self,
        *,
        role: str,
        claims: dict[str, Any],
    ) -> Connection:
        """Register a fresh WebSocket connection.

        Raises :class:`BrokerError` if the per-process connection cap is
        already reached.
        """
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                raise BrokerError(
                    f"realtime: connection cap reached ({self._max_connections})"
                )
            conn = Connection(
                id=next(self._conn_id_counter),
                role=role,
                claims=claims,
                outbound=asyncio.Queue(maxsize=self._queue_size),
            )
            self._connections[conn.id] = conn
            return conn

    async def unregister(self, conn: Connection) -> None:
        """Remove a connection and tear down all its subscriptions/presence."""
        async with self._lock:
            conn.closed = True
            self._connections.pop(conn.id, None)
            for topic in list(conn.subscriptions.keys()):
                self._unsubscribe_locked(conn, topic, send_diff=True)

    def update_claims(
        self,
        conn: Connection,
        *,
        role: str,
        claims: dict[str, Any],
    ) -> None:
        """Mutate the role/claims of an existing connection (access_token)."""
        conn.role = role
        conn.claims = claims

    # -- channel subscribe / leave -----------------------------------------

    async def subscribe(
        self,
        conn: Connection,
        *,
        topic: str,
        join_ref: str | None,
        postgres_changes: list[ResolvedSubscription],
        broadcast_self: bool,
        presence_key: str,
    ) -> ChannelSubscription:
        """Attach *conn* to *topic* with the given config.

        Idempotent on re-join: an existing subscription on the same topic
        is replaced, and any presence entries owned by the connection on
        that topic are cleared first.
        """
        async with self._lock:
            if topic in conn.subscriptions:
                self._unsubscribe_locked(conn, topic, send_diff=True)
            sub = ChannelSubscription(
                topic=topic,
                join_ref=join_ref,
                postgres_changes=list(postgres_changes),
                broadcast_self=broadcast_self,
                presence_key=presence_key or str(conn.id),
            )
            conn.subscriptions[topic] = sub
            self._topics.setdefault(topic, set()).add(conn.id)
            return sub

    async def unsubscribe(self, conn: Connection, topic: str) -> None:
        """Detach *conn* from *topic* and emit a presence diff if needed."""
        async with self._lock:
            self._unsubscribe_locked(conn, topic, send_diff=True)

    def _unsubscribe_locked(
        self,
        conn: Connection,
        topic: str,
        *,
        send_diff: bool,
    ) -> None:
        conn.subscriptions.pop(topic, None)
        peers = self._topics.get(topic)
        if peers is not None:
            peers.discard(conn.id)
            if not peers:
                self._topics.pop(topic, None)
        leaves = self._drop_presence_for(conn, topic)
        if send_diff and leaves:
            self._emit_presence_diff_locked(topic, joins={}, leaves=leaves)

    # -- broadcast ----------------------------------------------------------

    def broadcast(
        self,
        *,
        topic: str,
        event: str,
        payload: dict[str, Any],
        sender_id: int | None = None,
    ) -> int:
        """Fan a Phoenix ``broadcast`` event out to every subscriber of *topic*.

        ``sender_id`` is the connection id of the originator (or ``None``
        for REST-initiated broadcasts).  The sender is excluded from the
        fan-out unless they joined with ``config.broadcast.self = true``.

        Returns the number of recipients the frame was enqueued for.
        """
        peers = self._topics.get(topic)
        if not peers:
            return 0
        frame = make_server_push(
            topic=topic,
            event=EVENT_BROADCAST,
            payload={"type": "broadcast", "event": event, "payload": payload},
        )
        delivered = 0
        for cid in list(peers):
            conn = self._connections.get(cid)
            if conn is None or conn.closed:
                continue
            if cid == sender_id:
                sub = conn.subscriptions.get(topic)
                if sub is None or not sub.broadcast_self:
                    continue
            if self._enqueue(conn, frame):
                delivered += 1
        return delivered

    # -- presence -----------------------------------------------------------

    async def track_presence(
        self,
        conn: Connection,
        *,
        topic: str,
        meta: dict[str, Any],
    ) -> None:
        """Add a presence entry for *conn* on *topic*."""
        async with self._lock:
            sub = conn.subscriptions.get(topic)
            if sub is None:
                raise BrokerError(
                    f"connection {conn.id} cannot track presence on {topic!r} — not joined"
                )
            key = sub.presence_key
            bucket = self._presence.setdefault(topic, {}).setdefault(key, [])
            bucket.append((conn.id, meta))
            self._emit_presence_diff_locked(
                topic,
                joins={key: [meta]},
                leaves={},
            )

    async def untrack_presence(
        self,
        conn: Connection,
        *,
        topic: str,
    ) -> None:
        """Remove every presence entry owned by *conn* on *topic*."""
        async with self._lock:
            leaves = self._drop_presence_for(conn, topic)
            if leaves:
                self._emit_presence_diff_locked(topic, joins={}, leaves=leaves)

    def presence_state(self, topic: str) -> dict[str, list[dict[str, Any]]]:
        """Snapshot the current presence map for *topic*.

        The returned dict is a fresh copy — callers may mutate it freely.
        """
        bucket = self._presence.get(topic) or {}
        return {key: [meta for _cid, meta in entries] for key, entries in bucket.items()}

    async def push_presence_state(self, conn: Connection, topic: str) -> None:
        """Send the full ``presence_state`` for *topic* to *conn* (post-join).

        Supabase ships ``presence_state`` with the raw key→[meta] map as
        the payload (no ``presences`` wrapper); we mirror that shape.
        """
        state = self.presence_state(topic)
        frame = make_server_push(
            topic=topic,
            event=EVENT_PRESENCE_STATE,
            payload=state,
        )
        self._enqueue(conn, frame)

    # -- postgres_changes fan-out ------------------------------------------

    async def _on_notification(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """asyncpg LISTEN callback — runs on the listener connection."""
        if channel != self._channel:
            return
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("realtime: dropped malformed notify payload (not JSON)")
            return
        try:
            await self._fanout_change(event)
        except Exception:  # noqa: BLE001 — broker must never propagate
            logger.exception("realtime: fan-out failed for payload=%s", payload[:200])

    async def fanout_change(self, event: dict[str, Any]) -> None:
        """Public entry point used by tests to inject a synthetic notify event."""
        await self._fanout_change(event)

    async def _fanout_change(self, event: dict[str, Any]) -> None:
        try:
            data = PostgresChangesData.model_validate(
                {
                    "schema": event.get("schema"),
                    "table": event.get("table"),
                    "type": event.get("type"),
                    "commit_timestamp": event.get("commit_timestamp"),
                    "columns": event.get("columns") or [],
                    "record": event.get("record"),
                    "old_record": event.get("old_record"),
                }
            )
        except ValidationError as exc:
            logger.warning("realtime: dropped malformed notify payload: %s", exc)
            return

        registry = await self._lookup_registry(data.schema_name, data.table)
        if registry is None:
            logger.debug(
                "realtime: notify for %s.%s but table is not in the registry",
                data.schema_name,
                data.table,
            )
            return

        # Snapshot recipients under the lock so concurrent subscribe/leave
        # calls don't trip our iteration; the actual SELECT 1 RLS probes
        # happen outside the lock.
        candidates: list[tuple[Connection, ChannelSubscription, list[int]]] = []
        async with self._lock:
            for conn in self._connections.values():
                if conn.closed:
                    continue
                for sub in conn.subscriptions.values():
                    matched_ids = _match_subscription_ids(sub, data)
                    if matched_ids:
                        candidates.append((conn, sub, matched_ids))

        if not candidates:
            return

        for conn, _sub, matched_ids in candidates:
            try:
                allowed = await self._authorize(conn, data, registry)
            except Exception:  # noqa: BLE001 — never let one client stall fan-out
                logger.exception(
                    "realtime: authorize failed for conn=%s table=%s.%s",
                    conn.id,
                    data.schema_name,
                    data.table,
                )
                continue
            if not allowed:
                continue
            push = PostgresChangesPush(ids=matched_ids, data=data)
            frame = make_server_push(
                topic=_topic_for(conn, data),
                event=EVENT_POSTGRES_CHANGES,
                payload=push.model_dump(mode="json"),
            )
            self._enqueue(conn, frame)

    async def _authorize(
        self,
        conn: Connection,
        data: PostgresChangesData,
        registry: EnabledTable,
    ) -> bool:
        # service_role bypasses RLS by Postgres convention; mirror it here so
        # server-side listeners (edge functions) see everything.
        if conn.role == "service_role":
            return True

        # Stop forwarding to authenticated subscribers whose JWT has expired
        # mid-stream — the connection stays open (heartbeats continue) so the
        # client can rotate via the access_token in-channel event.
        if conn.is_token_expired:
            return False

        if data.type == "DELETE":
            # The row is gone — fall back to the owner-column short circuit.
            if registry.owner_column is None:
                return False
            owner_value = (data.old_record or {}).get(registry.owner_column)
            if owner_value is None:
                return False
            uid = conn.claims.get("sub")
            if uid is None:
                return False
            try:
                return UUID(str(owner_value)) == UUID(str(uid))
            except (ValueError, AttributeError):
                # Non-UUID owner columns: fall back to string equality.
                return str(owner_value) == str(uid)

        # INSERT / UPDATE: probe with a role-scoped SELECT 1.
        record = data.record or {}
        try:
            pk_values = [record[col] for col in registry.pk_columns]
        except KeyError as exc:
            logger.warning(
                "realtime: %s.%s notification missing pk column %s; dropping",
                data.schema_name,
                data.table,
                exc,
            )
            return False

        try:
            async with db.as_role(conn.role, conn.claims) as scoped:
                return await rls_check(
                    scoped,
                    schema_name=registry.schema_name,
                    table_name=registry.table_name,
                    pk_columns=registry.pk_columns,
                    pk_values=pk_values,
                    timeout=self._rls_timeout,
                )
        except ValueError:
            # role not in db_allowed_roles (e.g. "service_role" through the WS path)
            # — treat as deny to be safe; the service_role short-circuit above
            # is the only legitimate way through.
            return False

    # -- internals ----------------------------------------------------------

    async def _lookup_registry(
        self,
        schema_name: str,
        table_name: str,
    ) -> EnabledTable | None:
        key = (schema_name, table_name)
        if key in self._registry_cache:
            return self._registry_cache[key]
        # Use a service_role-equivalent: the registry is grant-readable by
        # anon/authenticated, so any pool connection works.
        async with db.acquire() as conn:
            row = await get_enabled(conn, schema_name, table_name)
        self._registry_cache[key] = row
        return row

    def _enqueue(self, conn: Connection, frame: Frame) -> bool:
        """Best-effort enqueue with drop-oldest on overflow.

        Returns ``True`` if the frame was queued, ``False`` if the
        connection is closed.
        """
        if conn.closed:
            return False
        q = conn.outbound
        if q.full():
            try:
                q.get_nowait()
                conn.dropped += 1
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(frame)
        except asyncio.QueueFull:
            conn.dropped += 1
            return False
        return True

    def _drop_presence_for(
        self,
        conn: Connection,
        topic: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """Strip presence entries owned by *conn* on *topic*.

        Returns a dict mapping presence key → metas removed, suitable for
        a ``presence_diff.leaves`` payload.  Caller must hold the lock.
        """
        leaves: dict[str, list[dict[str, Any]]] = {}
        bucket = self._presence.get(topic)
        if bucket is None:
            return leaves
        for key in list(bucket.keys()):
            entries = bucket[key]
            kept: list[tuple[int, dict[str, Any]]] = []
            removed: list[dict[str, Any]] = []
            for cid, meta in entries:
                if cid == conn.id:
                    removed.append(meta)
                else:
                    kept.append((cid, meta))
            if removed:
                leaves[key] = removed
            if kept:
                bucket[key] = kept
            else:
                bucket.pop(key, None)
        if not bucket:
            self._presence.pop(topic, None)
        return leaves

    def _emit_presence_diff_locked(
        self,
        topic: str,
        *,
        joins: dict[str, list[dict[str, Any]]],
        leaves: dict[str, list[dict[str, Any]]],
    ) -> None:
        peers = self._topics.get(topic)
        if not peers:
            return
        diff = PresenceDiff(joins=joins, leaves=leaves)
        frame = make_server_push(
            topic=topic,
            event=EVENT_PRESENCE_DIFF,
            payload=diff.model_dump(mode="json"),
        )
        for cid in peers:
            conn = self._connections.get(cid)
            if conn is None or conn.closed:
                continue
            self._enqueue(conn, frame)

    # -- listener loop ------------------------------------------------------

    async def _listener_loop(self) -> None:
        """Background task: keep a LISTEN connection alive, retrying on failure."""
        backoff = self._INITIAL_RECONNECT_BACKOFF_S
        while not self._stopping:
            try:
                listener = await asyncpg.connect(self._database_url)
                self._listener = listener
                await listener.add_listener(self._channel, self._on_notification)
                logger.info("realtime: LISTEN %s established", self._channel)
                backoff = self._INITIAL_RECONNECT_BACKOFF_S
                # asyncpg dispatches notifications on its own; we just need
                # to keep the connection open and notice when it dies.
                while not self._stopping and not listener.is_closed():
                    await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception(
                    "realtime: listener connection lost; reconnecting in %.1fs",
                    backoff,
                )
            finally:
                if self._listener is not None and not self._listener.is_closed():
                    with contextlib.suppress(Exception):
                        await self._listener.remove_listener(
                            self._channel, self._on_notification
                        )
                    with contextlib.suppress(Exception):
                        await self._listener.close()
                self._listener = None

            if self._stopping:
                return
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                raise
            backoff = min(backoff * 2.0, self._MAX_RECONNECT_BACKOFF_S)


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------


def _match_subscription_ids(
    sub: ChannelSubscription,
    data: PostgresChangesData,
) -> list[int]:
    """Return the subscription ids on *sub* whose filter matches *data*.

    Returns ``[]`` when no postgres_changes filter on this channel matches
    (the channel might still receive broadcasts, just not this row event).
    """
    matched: list[int] = []
    for resolved in sub.postgres_changes:
        spec = resolved.filter_spec
        if spec.schema_name != data.schema_name:
            continue
        if spec.table != data.table:
            continue
        if spec.event != "*" and spec.event != data.type:
            continue
        if not _row_matches_filter(resolved.parsed_filter, data):
            continue
        matched.append(resolved.id)
    return matched


def _row_matches_filter(
    parsed: ParsedFilter | None,
    data: PostgresChangesData,
) -> bool:
    if parsed is None:
        return True
    # For DELETE the row is in old_record; for INSERT/UPDATE, in record.
    row = data.record if data.type in ("INSERT", "UPDATE") else data.old_record
    if row is None:
        return False
    if isinstance(parsed, EqFilter):
        return _coerce(row.get(parsed.column)) == parsed.value
    if isinstance(parsed, InFilter):
        return _coerce(row.get(parsed.column)) in parsed.values
    return False


def _coerce(value: Any) -> str:
    """Normalize a Postgres column value to its string form for filter compare.

    Filters are always strings on the wire; we string-coerce the row value
    so ``id=eq.42`` matches an ``int8`` column without the user having to
    quote it.  ``None`` becomes the empty string sentinel which will not
    match any client-supplied filter (a client wanting to filter on NULL
    must use a server-side trigger instead — out of scope for v0.4).
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        # ISO-8601 with tz so equality with a JSON-encoded value matches.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    return str(value)


def _topic_for(conn: Connection, data: PostgresChangesData) -> str:
    """Pick the channel topic for a postgres_changes push.

    A connection may be subscribed to several topics that all match the
    same row event (e.g. one channel per room).  We re-walk the
    connection's subscriptions and pick the first whose
    ``postgres_changes`` matches — the broker's caller already guaranteed
    at least one match exists.
    """
    for sub in conn.subscriptions.values():
        if _match_subscription_ids(sub, data):
            return sub.topic
    # Should be unreachable; caller filters by exactly this predicate.
    return next(iter(conn.subscriptions.keys()), "realtime:unknown")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


_broker: Broker | None = None


def get_broker() -> Broker:
    """Return the process-wide broker, lazily constructed."""
    global _broker
    if _broker is None:
        _broker = Broker()
    return _broker


def reset_broker() -> None:
    """Drop the singleton (tests).  Caller is responsible for stopping it first."""
    global _broker
    _broker = None
