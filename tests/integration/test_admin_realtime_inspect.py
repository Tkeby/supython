"""Integration tests for /admin/api/v1/realtime endpoints.

Covers:
- GET  /tables           — auth gate, shape, content
- GET  /inspect?topic=   — auth gate, invalid topic 400, broker-down 503,
                            SSE happy-path (connected event)
- POST /broadcast        — auth gate, invalid topic 400, valid 202,
                            audit row written

The SSE happy-path tests drive ``_inspect_events`` directly rather than
going through ``client.stream()``: httpx ``ASGITransport`` buffers the
entire response body before returning (it does not support streaming),
which would deadlock against the broker's 30-second heartbeat loop.
"""

import asyncio
import json

import asyncpg
import httpx
import pytest_asyncio

from supython import passwords
from supython.admin import session as admin_session
from supython.admin.api.realtime import _inspect_events
from supython.realtime import get_broker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_user(pool: asyncpg.Pool):
    email = "ops@example.com"
    password = "correct horse battery staple"
    pw_hash = passwords.hash_password(password)
    async with pool.acquire() as conn:
        await conn.execute("delete from admin.admin_sessions")
        await conn.execute("delete from admin.admin_audit")
        await conn.execute("delete from admin.admin_users")
        admin_id = await conn.fetchval(
            """
            insert into admin.admin_users (email, password_hash, is_root)
            values ($1, $2, true)
            returning id
            """,
            email,
            pw_hash,
        )
    yield {"id": admin_id, "email": email, "password": password}
    async with pool.acquire() as conn:
        await conn.execute("delete from admin.admin_sessions")
        await conn.execute("delete from admin.admin_audit")
        await conn.execute("delete from admin.admin_users")


async def _login(client: httpx.AsyncClient, admin_user: dict) -> None:
    r = await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert r.status_code == 200, r.text
    assert client.cookies.get(admin_session.SESSION_COOKIE) is not None


# ---------------------------------------------------------------------------
# Auth gates — all three endpoints require admin session
# ---------------------------------------------------------------------------


