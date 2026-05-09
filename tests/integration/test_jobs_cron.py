"""Tests for ``jobs.cron.sync_pg_cron``.

``InProcScheduler`` lives in :mod:`supython.jobs.cron_inproc` (behind the
``cron-inproc`` optional extra) and is covered separately where the extra
is installed; this file exercises only the always-available pg_cron sync.
"""

import pytest
import pytest_asyncio

from supython import db
from supython.jobs.cron import sync_pg_cron
from supython.jobs.decorators import cron
from supython.jobs.registry import reset_registry


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_registry()
    yield
    reset_registry()


@pytest_asyncio.fixture
async def conn(pool):
    async with db.as_service_role() as c:
        yield c


async def _purge_cron_schedules():
    """Unschedule any pg_cron entries before clearing the metadata table.

    `sync_pg_cron` calls real `cron.schedule(...)` when pg_cron is present,
    which inserts a `cron.job` row that survives `delete from jobs.cron_schedules`.
    The stale-cleanup loop in sync_pg_cron only unschedules names it finds in
    the metadata table, so once metadata is wiped, the leaked cron.job fires
    forever. Mirror what test_jobs_cron_e2e.py does manually: unschedule first,
    then delete metadata. cron.unschedule needs a LOGIN role, so hop to a
    fresh pool connection rather than the service_role conn the tests use.

    Each step uses its own short-lived connection so we don't share a
    transaction with the test's `conn` fixture — the test's transaction
    holds locks on `cron.job` from any sync_pg_cron call, and a parallel
    transaction trying to unschedule would deadlock.
    """
    async with db.acquire() as c:
        has_pg_cron = await c.fetchval(
            "select exists(select 1 from pg_extension where extname = 'pg_cron')"
        )
    async with db.as_service_role() as c:
        names = [
            r["name"]
            for r in await c.fetch("select name from jobs.cron_schedules")
        ]
    if has_pg_cron and names:
        async with db.acquire() as c:
            for name in names:
                try:
                    await c.execute("select cron.unschedule($1)", name)
                except Exception:
                    pass
    async with db.as_service_role() as c:
        await c.execute("delete from jobs.cron_schedules")


@pytest_asyncio.fixture(autouse=True)
async def _clean_cron(pool):
    await _purge_cron_schedules()
    yield
    await _purge_cron_schedules()


async def test_sync_pg_cron_upserts_schedules(conn):
    @cron("*/5 * * * *", name="cleanup", job_name="cleanup_job")
    async def handler(ctx):
        pass

    await sync_pg_cron(conn)

    row = await conn.fetchrow(
        "select * from jobs.cron_schedules where name = $1", "cleanup"
    )
    assert row is not None
    assert row["cron_expr"] == "*/5 * * * *"
    assert row["job_name"] == "cleanup_job"


async def test_sync_pg_cron_updates_existing(conn):
    @cron("*/5 * * * *", name="cleanup", job_name="cleanup_job")
    async def handler(ctx):
        pass

    await sync_pg_cron(conn)

    reset_registry()

    @cron("*/10 * * * *", name="cleanup", job_name="cleanup_job_v2")
    async def handler2(ctx):
        pass

    await sync_pg_cron(conn)

    row = await conn.fetchrow(
        "select * from jobs.cron_schedules where name = $1", "cleanup"
    )
    assert row is not None
    assert row["cron_expr"] == "*/10 * * * *"
    assert row["job_name"] == "cleanup_job_v2"


@pytest.mark.pg_cron
async def test_sync_pg_cron_records_login_role(
    conn, pg_cron_available: bool
):
    """Regression: pg_cron stamps ``current_user`` on each ``cron.job`` row
    and re-uses it to initialise a background worker at every tick. If
    that role is NOLOGIN — e.g. ``service_role``, which the caller of
    ``sync_pg_cron`` is expected to be in — every tick FATALs with
    ``role "..." is not permitted to log in`` and no job is ever
    enqueued. The failure is invisible above the Postgres server log.

    This is a fast sentinel for the slow ``test_cron_e2e_enqueues_job``:
    it verifies in seconds (no 60s-120s wait for pg_cron to tick) that
    the username stamped by ``sync_pg_cron`` can actually log in.
    """
    if not pg_cron_available:
        pytest.skip("pg_cron extension not available")

    @cron("*/5 * * * *", name="login_check", job_name="login_check_job")
    async def handler(ctx):
        pass

    # Clean up any previous run's entry so we observe this sync only.
    await conn.execute("reset role")
    try:
        async with conn.transaction():
            await conn.execute("select cron.unschedule('login_check')")
    except Exception:
        pass
    await conn.execute("set local role service_role")

    await sync_pg_cron(conn)

    await conn.execute("reset role")
    try:
        row = await conn.fetchrow(
            """
            select j.username, r.rolcanlogin
            from cron.job j
            join pg_roles r on r.rolname = j.username
            where j.jobname = 'login_check'
            """
        )
    finally:
        # Best-effort teardown; the autouse _clean_cron handles the
        # metadata row, but we also unschedule from cron.job.
        try:
            async with conn.transaction():
                await conn.execute("select cron.unschedule('login_check')")
        except Exception:
            pass
        await conn.execute("set local role service_role")

    assert row is not None, (
        "sync_pg_cron did not create a cron.job entry — cron.schedule "
        "silently failed. Check that migration 0007 granted service_role "
        "execute on cron.schedule/unschedule."
    )
    assert row["rolcanlogin"], (
        f"sync_pg_cron stamped cron.job.username={row['username']!r}, "
        f"which is NOLOGIN. pg_cron's background worker can't initialise "
        "as a NOLOGIN role, so every tick will FATAL silently. "
        "sync_pg_cron must hop out of service_role before calling "
        "cron.schedule (see _as_login_role)."
    )
