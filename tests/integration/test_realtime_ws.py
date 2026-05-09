"""E2E WebSocket tests for the realtime module.

Uses ``starlette.testclient.TestClient.websocket_connect`` to exercise the
full Phoenix-channels protocol stack against the real ASGI app running in a
background thread.  The broker singleton is started and stopped by the
TestClient lifespan for each test block.

Test functions are ``async`` so they can use the session-scoped fixtures
(``app``, ``pool``) established in ``conftest.py``; calling synchronous
``TestClient`` code from an ``async`` function is safe because TestClient
manages its own thread + event loop and does not interact with the outer
asyncio loop.
"""

import asyncio
import uuid

import asyncpg
import pytest
import pytest_asyncio
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from supython.settings import Settings, get_settings
from supython.tokens import issue_access_token

# ---------------------------------------------------------------------------
# Skip when Postgres is not reachable (TestClient starts the broker which
# needs the DB for the LISTEN connection, though it handles failures
# gracefully — we skip anyway so tests are not flaky in CI without a DB).
# ---------------------------------------------------------------------------


async def _db_reachable() -> bool:
    s = get_settings()
    try:
        conn = await asyncio.wait_for(asyncpg.connect(s.database_url), timeout=3.0)
        await conn.close()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture(scope="module", autouse=True)
async def require_db():
    if not await _db_reachable():
        pytest.skip("Postgres not reachable — run `supython up` first")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _token(*, role: str = "authenticated", user_id: uuid.UUID | None = None) -> str:
    uid = user_id or uuid.uuid4()
    tok, _ = issue_access_token(uid, f"user-{uid}@test.com", role)
    return tok


def _join_frame(
    topic: str,
    *,
    join_ref: str = "1",
    ref: str = "1",
    config: dict | None = None,
    access_token: str | None = None,
) -> list:
    payload: dict = {"config": config or {}}
    if access_token:
        payload["access_token"] = access_token
    return [join_ref, ref, topic, "phx_join", payload]


def _heartbeat(ref: str = "1") -> list:
    return [None, ref, "phoenix", "heartbeat", {}]


def _leave_frame(topic: str, ref: str = "99") -> list:
    return [None, ref, topic, "phx_leave", {}]


def _broadcast_frame(topic: str, event: str, payload: dict, ref: str = "2") -> list:
    return [
        None, ref, topic, "broadcast",
        {"type": "broadcast", "event": event, "payload": payload},
    ]


def _recv_until(ws, event: str, max_frames: int = 10) -> list:
    """Receive frames until one carrying *event* arrives."""
    for _ in range(max_frames):
        frame = ws.receive_json()
        if frame[3] == event:
            return frame
    raise AssertionError(f"Did not receive event {event!r} within {max_frames} frames")


# ---------------------------------------------------------------------------
# Connection-level: heartbeat
# ---------------------------------------------------------------------------


async def test_heartbeat_gets_phx_reply_ok(app):
    """Heartbeat on the 'phoenix' topic receives a phx_reply with status=ok."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(_heartbeat("42"))
        reply = ws.receive_json()
        assert reply[3] == "phx_reply", f"Expected phx_reply, got {reply}"
        assert reply[1] == "42", "ref must be echoed"
        assert reply[2] == "phoenix"
        assert reply[4]["status"] == "ok"


# ---------------------------------------------------------------------------
# Channel: phx_join
# ---------------------------------------------------------------------------


async def test_phx_join_returns_ack_with_subscription_ids(app):
    """phx_join yields phx_reply with postgres_changes subscription ids."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(
            _join_frame(
                "realtime:chat",
                config={
                    "postgres_changes": [
                        {"event": "INSERT", "schema": "public", "table": "messages"},
                        {"event": "UPDATE", "schema": "public", "table": "messages"},
                    ],
                    "broadcast": {"self": False},
                    "presence": {"key": "alice"},
                },
            )
        )
        # First server frame: join ack.
        ack = ws.receive_json()
        assert ack[3] == "phx_reply"
        assert ack[0] == "1"   # join_ref echoed
        assert ack[4]["status"] == "ok"
        subs = ack[4]["response"]["postgres_changes"]
        assert len(subs) == 2
        assert all(isinstance(s["id"], int) for s in subs)
        assert subs[0]["schema"] == "public"
        assert subs[0]["table"] == "messages"
        assert subs[0]["event"] == "INSERT"

        # Second server frame: presence_state.
        ps = ws.receive_json()
        assert ps[3] == "presence_state"
        assert isinstance(ps[4], dict)


