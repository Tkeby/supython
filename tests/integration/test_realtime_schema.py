"""Integration tests for the realtime SQL schema (migration 0006).

Requires ``supython up`` (Postgres on port 54322) to be running.

Covered scenarios:
- Schema, table, and helper functions exist after migration.
- ``realtime.enable(regclass)`` is idempotent: calling it twice on the same
  table succeeds and leaves a single registry row + trigger.
- ``realtime.enable`` correctly populates ``realtime.enabled_tables`` with the
  PK columns and owner_column.
- An INSERT/UPDATE/DELETE on an enabled table fires ``pg_notify`` on the
  ``realtime:changes`` channel with the expected JSON shape.

The tests create a dedicated ``public.rt_schema_test`` table so they cannot
conflict with the data manipulated by other test modules.  A function-scoped
fixture drops and re-creates the table and cleans the registry entry before
each test, and tears everything down afterwards.
"""

import asyncio
import json
import uuid

import asyncpg
import pytest
import pytest_asyncio

from supython.settings import get_settings

# ---------------------------------------------------------------------------
# Skip entire module when Postgres is not reachable
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
# Fixtures
# ---------------------------------------------------------------------------

_TABLE = "public.rt_schema_test"
_SCHEMA = "public"
_TNAME = "rt_schema_test"


@pytest_asyncio.fixture
async def schema_table(pool: asyncpg.Pool):
    """Create the test table and clean up after."""
    async with pool.acquire() as conn:
        # Create as superuser (supython) — no service_role DDL needed.
        await conn.execute(
            f"""
            create table if not exists {_TABLE} (
                id         serial primary key,
                owner_id   uuid,
                name       text not null default ''
            )
            """
        )
    yield _TABLE
    # Teardown: remove trigger, registry entry, and the table itself.
    async with pool.acquire() as conn:
        await conn.execute(
            f"drop trigger if exists realtime_notify on {_TABLE}"
        )
        await conn.execute(
            f"""
            delete from realtime.enabled_tables
            where schema_name = '{_SCHEMA}' and table_name = '{_TNAME}'
            """
        )
        await conn.execute(f"drop table if exists {_TABLE}")


@pytest_asyncio.fixture
async def enabled_table(pool: asyncpg.Pool, schema_table):
    """Enable realtime on the test table (service_role call)."""
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute('set local role "service_role"')
        await conn.execute(
            "select realtime.enable($1::regclass, $2)",
            _TABLE,
            "owner_id",
        )
    yield schema_table


@pytest_asyncio.fixture
async def listen_conn():
    """Dedicated asyncpg connection for capturing pg_notify events."""
    s = get_settings()
    conn = await asyncpg.connect(s.database_url)
    notifications: list[dict] = []
    ready = asyncio.Event()

    async def _cb(_conn, _pid, _channel, payload: str) -> None:
        notifications.append(json.loads(payload))
        ready.set()

    await conn.add_listener("realtime:changes", _cb)
    yield conn, notifications, ready
    await conn.remove_listener("realtime:changes", _cb)
    await conn.close()


# ---------------------------------------------------------------------------
# Schema structure
# ---------------------------------------------------------------------------


