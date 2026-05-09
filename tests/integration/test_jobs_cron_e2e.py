"""End-to-end cron test — requires pg_cron extension."""

import asyncio
import time

import pytest

from supython import db
from supython.jobs.cron import sync_pg_cron
from supython.jobs.decorators import cron
from supython.jobs.registry import reset_registry


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_registry()
    yield
    reset_registry()


@pytest.mark.pg_cron
@pytest.mark.slow
async def test_cron_e2e_enqueues_job(pool, skip_without_pg_cron):
    async with db.as_service_role() as conn:
        await conn.execute("delete from jobs.cron_schedules")
        await conn.execute("delete from jobs.jobs")

    # Clear any stale ``e2e_test`` entry from a prior run so the
    # assertion below only observes fires produced by *this* sync.
    async with db.acquire() as conn:
        try:
            await conn.execute("select cron.unschedule('e2e_test')")
        except Exception:
            pass

    async with db.as_service_role() as conn:
        @cron("* * * * *", name="e2e_test", job_name="e2e_job")
        async def handler(ctx):
            pass

        await sync_pg_cron(conn)

    # pg_cron's launcher polls ``cron.job`` once per minute; a
    # newly-inserted ``* * * * *`` schedule can therefore take up to
    # ~120s from scheduling until its first fire (worst case:
    # launcher tick happens just before our insert, so the next
    # launcher tick is ~60s away, and the first minute-boundary fire
    # is up to another ~60s after that). Poll up to 150s instead of
    # the old fixed 65s sleep, which was below this bound and made
    # the test flaky even when the wiring was correct.
    deadline = time.monotonic() + 150
    cnt = 0
    async with db.acquire() as conn:
        while time.monotonic() < deadline:
            cnt = await conn.fetchval(
                "select count(*) from jobs.jobs where name = 'e2e_job'"
            )
            if cnt >= 1:
                break
            await asyncio.sleep(2)

    assert cnt >= 1, (
        f"pg_cron did not enqueue a jobs.jobs row within 150s "
        f"(count={cnt}); inspect cron.job and cron.job_run_details "
        f"for scheduling / tick-time errors"
    )

    # Teardown: remove the schedule so follow-up test runs don't
    # accumulate fires between runs.
    async with db.acquire() as conn:
        try:
            await conn.execute("select cron.unschedule('e2e_test')")
        except Exception:
            pass