async def test_phx_join_invalid_topic_returns_error(app):
    """Joining a topic that doesn't match the realtime:<name> grammar gets an error reply."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(["1", "1", "not-a-realtime-topic", "phx_join", {}])
        reply = ws.receive_json()
        assert reply[3] == "phx_reply"
        assert reply[4]["status"] == "error"


async def test_phx_join_bad_filter_returns_error(app):
    """A malformed postgres_changes filter is rejected at join time."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(
            _join_frame(
                "realtime:chat",
                config={
                    "postgres_changes": [
                        {
                            "event": "INSERT",
                            "schema": "public",
                            "table": "messages",
                            "filter": "totally_invalid!!",
                        }
                    ]
                },
            )
        )
        reply = ws.receive_json()
        assert reply[3] == "phx_reply"
        assert reply[4]["status"] == "error"


async def test_phx_join_without_config_succeeds(app):
    """A bare phx_join with no config (no postgres_changes) is valid."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(["1", "1", "realtime:chat", "phx_join", {}])
        ack = ws.receive_json()
        assert ack[3] == "phx_reply"
        assert ack[4]["status"] == "ok"
        assert ack[4]["response"]["postgres_changes"] == []


# ---------------------------------------------------------------------------
# Channel: phx_leave
# ---------------------------------------------------------------------------


async def test_phx_leave_sends_ack_then_phx_close(app):
    """phx_leave receives phx_reply ok followed by phx_close."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(_join_frame("realtime:chat"))
        _recv_until(ws, "phx_reply")
        _recv_until(ws, "presence_state")

        ws.send_json(_leave_frame("realtime:chat", ref="5"))
        ack = _recv_until(ws, "phx_reply")
        assert ack[4]["status"] == "ok"
        assert ack[1] == "5"

        close_frame = _recv_until(ws, "phx_close")
        assert close_frame[2] == "realtime:chat"


# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------


async def test_broadcast_peer_receives_frame(app):
    """Client 1 broadcasts; client 2 (peer) receives the broadcast frame."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws1:
        ws1.send_json(
            _join_frame("realtime:chat", join_ref="1", ref="1",
                        config={"broadcast": {"self": False}})
        )
        _recv_until(ws1, "phx_reply")
        _recv_until(ws1, "presence_state")

        with client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws2:
            ws2.send_json(
                _join_frame("realtime:chat", join_ref="2", ref="2",
                            config={"broadcast": {"self": False}})
            )
            _recv_until(ws2, "phx_reply")
            _recv_until(ws2, "presence_state")

            ws1.send_json(_broadcast_frame("realtime:chat", "message", {"text": "hello"}, ref="3"))
            # ws1 receives the ack (ref is set).
            ack = _recv_until(ws1, "phx_reply")
            assert ack[4]["status"] == "ok"

            # ws2 receives the broadcast.
            bcast = _recv_until(ws2, "broadcast")
            assert bcast[4]["event"] == "message"
            assert bcast[4]["payload"]["text"] == "hello"


async def test_broadcast_sender_not_in_recipients_by_default(app):
    """With broadcast.self=false (default) the sender does not receive its own broadcast."""
    with (
        TestClient(app) as client,
        client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws1,
        client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws2,
    ):
        for ws, jr in [(ws1, "1"), (ws2, "2")]:
            ws.send_json(
                _join_frame("realtime:chat", join_ref=jr, ref=jr,
                            config={"broadcast": {"self": False}})
            )
            _recv_until(ws, "phx_reply")
            _recv_until(ws, "presence_state")

        # ws1 sends broadcast without a ref so no ack is returned.
        ws1.send_json(
            [None, None, "realtime:chat", "broadcast",
             {"type": "broadcast", "event": "msg", "payload": {"x": 1}}]
        )
        # ws2 must receive the broadcast.
        bcast = _recv_until(ws2, "broadcast")
        assert bcast[4]["event"] == "msg"

        # ws1's outbound queue should have nothing (no ack, no self-echo).
        # We verify by sending a heartbeat and making sure the next frame is the ack.
        ws1.send_json(_heartbeat("hb"))
        hb_ack = ws1.receive_json()
        assert hb_ack[3] == "phx_reply"
        assert hb_ack[2] == "phoenix"


async def test_broadcast_sender_included_when_self_true(app):
    """With broadcast.self=true the sender also receives its own broadcast."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws1:
        ws1.send_json(
            _join_frame("realtime:chat", join_ref="1", ref="1",
                        config={"broadcast": {"self": True}})
        )
        _recv_until(ws1, "phx_reply")
        _recv_until(ws1, "presence_state")

        ws1.send_json(_broadcast_frame("realtime:chat", "echo", {"d": "ping"}, ref="2"))
        # Both the ack (phx_reply) and the self-echo (broadcast) should arrive.
        events_seen = set()
        for _ in range(2):
            frame = ws1.receive_json()
            events_seen.add(frame[3])
        assert "phx_reply" in events_seen
        assert "broadcast" in events_seen


