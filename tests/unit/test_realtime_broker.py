"""Unit tests for the in-process realtime Broker.

The broker is tested in isolation: the LISTEN loop is never started, the
``_registry_cache`` is pre-populated to bypass DB calls in
``_lookup_registry``, and ``_authorize`` is replaced with an
``AsyncMock`` or a custom coroutine where the test needs fine control.

No network, no database, no ASGI transport required.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from supython.realtime.broker import Broker, BrokerError
from supython.realtime.protocol import EVENT_BROADCAST, EVENT_POSTGRES_CHANGES, EVENT_PRESENCE_DIFF
from supython.realtime.schemas import EnabledTable, JoinConfig
from supython.realtime.topics import assign_subscription_ids

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def broker():
    """Fresh Broker instance with the listener loop *not* started."""
    b = Broker()
    yield b
    # Make sure state is clean even if the test raised.
    b._connections.clear()
    b._topics.clear()
    b._presence.clear()
    b._registry_cache.clear()


def _registry(
    *,
    schema: str = "public",
    table: str = "todos",
    pk: list[str] | None = None,
    owner_column: str | None = "user_id",
) -> EnabledTable:
    return EnabledTable(
        schema_name=schema,
        table_name=table,
        pk_columns=pk or ["id"],
        owner_column=owner_column,
        created_at=datetime.now(UTC),
    )


def _event(
    *,
    schema: str = "public",
    table: str = "todos",
    type_: str = "INSERT",
    record: dict | None = None,
    old_record: dict | None = None,
) -> dict:
    return {
        "schema": schema,
        "table": table,
        "type": type_,
        "commit_timestamp": "2026-01-01T00:00:00Z",
        "columns": [],
        "record": record,
        "old_record": old_record,
    }


async def _subscribe(
    broker: Broker,
    *,
    role: str = "authenticated",
    sub: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    topic: str = "realtime:room1",
    schema: str = "public",
    table: str = "todos",
    event: str = "*",
    filter_str: str | None = None,
    broadcast_self: bool = False,
    presence_key: str = "",
):
    """Register a connection and subscribe it to *topic*. Returns (conn, sub)."""
    conn = await broker.register(role=role, claims={"sub": sub, "role": role})
    spec: dict = {"event": event, "schema": schema, "table": table}
    if filter_str is not None:
        spec["filter"] = filter_str
    config = JoinConfig.model_validate({"postgres_changes": [spec]})
    resolved = assign_subscription_ids(config)
    channel_sub = await broker.subscribe(
        conn,
        topic=topic,
        join_ref="1",
        postgres_changes=resolved,
        broadcast_self=broadcast_self,
        presence_key=presence_key,
    )
    return conn, channel_sub


# ---------------------------------------------------------------------------
# Fan-out: topic / table matching
# ---------------------------------------------------------------------------


async def test_fanout_delivers_to_matching_subscriber(broker):
    """INSERT on the subscribed (schema, table) is forwarded to the connection."""
    broker._registry_cache[("public", "todos")] = _registry()
    broker._authorize = AsyncMock(return_value=True)

    conn, _ = await _subscribe(broker, schema="public", table="todos")
    await broker.fanout_change(_event(type_="INSERT", record={"id": 1}))

    assert not conn.outbound.empty()
    frame = conn.outbound.get_nowait()
    assert frame.event == EVENT_POSTGRES_CHANGES


async def test_fanout_ignores_different_table(broker):
    """A notification for a different table must not reach the subscriber."""
    broker._registry_cache[("public", "messages")] = _registry(table="messages")
    broker._authorize = AsyncMock(return_value=True)

    # subscribed to todos, notify for messages
    conn, _ = await _subscribe(broker, schema="public", table="todos")
    await broker.fanout_change(
        _event(schema="public", table="messages", type_="INSERT", record={"id": 1})
    )
    assert conn.outbound.empty()


async def test_fanout_ignores_table_absent_from_registry(broker):
    """pg_notify for a table not in realtime.enabled_tables is silently dropped."""
    broker._registry_cache[("public", "todos")] = None  # explicitly absent

    conn, _ = await _subscribe(broker, schema="public", table="todos")
    await broker.fanout_change(_event(type_="INSERT", record={"id": 1}))
    assert conn.outbound.empty()


async def test_fanout_ignores_wrong_schema(broker):
    """Subscriber on public.todos must not get events for auth.todos."""
    broker._registry_cache[("auth", "todos")] = _registry(schema="auth")
    broker._authorize = AsyncMock(return_value=True)

    conn, _ = await _subscribe(broker, schema="public", table="todos")
    # registry has no entry for public.todos
    broker._registry_cache[("public", "todos")] = None
    await broker.fanout_change(
        _event(schema="auth", table="todos", type_="INSERT", record={"id": 1})
    )
    assert conn.outbound.empty()


# ---------------------------------------------------------------------------
# Fan-out: RLS gate
# ---------------------------------------------------------------------------


async def test_rls_deny_blocks_delivery(broker):
    """_authorize returning False must suppress the frame."""
    broker._registry_cache[("public", "todos")] = _registry()
    broker._authorize = AsyncMock(return_value=False)

    conn, _ = await _subscribe(broker)
    await broker.fanout_change(_event(type_="INSERT", record={"id": 1}))
    assert conn.outbound.empty()


async def test_rls_allow_delivers_frame(broker):
    """_authorize returning True must deliver the frame."""
    broker._registry_cache[("public", "todos")] = _registry()
    broker._authorize = AsyncMock(return_value=True)

    conn, _ = await _subscribe(broker)
    await broker.fanout_change(_event(type_="INSERT", record={"id": 1}))
    assert not conn.outbound.empty()


async def test_service_role_bypasses_rls_probe(broker):
    """service_role connections receive every event without calling db.as_role."""
    broker._registry_cache[("public", "todos")] = _registry()

    with patch("supython.realtime.broker.db.as_role") as mock_as_role:
        conn, _ = await _subscribe(broker, role="service_role")
        await broker.fanout_change(_event(type_="INSERT", record={"id": 1}))
        mock_as_role.assert_not_called()

    assert not conn.outbound.empty()


async def test_expired_token_blocks_delivery(broker):
    """A connection whose JWT exp claim is in the past must not receive events."""
    broker._registry_cache[("public", "todos")] = _registry()

    conn = await broker.register(
        role="authenticated",
        claims={"sub": "u1", "role": "authenticated", "exp": 1},  # already expired
    )
    config = JoinConfig.model_validate(
        {"postgres_changes": [{"event": "*", "schema": "public", "table": "todos"}]}
    )
    resolved = assign_subscription_ids(config)
    await broker.subscribe(
        conn, topic="realtime:r", join_ref="1",
        postgres_changes=resolved, broadcast_self=False, presence_key="",
    )

    # _authorize is NOT mocked; the real path should short-circuit on expiry.
    await broker.fanout_change(_event(type_="INSERT", record={"id": 1}))
    assert conn.outbound.empty()


# ---------------------------------------------------------------------------
# Fan-out: filter matching
# ---------------------------------------------------------------------------


async def test_eq_filter_match_delivers(broker):
    broker._registry_cache[("public", "messages")] = _registry(table="messages")
    broker._authorize = AsyncMock(return_value=True)

    conn, _ = await _subscribe(
        broker, schema="public", table="messages", filter_str="room_id=eq.42"
    )
    await broker.fanout_change(
        _event(schema="public", table="messages", type_="INSERT", record={"id": 1, "room_id": 42})
    )
    assert not conn.outbound.empty()


async def test_eq_filter_no_match_skips(broker):
    broker._registry_cache[("public", "messages")] = _registry(table="messages")
    broker._authorize = AsyncMock(return_value=True)

    conn, _ = await _subscribe(
        broker, schema="public", table="messages", filter_str="room_id=eq.42"
    )
    await broker.fanout_change(
        _event(schema="public", table="messages", type_="INSERT", record={"id": 1, "room_id": 99})
    )
    assert conn.outbound.empty()


async def test_in_filter_match_delivers(broker):
    broker._registry_cache[("public", "messages")] = _registry(table="messages")
    broker._authorize = AsyncMock(return_value=True)

    conn, _ = await _subscribe(
        broker, schema="public", table="messages", filter_str="status=in.(active,pending)"
    )
    await broker.fanout_change(
        _event(
            schema="public", table="messages", type_="INSERT",
            record={"id": 1, "status": "active"},
        )
    )
    assert not conn.outbound.empty()


async def test_in_filter_no_match_skips(broker):
    broker._registry_cache[("public", "messages")] = _registry(table="messages")
    broker._authorize = AsyncMock(return_value=True)

    conn, _ = await _subscribe(
        broker, schema="public", table="messages", filter_str="status=in.(active,pending)"
    )
    await broker.fanout_change(
        _event(
            schema="public", table="messages", type_="INSERT",
            record={"id": 1, "status": "archived"},
        )
    )
    assert conn.outbound.empty()


async def test_wildcard_event_matches_all_dml(broker):
    """event='*' must match INSERT, UPDATE, and DELETE."""
    broker._registry_cache[("public", "todos")] = _registry()
    broker._authorize = AsyncMock(return_value=True)

    for dml, kwargs in [
        ("INSERT", {"record": {"id": 1}}),
        ("UPDATE", {"record": {"id": 1}, "old_record": {"id": 1}}),
        ("DELETE", {"old_record": {"id": 1}}),
    ]:
        # Authorize DELETE path: short-circuit on owner_column match
        if dml == "DELETE":
            broker._registry_cache[("public", "todos")] = _registry(owner_column=None)
            broker._authorize = AsyncMock(return_value=True)  # pragma: no cover (service_role mock)
            conn = await broker.register(role="service_role", claims={})
            config = JoinConfig.model_validate(
                {"postgres_changes": [{"event": "*", "schema": "public", "table": "todos"}]}
            )
            resolved = assign_subscription_ids(config)
            await broker.subscribe(
                conn, topic="realtime:r", join_ref="1",
                postgres_changes=resolved, broadcast_self=False, presence_key="",
            )
            await broker.fanout_change(_event(type_=dml, **kwargs))
            assert not conn.outbound.empty(), f"wildcard should match {dml}"
        else:
            conn, _ = await _subscribe(broker, event="*", sub=f"u-{dml}")
            await broker.fanout_change(_event(type_=dml, **kwargs))
            assert not conn.outbound.empty(), f"wildcard should match {dml}"
            # Drain for isolation.
            while not conn.outbound.empty():
                conn.outbound.get_nowait()


# ---------------------------------------------------------------------------
# Fan-out: DELETE owner-column path
# ---------------------------------------------------------------------------


async def test_delete_owner_column_match_delivers(broker):
    """DELETE fan-out succeeds when old_record[owner_column] == conn.claims['sub']."""
    user_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    broker._registry_cache[("public", "todos")] = _registry(owner_column="user_id")

    conn = await broker.register(
        role="authenticated",
        claims={"sub": user_id, "role": "authenticated"},
    )
    config = JoinConfig.model_validate(
        {"postgres_changes": [{"event": "*", "schema": "public", "table": "todos"}]}
    )
    resolved = assign_subscription_ids(config)
    await broker.subscribe(
        conn, topic="realtime:room1", join_ref="1",
        postgres_changes=resolved, broadcast_self=False, presence_key="",
    )

    await broker.fanout_change(
        _event(type_="DELETE", old_record={"id": 1, "user_id": user_id})
    )
    assert not conn.outbound.empty()


async def test_delete_owner_column_mismatch_withholds(broker):
    """DELETE must be withheld when old_record[owner_column] differs from sub."""
    user_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    user_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    broker._registry_cache[("public", "todos")] = _registry(owner_column="user_id")

    conn = await broker.register(
        role="authenticated",
        claims={"sub": user_a, "role": "authenticated"},
    )
    config = JoinConfig.model_validate(
        {"postgres_changes": [{"event": "*", "schema": "public", "table": "todos"}]}
    )
    resolved = assign_subscription_ids(config)
    await broker.subscribe(
        conn, topic="realtime:room1", join_ref="1",
        postgres_changes=resolved, broadcast_self=False, presence_key="",
    )

    await broker.fanout_change(
        _event(type_="DELETE", old_record={"id": 1, "user_id": user_b})
    )
    assert conn.outbound.empty()


async def test_delete_null_owner_column_withheld_from_authenticated(broker):
    """When owner_column is NULL in the registry, DELETEs skip non-service_role."""
    broker._registry_cache[("public", "todos")] = _registry(owner_column=None)

    conn, _ = await _subscribe(broker, role="authenticated")
    await broker.fanout_change(_event(type_="DELETE", old_record={"id": 1}))
    assert conn.outbound.empty()


async def test_delete_null_owner_column_delivered_to_service_role(broker):
    """service_role always receives DELETE even when owner_column is NULL."""
    broker._registry_cache[("public", "todos")] = _registry(owner_column=None)

    conn = await broker.register(role="service_role", claims={})
    config = JoinConfig.model_validate(
        {"postgres_changes": [{"event": "*", "schema": "public", "table": "todos"}]}
    )
    resolved = assign_subscription_ids(config)
    await broker.subscribe(
        conn, topic="realtime:room1", join_ref="1",
        postgres_changes=resolved, broadcast_self=False, presence_key="",
    )

    await broker.fanout_change(_event(type_="DELETE", old_record={"id": 1}))
    assert not conn.outbound.empty()


# ---------------------------------------------------------------------------
# Queue overflow
# ---------------------------------------------------------------------------


async def test_queue_overflow_drops_oldest_increments_counter(broker):
    """On overflow, the oldest frame is evicted and dropped counter increments."""
    broker._queue_size = 2  # tiny queue for this test
    broker._registry_cache[("public", "todos")] = _registry()
    broker._authorize = AsyncMock(return_value=True)

    conn, _ = await _subscribe(broker)

    # Fill the queue exactly.
    for i in range(2):
        await broker.fanout_change(_event(type_="INSERT", record={"id": i}))
    assert conn.outbound.qsize() == 2
    assert conn.dropped == 0

    # One more event → oldest is dropped.
    await broker.fanout_change(_event(type_="INSERT", record={"id": 99}))
    assert conn.outbound.qsize() == 2
    assert conn.dropped == 1

    # The newest (id=99) must still be in the queue.
    frames = [conn.outbound.get_nowait(), conn.outbound.get_nowait()]
    ids = [f.payload["data"]["record"]["id"] for f in frames]
    assert 99 in ids


# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------


async def test_broadcast_excludes_sender_by_default(broker):
    """Sender with broadcast_self=False must not receive its own broadcast."""
    conn1, _ = await _subscribe(broker, sub="u1", topic="realtime:chat")
    conn2, _ = await _subscribe(broker, sub="u2", topic="realtime:chat")

    delivered = broker.broadcast(
        topic="realtime:chat",
        event="msg",
        payload={"text": "hello"},
        sender_id=conn1.id,
    )
    assert delivered == 1
    assert conn1.outbound.empty()
    assert not conn2.outbound.empty()
    assert conn2.outbound.get_nowait().event == EVENT_BROADCAST


async def test_broadcast_includes_sender_when_self_true(broker):
    """Sender with broadcast_self=True must also receive the frame."""
    for sub_id in ("u1", "u2"):
        conn = await broker.register(role="authenticated", claims={"sub": sub_id})
        config = JoinConfig.model_validate({"postgres_changes": [], "broadcast": {"self": True}})
        resolved = assign_subscription_ids(config)
        await broker.subscribe(
            conn, topic="realtime:chat", join_ref="1",
            postgres_changes=resolved, broadcast_self=True, presence_key="",
        )

    conns = list(broker._connections.values())
    sender = conns[0]
    peer = conns[1]

    delivered = broker.broadcast(
        topic="realtime:chat", event="echo", payload={}, sender_id=sender.id
    )
    assert delivered == 2
    assert not sender.outbound.empty()
    assert not peer.outbound.empty()


async def test_rest_broadcast_reaches_all_subscribers(broker):
    """sender_id=None (REST broadcast) delivers to every subscriber."""
    conn1, _ = await _subscribe(broker, sub="u1", topic="realtime:chat")
    conn2, _ = await _subscribe(broker, sub="u2", topic="realtime:chat")

    delivered = broker.broadcast(
        topic="realtime:chat", event="ping", payload={}, sender_id=None
    )
    assert delivered == 2
    assert not conn1.outbound.empty()
    assert not conn2.outbound.empty()


async def test_broadcast_unknown_topic_returns_zero(broker):
    delivered = broker.broadcast(topic="realtime:nobody", event="x", payload={})
    assert delivered == 0


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------


async def test_track_presence_emits_diff_to_all_peers(broker):
    """Tracking presence sends presence_diff to every subscriber on the topic."""
    conn1, _ = await _subscribe(broker, sub="u1", topic="realtime:room1")
    conn2, _ = await _subscribe(broker, sub="u2", topic="realtime:room1")

    await broker.track_presence(conn1, topic="realtime:room1", meta={"name": "Alice"})

    for conn in (conn1, conn2):
        assert not conn.outbound.empty()
        frame = conn.outbound.get_nowait()
        assert frame.event == EVENT_PRESENCE_DIFF
        assert frame.payload["joins"]


async def test_presence_state_snapshot(broker):
    """presence_state() returns a point-in-time copy of the presence map."""
    conn, _ = await _subscribe(broker, sub="u1", topic="realtime:room1")
    await broker.track_presence(conn, topic="realtime:room1", meta={"name": "Alice"})
    # Drain the diff.
    conn.outbound.get_nowait()

    state = broker.presence_state("realtime:room1")
    all_metas = [m for metas in state.values() for m in metas]
    assert any(m.get("name") == "Alice" for m in all_metas)


async def test_push_presence_state_enqueues_frame(broker):
    """push_presence_state() enqueues a presence_state frame to the target conn."""
    conn, _ = await _subscribe(broker, sub="u1", topic="realtime:room1")
    await broker.push_presence_state(conn, "realtime:room1")
    assert not conn.outbound.empty()
    frame = conn.outbound.get_nowait()
    assert frame.event == "presence_state"


async def test_unregister_emits_presence_diff_to_peers(broker):
    """Unregistering a presence-tracked connection emits presence_diff (leaves)."""
    conn1, _ = await _subscribe(broker, sub="u1", topic="realtime:room1")
    conn2, _ = await _subscribe(broker, sub="u2", topic="realtime:room1")

    await broker.track_presence(conn1, topic="realtime:room1", meta={"status": "online"})
    # Drain join diffs.
    conn1.outbound.get_nowait()
    conn2.outbound.get_nowait()

    await broker.unregister(conn1)

    assert not conn2.outbound.empty()
    frame = conn2.outbound.get_nowait()
    assert frame.event == EVENT_PRESENCE_DIFF
    assert frame.payload["leaves"]


# ---------------------------------------------------------------------------
# RLS isolation — DoD scenario
# ---------------------------------------------------------------------------


async def test_rls_isolation_only_authorized_subscriber_receives(broker):
    """User A receives the event; User B (different owner) does not.

    Covers the DoD requirement: per-room RLS scoping ensures a subscriber
    whose RLS query returns no row never receives the event.
    """
    user_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    user_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    broker._registry_cache[("public", "todos")] = _registry()

    # _authorize returns True only for user_a's connection.
    async def selective_authorize(conn, data, registry):
        return conn.claims.get("sub") == user_a

    broker._authorize = selective_authorize

    conn_a, _ = await _subscribe(broker, sub=user_a, topic="realtime:room1")
    conn_b, _ = await _subscribe(broker, sub=user_b, topic="realtime:room1")

    await broker.fanout_change(_event(type_="INSERT", record={"id": 1, "user_id": user_a}))

    assert not conn_a.outbound.empty(), "User A should receive the event"
    assert conn_b.outbound.empty(), "User B must not receive user A's event"


async def test_two_topics_same_notification_only_matching_subscriber_receives(broker):
    """Two subscribers on different topics: only the one whose config matches gets the frame."""
    broker._registry_cache[("public", "messages")] = _registry(table="messages")
    broker._authorize = AsyncMock(return_value=True)

    # conn1 is on "realtime:room1" subscribed to room_id=eq.1
    conn1, _ = await _subscribe(
        broker, sub="u1", topic="realtime:room1",
        schema="public", table="messages", filter_str="room_id=eq.1",
    )
    # conn2 is on "realtime:room2" subscribed to room_id=eq.2
    conn2, _ = await _subscribe(
        broker, sub="u2", topic="realtime:room2",
        schema="public", table="messages", filter_str="room_id=eq.2",
    )

    await broker.fanout_change(
        _event(
            schema="public", table="messages", type_="INSERT",
            record={"id": 1, "room_id": 1},
        )
    )

    assert not conn1.outbound.empty(), "conn1 (room_id=eq.1) should receive the event"
    assert conn2.outbound.empty(), "conn2 (room_id=eq.2) must not receive event for room 1"


# ---------------------------------------------------------------------------
# RLS probe path — exercises the real _authorize for authenticated users
# ---------------------------------------------------------------------------


async def test_authorize_invokes_db_as_role_and_rls_check(broker):
    """For an authenticated subscriber, the broker probes RLS via db.as_role + rls_check.

    The earlier RLS tests stub ``_authorize`` wholesale; this one keeps the
    real implementation and verifies that ``db.as_role`` opens a role-scoped
    connection and ``rls_check`` is called with the schema, table, and PK
    extracted from the registry + the row's ``record``.
    """
    broker._registry_cache[("public", "todos")] = _registry(
        pk=["id"], owner_column="user_id"
    )

    scoped_conn = MagicMock(name="scoped_asyncpg_conn")
    captured: dict = {}

    @asynccontextmanager
    async def fake_as_role(role, claims):
        captured["role"] = role
        captured["claims"] = claims
        yield scoped_conn

    rls_mock = AsyncMock(return_value=True)
    with (
        patch("supython.realtime.broker.db.as_role", new=fake_as_role),
        patch("supython.realtime.broker.rls_check", new=rls_mock),
    ):
        conn, _ = await _subscribe(broker, role="authenticated", sub="user-42")
        await broker.fanout_change(
            _event(type_="INSERT", record={"id": 7, "user_id": "user-42"})
        )

    assert captured["role"] == "authenticated"
    assert captured["claims"]["sub"] == "user-42"
    assert rls_mock.await_count == 1
    call_kwargs = rls_mock.await_args.kwargs
    assert call_kwargs["schema_name"] == "public"
    assert call_kwargs["table_name"] == "todos"
    assert call_kwargs["pk_columns"] == ["id"]
    assert call_kwargs["pk_values"] == [7]
    assert call_kwargs["timeout"] == broker._rls_timeout
    assert not conn.outbound.empty(), "rls_check returned True; frame must be delivered"


async def test_authorize_rls_check_false_suppresses_delivery(broker):
    """When rls_check returns False, the frame is dropped before enqueue."""
    broker._registry_cache[("public", "todos")] = _registry(
        pk=["id"], owner_column="user_id"
    )

    @asynccontextmanager
    async def fake_as_role(role, claims):
        yield MagicMock()

    with (
        patch("supython.realtime.broker.db.as_role", new=fake_as_role),
        patch(
            "supython.realtime.broker.rls_check",
            new=AsyncMock(return_value=False),
        ),
    ):
        conn, _ = await _subscribe(broker, role="authenticated")
        await broker.fanout_change(_event(type_="INSERT", record={"id": 1}))
    assert conn.outbound.empty()


async def test_authorize_drops_event_when_record_missing_pk(broker):
    """A notify whose record lacks a registered PK column is logged & dropped."""
    broker._registry_cache[("public", "todos")] = _registry(
        pk=["id"], owner_column=None
    )

    rls_mock = AsyncMock(return_value=True)
    with patch("supython.realtime.broker.rls_check", new=rls_mock):
        conn, _ = await _subscribe(broker, role="authenticated")
        # record is missing the 'id' PK column.
        await broker.fanout_change(_event(type_="INSERT", record={"name": "x"}))

    assert conn.outbound.empty()
    rls_mock.assert_not_awaited()


async def test_authorize_returns_false_when_role_not_in_allowed_roles(broker):
    """If db.as_role raises ValueError (role not allowed), authorize returns False."""
    broker._registry_cache[("public", "todos")] = _registry(pk=["id"])

    @asynccontextmanager
    async def raising_as_role(role, claims):
        raise ValueError(f"role {role!r} not allowed")
        yield  # pragma: no cover  (unreachable; required to make this an async gen)

    with patch("supython.realtime.broker.db.as_role", new=raising_as_role):
        # Use a non-service_role role string that the broker won't short-circuit.
        conn = await broker.register(
            role="ghost",
            claims={"sub": "u1", "role": "ghost"},
        )
        config = JoinConfig.model_validate(
            {"postgres_changes": [{"event": "*", "schema": "public", "table": "todos"}]}
        )
        resolved = assign_subscription_ids(config)
        await broker.subscribe(
            conn, topic="realtime:r", join_ref="1",
            postgres_changes=resolved, broadcast_self=False, presence_key="",
        )
        await broker.fanout_change(_event(type_="INSERT", record={"id": 1}))

    assert conn.outbound.empty()


# ---------------------------------------------------------------------------
# _lookup_registry — cache behaviour
# ---------------------------------------------------------------------------


async def test_lookup_registry_caches_on_first_miss(broker):
    """A cold lookup hits the DB; a warm one is served from the cache."""
    fake_conn = MagicMock(name="db_conn")

    @asynccontextmanager
    async def fake_acquire():
        yield fake_conn

    fake_row = _registry(schema="public", table="todos")
    get_enabled_mock = AsyncMock(return_value=fake_row)

    with (
        patch("supython.realtime.broker.db.acquire", new=fake_acquire),
        patch("supython.realtime.broker.get_enabled", new=get_enabled_mock),
    ):
        result1 = await broker._lookup_registry("public", "todos")
        result2 = await broker._lookup_registry("public", "todos")

    assert result1 is fake_row
    assert result2 is fake_row
    assert get_enabled_mock.await_count == 1, "Second lookup must be served from cache"
    assert broker._registry_cache[("public", "todos")] is fake_row


async def test_lookup_registry_caches_negative_lookup(broker):
    """A table absent from realtime.enabled_tables is cached as None.

    Without negative caching the broker would re-query the registry on
    every notify for an unregistered table, which is wasteful.
    """
    fake_conn = MagicMock(name="db_conn")

    @asynccontextmanager
    async def fake_acquire():
        yield fake_conn

    get_enabled_mock = AsyncMock(return_value=None)
    with (
        patch("supython.realtime.broker.db.acquire", new=fake_acquire),
        patch("supython.realtime.broker.get_enabled", new=get_enabled_mock),
    ):
        result1 = await broker._lookup_registry("public", "ghost")
        result2 = await broker._lookup_registry("public", "ghost")

    assert result1 is None
    assert result2 is None
    assert get_enabled_mock.await_count == 1
    assert ("public", "ghost") in broker._registry_cache
    assert broker._registry_cache[("public", "ghost")] is None


async def test_fanout_triggers_lookup_registry_on_cache_miss(broker):
    """An incoming notify for an unseen table fetches the registry then dispatches."""
    fake_conn = MagicMock(name="db_conn")

    @asynccontextmanager
    async def fake_acquire():
        yield fake_conn

    fake_row = _registry(schema="public", table="messages", pk=["id"])
    get_enabled_mock = AsyncMock(return_value=fake_row)
    broker._authorize = AsyncMock(return_value=True)

    with (
        patch("supython.realtime.broker.db.acquire", new=fake_acquire),
        patch("supython.realtime.broker.get_enabled", new=get_enabled_mock),
    ):
        conn, _ = await _subscribe(broker, schema="public", table="messages")
        await broker.fanout_change(
            _event(schema="public", table="messages", type_="INSERT", record={"id": 1})
        )

    assert get_enabled_mock.await_count == 1
    assert not conn.outbound.empty(), "Expected fanout to deliver after registry fetch"


# ---------------------------------------------------------------------------
# _listener_loop — connection lifecycle & reconnect
# ---------------------------------------------------------------------------


def _fake_listener() -> MagicMock:
    """Build an asyncpg-Connection-shaped mock for the LISTEN loop."""
    listener = MagicMock(name="asyncpg_listener")
    listener.add_listener = AsyncMock()
    listener.remove_listener = AsyncMock()
    listener.close = AsyncMock()
    listener.is_closed = MagicMock(return_value=False)
    return listener


async def test_listener_loop_attaches_listener_on_start(broker):
    """start() opens an asyncpg connection and registers the LISTEN callback."""
    listener = _fake_listener()
    with patch(
        "supython.realtime.broker.asyncpg.connect",
        new=AsyncMock(return_value=listener),
    ) as connect_mock:
        await broker.start()
        # Yield control until the listener task has installed the callback.
        for _ in range(100):
            if listener.add_listener.await_count >= 1:
                break
            await asyncio.sleep(0.01)
        try:
            assert connect_mock.await_count >= 1
            listener.add_listener.assert_awaited_with(
                broker._channel, broker._on_notification
            )
            assert broker._listener is listener
        finally:
            await broker.stop()

    listener.remove_listener.assert_awaited()
    listener.close.assert_awaited()
    assert broker._listener is None
    assert broker._listener_task is None


async def test_listener_loop_reconnects_after_failure(broker):
    """A failed asyncpg.connect is followed by a retry with backoff."""
    # Tighten the backoff so the test finishes in well under a second.
    broker._INITIAL_RECONNECT_BACKOFF_S = 0.01

    listener = _fake_listener()
    call_count = 0

    async def flaky_connect(_url):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("simulated connection failure")
        return listener

    with patch("supython.realtime.broker.asyncpg.connect", new=flaky_connect):
        await broker.start()
        try:
            for _ in range(200):
                if broker._listener is listener:
                    break
                await asyncio.sleep(0.01)
            assert call_count >= 2, "Expected at least one reconnect attempt"
            assert broker._listener is listener
            listener.add_listener.assert_awaited_with(
                broker._channel, broker._on_notification
            )
        finally:
            await broker.stop()


async def test_listener_loop_stops_cleanly_when_started_then_stopped(broker):
    """stop() cancels the listener task and tears down all in-process state."""
    listener = _fake_listener()
    with patch(
        "supython.realtime.broker.asyncpg.connect",
        new=AsyncMock(return_value=listener),
    ):
        await broker.start()
        for _ in range(100):
            if broker._listener is listener:
                break
            await asyncio.sleep(0.01)

        # Seed some state so we can verify stop() drains it.
        broker._connections[999] = MagicMock()
        broker._topics["realtime:x"] = {999}
        broker._registry_cache[("public", "todos")] = _registry()

        await broker.stop()

    assert broker._connections == {}
    assert broker._topics == {}
    assert broker._registry_cache == {}
    assert broker._listener is None


# ---------------------------------------------------------------------------
# Connection cap (broker-level)
# ---------------------------------------------------------------------------


async def test_register_raises_broker_error_when_cap_reached(broker):
    """register() rejects new connections once realtime_max_connections is hit."""
    broker._max_connections = 2
    await broker.register(role="anon", claims={})
    await broker.register(role="anon", claims={})

    with pytest.raises(BrokerError, match="connection cap reached"):
        await broker.register(role="anon", claims={})

    # Cap is restored after one frees up.
    conn = next(iter(broker._connections.values()))
    await broker.unregister(conn)
    # Should now succeed.
    await broker.register(role="anon", claims={})