async def test_realtime_schema_exists(pool: asyncpg.Pool):
    """The ``realtime`` schema must be present after migration 0006."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select 1 from information_schema.schemata where schema_name = 'realtime'"
        )
    assert row is not None, "realtime schema is missing"


async def test_enabled_tables_table_exists(pool: asyncpg.Pool):
    """``realtime.enabled_tables`` must exist with the expected columns."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select 1
            from information_schema.tables
            where table_schema = 'realtime'
              and table_name   = 'enabled_tables'
            """
        )
    assert row is not None, "realtime.enabled_tables table is missing"


async def test_fire_notify_function_exists(pool: asyncpg.Pool):
    """``realtime.fire_notify()`` trigger function must exist."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select 1
            from information_schema.routines
            where routine_schema = 'realtime'
              and routine_name   = 'fire_notify'
            """
        )
    assert row is not None, "realtime.fire_notify() function is missing"


async def test_enable_function_exists(pool: asyncpg.Pool):
    """``realtime.enable(regclass, text)`` must exist."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select 1
            from information_schema.routines
            where routine_schema = 'realtime'
              and routine_name   = 'enable'
            """
        )
    assert row is not None, "realtime.enable() function is missing"


# ---------------------------------------------------------------------------
# realtime.enable
# ---------------------------------------------------------------------------


async def test_enable_creates_registry_row(pool: asyncpg.Pool, enabled_table):
    """After enable(), a row appears in realtime.enabled_tables."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select schema_name, table_name, pk_columns, owner_column
            from realtime.enabled_tables
            where schema_name = $1 and table_name = $2
            """,
            _SCHEMA,
            _TNAME,
        )
    assert row is not None, "No registry row was created by realtime.enable()"
    assert list(row["pk_columns"]) == ["id"]
    assert row["owner_column"] == "owner_id"


async def test_enable_creates_trigger(pool: asyncpg.Pool, enabled_table):
    """After enable(), the ``realtime_notify`` AFTER trigger exists on the table."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select 1
            from information_schema.triggers
            where event_object_schema = $1
              and event_object_table  = $2
              and trigger_name        = 'realtime_notify'
            """,
            _SCHEMA,
            _TNAME,
        )
    assert row is not None, "realtime_notify trigger was not created"


async def test_enable_is_idempotent(pool: asyncpg.Pool, enabled_table):
    """Calling enable() a second time on the same table must not raise."""
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute('set local role "service_role"')
        # Should succeed without error.
        await conn.execute(
            "select realtime.enable($1::regclass, $2)",
            _TABLE,
            "owner_id",
        )
    # Exactly one registry row.
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "select count(*) from realtime.enabled_tables where schema_name=$1 and table_name=$2",
            _SCHEMA,
            _TNAME,
        )
    assert count == 1, f"Expected 1 registry row after idempotent enable; got {count}"


async def test_enable_sets_owner_column_null_when_column_absent(
    pool: asyncpg.Pool, schema_table
):
    """When the requested owner_column does not exist, enable() records NULL."""
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute('set local role "service_role"')
        await conn.execute(
            "select realtime.enable($1::regclass, $2)",
            _TABLE,
            "nonexistent_column",   # column does not exist on the table
        )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select owner_column from realtime.enabled_tables"
            " where schema_name=$1 and table_name=$2",
            _SCHEMA, _TNAME,
        )
    assert row is not None
    assert row["owner_column"] is None, (
        "owner_column should be NULL when the column is absent from the table"
    )


# ---------------------------------------------------------------------------
# pg_notify payload shape
# ---------------------------------------------------------------------------


async def test_insert_fires_notify_with_correct_shape(
    pool: asyncpg.Pool, enabled_table, listen_conn
):
    """INSERT fires pg_notify with the expected JSON shape on realtime:changes."""
    conn, notifications, ready = listen_conn
    owner_id = str(uuid.uuid4())

    async with pool.acquire() as conn_w:
        await conn_w.execute(
            f"insert into {_TABLE} (owner_id, name) values ($1, $2)",
            uuid.UUID(owner_id),
            "test-insert",
        )

    await asyncio.wait_for(ready.wait(), timeout=5.0)

    assert len(notifications) >= 1
    payload = notifications[-1]
    assert payload["schema"] == _SCHEMA
    assert payload["table"] == _TNAME
    assert payload["type"] == "INSERT"
    assert payload["commit_timestamp"]
    assert isinstance(payload["columns"], list)
    assert payload["record"] is not None
    assert payload["record"]["name"] == "test-insert"
    assert payload["old_record"] is None


async def test_update_fires_notify_with_old_and_new_record(
    pool: asyncpg.Pool, enabled_table, listen_conn
):
    """UPDATE fires pg_notify with both 'record' (NEW) and 'old_record' (OLD)."""
    conn, notifications, ready = listen_conn

    async with pool.acquire() as conn_w:
        row_id = await conn_w.fetchval(
            f"insert into {_TABLE} (name) values ('before') returning id"
        )

    # Reset the event after INSERT notification.
    ready.clear()
    notifications.clear()

    async with pool.acquire() as conn_w:
        await conn_w.execute(
            f"update {_TABLE} set name = 'after' where id = $1", row_id
        )

    await asyncio.wait_for(ready.wait(), timeout=5.0)

    payload = notifications[-1]
    assert payload["type"] == "UPDATE"
    assert payload["record"]["name"] == "after"
    assert payload["old_record"]["name"] == "before"


async def test_delete_fires_notify_with_old_record_and_null_record(
    pool: asyncpg.Pool, enabled_table, listen_conn
):
    """DELETE fires pg_notify with 'old_record' set and 'record' null."""
    conn, notifications, ready = listen_conn

    async with pool.acquire() as conn_w:
        row_id = await conn_w.fetchval(
            f"insert into {_TABLE} (name) values ('to-delete') returning id"
        )

    ready.clear()
    notifications.clear()

    async with pool.acquire() as conn_w:
        await conn_w.execute(f"delete from {_TABLE} where id = $1", row_id)

    await asyncio.wait_for(ready.wait(), timeout=5.0)

    payload = notifications[-1]
    assert payload["type"] == "DELETE"
    assert payload["record"] is None
    assert payload["old_record"]["name"] == "to-delete"
    assert payload["old_record"]["id"] == row_id


async def test_notify_payload_includes_column_metadata(
    pool: asyncpg.Pool, enabled_table, listen_conn
):
    """The ``columns`` field in the notify payload lists column name/type pairs."""
    _conn, notifications, ready = listen_conn

    async with pool.acquire() as conn_w:
        await conn_w.execute(
            f"insert into {_TABLE} (name) values ('cols-test')"
        )

    await asyncio.wait_for(ready.wait(), timeout=5.0)

    payload = notifications[-1]
    columns = {c["name"]: c["type"] for c in payload["columns"]}
    assert "id" in columns
    assert "name" in columns
    assert "owner_id" in columns


# ---------------------------------------------------------------------------
# 8KB NOTIFY ceiling — fire_notify() must warn + skip, not abort the write
# (migration 0014_realtime_payload_warning.sql)
# ---------------------------------------------------------------------------


async def test_oversize_payload_skips_notify_and_emits_warning(
    pool: asyncpg.Pool, enabled_table, listen_conn
):
    """Writes that would render a >8KB NOTIFY payload succeed without firing.

    The trigger pre-checks the rendered payload size; over the 7900-byte
    headroom threshold it raises a WARNING and skips ``pg_notify``.  The
    user's INSERT still commits — that is the whole point of this guard.
    """
    _listener_conn, notifications, ready = listen_conn

    # ~9.5 KB of column data — comfortably over the 7900-byte threshold
    # once jsonb-encoded with the surrounding metadata.
    big_value = "x" * 9500

    warnings: list[str] = []
    listener = lambda _c, msg: warnings.append(f"{msg.severity}:{msg.message}")  # noqa: E731

    async with pool.acquire() as conn_w:
        conn_w.add_log_listener(listener)
        try:
            await conn_w.execute(
                f"insert into {_TABLE} (name) values ($1)", big_value
            )
        finally:
            conn_w.remove_log_listener(listener)

    # Write must have committed — the row is queryable.
    async with pool.acquire() as conn_r:
        row_count = await conn_r.fetchval(
            f"select count(*) from {_TABLE} where name = $1", big_value
        )
    assert row_count == 1, "oversize INSERT must commit despite oversize NOTIFY payload"

    # No NOTIFY for this row (the trigger skipped it).  Allow a brief grace
    # period for any in-flight delivery, then assert silence.
    try:
        await asyncio.wait_for(ready.wait(), timeout=0.5)
    except asyncio.TimeoutError:
        pass
    assert notifications == [], (
        f"trigger emitted a notify for the oversize row: {notifications!r}"
    )

    # Exactly one WARNING that names the table, op, and rendered byte count.
    matching = [
        w for w in warnings
        if "WARNING" in w
        and "fire_notify" in w
        and _TNAME in w
        and "INSERT" in w
        and "NOTIFY ceiling" in w
    ]
    assert len(matching) == 1, (
        f"expected exactly one fire_notify oversize warning; got {warnings!r}"
    )


async def test_under_threshold_payload_still_fires_notify(
    pool: asyncpg.Pool, enabled_table, listen_conn
):
    """A row whose rendered payload is just under the ceiling still fires NOTIFY.

    Guards against regression: the size pre-check must only suppress
    genuinely oversize payloads, not normal traffic.
    """
    _listener_conn, notifications, ready = listen_conn

    # Comfortably under 7900 bytes after wrapping in the trigger's JSON.
    medium = "y" * 4000

    async with pool.acquire() as conn_w:
        await conn_w.execute(
            f"insert into {_TABLE} (name) values ($1)", medium
        )

    await asyncio.wait_for(ready.wait(), timeout=5.0)
    assert any(
        n["type"] == "INSERT" and n["record"]["name"] == medium
        for n in notifications
    )