async def test_broadcast_not_joined_returns_error(app):
    """Broadcasting on a channel the client hasn't joined returns a phx_reply error."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(_broadcast_frame("realtime:unjoined", "msg", {}, ref="1"))
        reply = _recv_until(ws, "phx_reply")
        assert reply[4]["status"] == "error"
        assert "not joined" in reply[4]["response"].get("reason", "")


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------


async def test_presence_state_sent_immediately_on_join(app):
    """Presence state frame is pushed right after the join ack."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(_join_frame("realtime:proom"))
        _recv_until(ws, "phx_reply")
        ps = _recv_until(ws, "presence_state")
        assert isinstance(ps[4], dict)


async def test_presence_diff_on_track(app):
    """Tracking presence causes a presence_diff to reach all peers on the topic."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws1:
        ws1.send_json(
            _join_frame("realtime:proom", join_ref="1", ref="1",
                        config={"presence": {"key": "alice"}})
        )
        _recv_until(ws1, "phx_reply")
        _recv_until(ws1, "presence_state")

        with client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws2:
            ws2.send_json(
                _join_frame("realtime:proom", join_ref="2", ref="2",
                            config={"presence": {"key": "bob"}})
            )
            _recv_until(ws2, "phx_reply")
            _recv_until(ws2, "presence_state")

            # ws2 tracks presence.
            ws2.send_json(
                ["2", "3", "realtime:proom", "presence",
                 {"type": "presence", "event": "track", "payload": {"status": "online"}}]
            )
            _recv_until(ws2, "phx_reply")  # ack for track

            # ws1 must receive a presence_diff containing ws2's join.
            diff = _recv_until(ws1, "presence_diff")
            assert diff[4]["joins"], "Expected non-empty joins in presence_diff"


async def test_presence_state_includes_previously_tracked_peers(app):
    """A client joining after others have tracked presence sees the current state."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws1:
        ws1.send_json(
            _join_frame("realtime:proom2", join_ref="1", ref="1",
                        config={"presence": {"key": "alice"}})
        )
        _recv_until(ws1, "phx_reply")
        _recv_until(ws1, "presence_state")

        ws1.send_json(
            ["1", "2", "realtime:proom2", "presence",
             {"type": "presence", "event": "track", "payload": {"name": "Alice"}}]
        )
        _recv_until(ws1, "phx_reply")   # ack
        _recv_until(ws1, "presence_diff")  # self-diff

        # Second client joins; its presence_state must include Alice.
        with client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws2:
            ws2.send_json(
                _join_frame("realtime:proom2", join_ref="2", ref="2",
                            config={"presence": {"key": "bob"}})
            )
            _recv_until(ws2, "phx_reply")
            ps = _recv_until(ws2, "presence_state")
            # Alice should be in the state.
            all_metas = [m for metas in ps[4].values() for m in metas]
            assert any(m.get("name") == "Alice" for m in all_metas), (
                f"Expected Alice in presence_state, got {ps[4]}"
            )