async def test_tables_requires_admin(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/realtime/tables")
    assert r.status_code == 401


async def test_inspect_requires_admin(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/realtime/inspect?topic=realtime:test")
    assert r.status_code == 401


async def test_broadcast_requires_admin(client: httpx.AsyncClient):
    r = await client.post(
        "/admin/api/v1/realtime/broadcast",
        json={"topic": "realtime:test", "event": "ping", "payload": {}},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /tables — list enabled tables
# ---------------------------------------------------------------------------


async def test_tables_returns_list(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    # Enable a table so there is at least one row.
    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        await conn.execute("select realtime.enable('public.todos'::regclass, 'user_id')")

    r = await client.get("/admin/api/v1/realtime/tables")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list)

    # Find the todos entry.
    todos = [t for t in rows if t["table_name"] == "todos"]
    assert len(todos) == 1
    assert todos[0]["schema_name"] == "public"
    assert todos[0]["owner_column"] == "user_id"
    assert isinstance(todos[0]["pk_columns"], list)
    assert "id" in todos[0]["pk_columns"]
    assert todos[0]["created_at"] is not None


async def test_tables_empty_when_none_enabled(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    # Remove any previously enabled tables.
    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        await conn.execute("delete from realtime.enabled_tables")

    r = await client.get("/admin/api/v1/realtime/tables")
    assert r.status_code == 200, r.text
    assert r.json() == []


# ---------------------------------------------------------------------------
# GET /inspect — SSE broker subscriber (error paths)
# ---------------------------------------------------------------------------


async def test_inspect_invalid_topic_returns_400(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/realtime/inspect?topic=bad!!!topic")
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "invalid_topic"


async def test_inspect_broker_down_returns_503(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    """When the broker is not running (not started), the endpoint returns 503."""
    await _login(client, admin_user)

    broker = get_broker()
    assert not broker.is_healthy, "broker should not be started in integration suite"

    r = await client.get("/admin/api/v1/realtime/inspect?topic=realtime:test")
    assert r.status_code == 503
    body = r.json()
    assert body["detail"]["code"] == "broker_unhealthy"


# ---------------------------------------------------------------------------
# GET /inspect — SSE happy-path (requires broker start)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def running_broker(pool: asyncpg.Pool):
    """Start the broker and stop it after the test."""
    broker = get_broker()
    await broker.start()
    yield broker
    await broker.stop()


def _parse_sse_frame(frame: str) -> dict:
    """Parse a single SSE frame ("event: …\\ndata: …\\n\\n") into a dict."""
    event = ""
    data: dict = {}
    for line in frame.split("\n"):
        if line.startswith("event: "):
            event = line[len("event: ") :]
        elif line.startswith("data: "):
            data = json.loads(line[len("data: ") :])
    return {"event": event, "data": data}


async def test_inspect_sse_connected_event(running_broker):
    """First frame yielded by the inspect generator is a 'connected' event."""
    gen = _inspect_events("realtime:test")
    try:
        first = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
    finally:
        await gen.aclose()

    parsed = _parse_sse_frame(first)
    assert parsed["event"] == "connected"
    assert parsed["data"]["topic"] == "realtime:test"
    assert isinstance(parsed["data"]["tables"], int)


async def test_inspect_disconnects_on_cancellation(running_broker):
    """Closing the inspect generator unregisters its broker connection."""
    broker = running_broker
    before = broker.connection_count

    gen = _inspect_events("realtime:test")
    # Drive the generator far enough to register + subscribe.
    first = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
    assert first.startswith("event: connected")
    assert broker.connection_count == before + 1

    # Close the generator (analogous to the client disconnecting).
    await gen.aclose()
    assert broker.connection_count == before


# ---------------------------------------------------------------------------
# POST /broadcast — confirm-required broadcast
# ---------------------------------------------------------------------------


async def test_broadcast_invalid_topic_returns_400(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    await _login(client, admin_user)
    r = await client.post(
        "/admin/api/v1/realtime/broadcast",
        json={"topic": "bad topic", "event": "ping", "payload": {}},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "invalid_topic"


async def test_broadcast_valid_returns_202(
    client: httpx.AsyncClient,
    admin_user: dict,
    running_broker,
    pool: asyncpg.Pool,
):
    """Valid broadcast returns 202 and writes an audit row."""
    await _login(client, admin_user)

    r = await client.post(
        "/admin/api/v1/realtime/broadcast",
        json={"topic": "realtime:test", "event": "ping", "payload": {"msg": "hello"}},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["topic"] == "realtime:test"
    assert body["delivered"] == 0  # no subscribers yet

    # Audit row must exist.
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select action, target, payload
            from admin.admin_audit
            where action = 'realtime.broadcast'
            order by at desc
            limit 1
            """
        )
    assert row is not None
    assert row["action"] == "realtime.broadcast"
    assert row["target"] == "realtime:test"
    payload = json.loads(row["payload"])
    assert payload["event"] == "ping"
    assert payload["delivered"] == 0


async def test_broadcast_delivers_to_inspector(
    client: httpx.AsyncClient,
    admin_user: dict,
    running_broker,
):
    """A broadcast event reaches an active inspect generator subscriber."""
    await _login(client, admin_user)

    gen = _inspect_events("realtime:delivery-test")
    try:
        # Drain the connected frame so the generator is fully subscribed.
        connected = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
        assert connected.startswith("event: connected")

        # Broadcast into the same topic via HTTP.
        r = await client.post(
            "/admin/api/v1/realtime/broadcast",
            json={
                "topic": "realtime:delivery-test",
                "event": "greeting",
                "payload": {"text": "hi"},
            },
        )
        assert r.status_code == 202
        assert r.json()["delivered"] >= 1

        # Next frame on the generator should be the broadcast.
        frame = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
        parsed = _parse_sse_frame(frame)
        assert parsed["event"] == "broadcast"
        assert parsed["data"]["topic"] == "realtime:delivery-test"
        bcast_payload = parsed["data"]["payload"]
        assert bcast_payload.get("event") == "greeting"
        assert bcast_payload.get("payload", {}).get("text") == "hi"
    finally:
        await gen.aclose()