async def test_presence_diff_on_leave(app):
    """When a tracked client leaves the channel, peers see a presence_diff with leaves."""
    with (
        TestClient(app) as client,
        client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws1,
        client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws2,
    ):
        topic = "realtime:leaveroom"

        # Both clients join.
        ws1.send_json(
            _join_frame(topic, join_ref="1", ref="1",
                        config={"presence": {"key": "alice"}})
        )
        ws2.send_json(
            _join_frame(topic, join_ref="2", ref="2",
                        config={"presence": {"key": "bob"}})
        )
        _recv_until(ws1, "phx_reply")
        _recv_until(ws1, "presence_state")
        _recv_until(ws2, "phx_reply")
        _recv_until(ws2, "presence_state")

        # ws1 tracks presence.
        ws1.send_json(
            ["1", "3", topic, "presence",
             {"type": "presence", "event": "track", "payload": {"name": "Alice"}}]
        )
        _recv_until(ws1, "phx_reply")
        _recv_until(ws1, "presence_diff")   # self-diff
        _recv_until(ws2, "presence_diff")   # ws2 sees Alice join

        # ws1 leaves the channel explicitly.
        ws1.send_json(_leave_frame(topic, ref="4"))
        _recv_until(ws1, "phx_reply")
        _recv_until(ws1, "phx_close")

        # ws2 must see a presence_diff with leaves.
        diff = _recv_until(ws2, "presence_diff")
        assert diff[4]["leaves"], (
            f"Expected non-empty leaves in presence_diff, got {diff[4]}"
        )


# ---------------------------------------------------------------------------
# Per-room scoping: clients on different channels are isolated
# ---------------------------------------------------------------------------


async def test_broadcast_channel_isolation(app):
    """Clients on different channels must not receive each other's broadcasts.

    This is the WS-level equivalent of the DoD 'per-room RLS scoping' check:
    a subscriber not joined to a channel never receives events on it.  The
    deeper postgres_changes / RLS fanout variant is covered exhaustively in
    ``test_realtime_broker.py::test_rls_isolation_only_authorized_subscriber_receives``.
    """
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws_a:
        # ws_a joins channel "room-1"
        ws_a.send_json(
            _join_frame("realtime:room-1", join_ref="1", ref="1",
                        config={"broadcast": {"self": False}})
        )
        _recv_until(ws_a, "phx_reply")
        _recv_until(ws_a, "presence_state")

        with client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws_b:
            # ws_b joins a DIFFERENT channel "room-2"
            ws_b.send_json(
                _join_frame("realtime:room-2", join_ref="2", ref="2",
                            config={"broadcast": {"self": False}})
            )
            _recv_until(ws_b, "phx_reply")
            _recv_until(ws_b, "presence_state")

            # ws_a broadcasts on room-1.
            ws_a.send_json(
                _broadcast_frame("realtime:room-1", "secret", {"data": "private"}, ref="3")
            )
            # ws_a gets the ack.
            _recv_until(ws_a, "phx_reply")

            # ws_b must NOT receive the broadcast — it's on a different channel.
            # Verify by sending ws_b a heartbeat; the next frame ws_b sees must be
            # the heartbeat ack, not the broadcast from room-1.
            ws_b.send_json(_heartbeat("hb"))
            next_b = ws_b.receive_json()
            assert next_b[3] != "broadcast", (
                f"ws_b (room-2) must not receive room-1 broadcast; got event={next_b[3]!r}"
            )


async def test_two_subscribers_same_channel_both_receive_rest_broadcast(app, client):
    """REST-initiated broadcast is delivered to both subscribers on the channel.

    Uses the POST /realtime/v1/broadcast/{topic} endpoint (service-role) to push
    a broadcast frame without holding a WebSocket, then verifies both WS clients
    receive it.
    """
    import httpx

    svc_token = _token(role="service_role")

    with (
        TestClient(app) as ws_client,
        ws_client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws_a,
        ws_client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws_b,
    ):
        ws_a.send_json(_join_frame("realtime:shared", join_ref="1", ref="1"))
        _recv_until(ws_a, "phx_reply")
        _recv_until(ws_a, "presence_state")

        ws_b.send_json(_join_frame("realtime:shared", join_ref="2", ref="2"))
        _recv_until(ws_b, "phx_reply")
        _recv_until(ws_b, "presence_state")

        # Fire REST broadcast via the app's HTTP interface.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as http:
            resp = await http.post(
                "/realtime/v1/broadcast/realtime:shared",
                json={"event": "server-push", "payload": {"msg": "hi all"}},
                headers={"Authorization": f"Bearer {svc_token}"},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["delivered"] == 2

        # Both WS clients must receive the broadcast.
        bcast_a = _recv_until(ws_a, "broadcast")
        bcast_b = _recv_until(ws_b, "broadcast")
        assert bcast_a[4]["event"] == "server-push"
        assert bcast_b[4]["payload"]["msg"] == "hi all"


# ---------------------------------------------------------------------------
# postgres_changes — full E2E from SQL trigger to WS frame
# ---------------------------------------------------------------------------


_E2E_TABLE = "public.rt_ws_e2e"
_E2E_SCHEMA = "public"
_E2E_TNAME = "rt_ws_e2e"


@pytest_asyncio.fixture
async def e2e_table(pool: asyncpg.Pool):
    """Create + realtime-enable a dedicated test table; drop it after the test."""
    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            create table if not exists {_E2E_TABLE} (
                id       serial primary key,
                owner_id uuid,
                body     text not null default ''
            )
            """
        )
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute('set local role "service_role"')
        await conn.execute(
            "select realtime.enable($1::regclass, $2)", _E2E_TABLE, "owner_id"
        )
    try:
        yield _E2E_TABLE
    finally:
        async with pool.acquire() as conn:
            await conn.execute(f"drop trigger if exists realtime_notify on {_E2E_TABLE}")
            await conn.execute(
                "delete from realtime.enabled_tables "
                "where schema_name = $1 and table_name = $2",
                _E2E_SCHEMA, _E2E_TNAME,
            )
            await conn.execute(f"drop table if exists {_E2E_TABLE}")


async def test_postgres_changes_insert_delivers_frame_to_subscriber(
    app, pool: asyncpg.Pool, e2e_table
):
    """SQL INSERT on an enabled table is fanned out as a postgres_changes frame.

    Closes the loop end-to-end:
      enable → trigger fires → pg_notify → broker LISTEN → WS frame.

    Uses ``service_role`` so the broker's RLS short-circuit applies and the
    test does not depend on a particular RLS policy on the test table.

    Cross-loop note:
      ``conftest.pool`` is created in the session event loop, but the broker's
      listener task runs inside ``TestClient``'s private thread + loop. If the
      listener tried to call ``db.acquire()`` on the session-loop pool from
      its own loop, the acquire would hang and the watchdog would eventually
      close the socket with code 1001. To keep the listener on its own loop
      we pre-populate ``broker._registry_cache`` so ``_lookup_registry`` is a
      pure dict hit and never touches the pool.
    """
    from datetime import UTC, datetime

    from supython.realtime.broker import get_broker
    from supython.realtime.schemas import EnabledTable

    svc_token = _token(role="service_role")

    with TestClient(app) as client:
        broker = get_broker()

        # Bypass the cross-loop db.acquire() inside _lookup_registry.
        broker._registry_cache[(_E2E_SCHEMA, _E2E_TNAME)] = EnabledTable(
            schema_name=_E2E_SCHEMA,
            table_name=_E2E_TNAME,
            pk_columns=["id"],
            owner_column="owner_id",
            created_at=datetime.now(UTC),
        )

        # Wait until the broker has attached the LISTEN callback. pg_notify
        # is fire-and-forget: a notify sent before LISTEN is in place is lost,
        # which would manifest as a heartbeat timeout 30 s later.
        for _ in range(50):
            listener = broker._listener
            if listener is not None and not listener.is_closed():
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("Broker listener did not attach within 5s")

        with client.websocket_connect(
            f"/realtime/v1/websocket?vsn=1.0.0&apikey={svc_token}"
        ) as ws:
            ws.send_json(
                _join_frame(
                    "realtime:e2e",
                    config={
                        "postgres_changes": [
                            {"event": "INSERT", "schema": _E2E_SCHEMA, "table": _E2E_TNAME}
                        ]
                    },
                )
            )
            ack = _recv_until(ws, "phx_reply")
            assert ack[4]["status"] == "ok"
            _recv_until(ws, "presence_state")

            # Trigger the row event from outside the WS thread.
            async with pool.acquire() as conn:
                await conn.execute(
                    f"insert into {_E2E_TABLE} (body) values ('e2e-payload')"
                )

            # The notify travels through asyncpg's listener task; a small number
            # of intermediate frames may arrive first (e.g. additional pushes
            # from other tests if state leaked), so loop a few times.
            frame = _recv_until(ws, "postgres_changes", max_frames=20)
            assert frame[2] == "realtime:e2e"
            data = frame[4]["data"]
            assert data["type"] == "INSERT"
            # Broker serializes PostgresChangesData with model_dump(mode="json")
            # — no by_alias — so the key on the wire is the field name
            # (`schema_name`), not the Pydantic alias (`schema`).
            assert data["schema_name"] == _E2E_SCHEMA
            assert data["table"] == _E2E_TNAME
            assert data["record"]["body"] == "e2e-payload"
            assert isinstance(frame[4]["ids"], list) and frame[4]["ids"], (
                "Expected non-empty subscription ids in the postgres_changes payload"
            )


# ---------------------------------------------------------------------------
# Connection cap
# ---------------------------------------------------------------------------


async def test_connection_cap_closes_excess_connections(app):
    """When realtime_max_connections is hit, new WS upgrades are closed (1013).

    The broker is a process-wide singleton; we tighten the cap on the
    instance for the duration of this test and restore it afterwards so
    other tests are not affected.
    """
    from supython.realtime.broker import get_broker

    broker = get_broker()
    original_cap = broker._max_connections
    broker._max_connections = 1

    try:
        with TestClient(app) as client, client.websocket_connect(
            "/realtime/v1/websocket?vsn=1.0.0"
        ) as ws1:
            # Confirm ws1 is healthy.
            ws1.send_json(_heartbeat("hb"))
            reply = ws1.receive_json()
            assert reply[3] == "phx_reply"

            # ws2 should be accepted by the WS handshake then immediately closed.
            with client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0") as ws2:
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    ws2.receive_json()
                # 1013 = TRY_AGAIN_LATER per the WS module's close-code map.
                assert exc_info.value.code == 1013
    finally:
        broker._max_connections = original_cap


# ---------------------------------------------------------------------------
# Per-connection subscription cap
# ---------------------------------------------------------------------------


async def test_subscription_cap_returns_error_reply(app):
    """A phx_join whose postgres_changes count exceeds the per-conn cap is rejected."""
    settings = get_settings()
    too_many = settings.realtime_max_subs_per_conn + 1
    filters = [
        {"event": "INSERT", "schema": "public", "table": f"t{i}"}
        for i in range(too_many)
    ]
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(
            _join_frame(
                "realtime:bigsubs",
                config={"postgres_changes": filters},
            )
        )
        reply = ws.receive_json()
        assert reply[3] == "phx_reply"
        assert reply[4]["status"] == "error"
        reason = reply[4]["response"].get("reason", "")
        assert "subscription cap" in reason


# ---------------------------------------------------------------------------
# Heartbeat timeout
# ---------------------------------------------------------------------------


async def test_heartbeat_timeout_closes_socket(app, monkeypatch):
    """A connection that stops heart-beating is closed with 1001 (going away).

    We patch ``get_settings`` inside the websocket module to a copy with a
    1-second timeout, then open a connection and never send a heartbeat;
    the watchdog must trip and close the socket within a few seconds.
    """
    base = get_settings()
    short = Settings(
        **{**base.model_dump(), "realtime_heartbeat_timeout_seconds": 1}
    )
    monkeypatch.setattr(
        "supython.realtime.websocket.get_settings", lambda: short
    )

    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            # Server has nothing to send, so receive_json() blocks until close.
            ws.receive_json()
        # 1001 = GOING_AWAY per the WS module's close-code map.
        assert exc_info.value.code == 1001
