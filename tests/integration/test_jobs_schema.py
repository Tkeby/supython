"""Tests for the jobs schema (0007_jobs_schema.sql).

Covers: idempotent migration, enqueue returning (job, is_new), duplicate
idempotency key, claim_next with SKIP LOCKED, and zombie reclaim.

The SELECT syntax drops the ``as (j jobs.jobs, is_new boolean)`` column
definition list that the pre-grooming tests used: ``jobs.enqueue`` declares
named OUT columns (``job jobs.jobs``, ``is_new boolean``), so Postgres treats
a redundant column-def list as a syntax error. ``select (job).*, is_new``
is the correct form.
"""

import asyncpg
import pytest_asyncio

from supython import db


@pytest_asyncio.fixture
async def conn(pool: asyncpg.Pool) -> asyncpg.Connection:
    async with db.as_service_role() as c:
        yield c


async def _clean(conn: asyncpg.Connection) -> None:
    await conn.execute("delete from jobs.jobs")


@pytest_asyncio.fixture(autouse=True)
async def _clean_jobs(conn: asyncpg.Connection):
    await _clean(conn)
    yield
    await _clean(conn)


async def test_enqueue_inserts_and_returns_is_new(conn: asyncpg.Connection):
    row = await conn.fetchrow(
        """
        select (job).id, (job).name, (job).status, is_new
        from jobs.enqueue($1)
        """,
        "test_job",
    )
    assert row["is_new"] is True
    assert row["name"] == "test_job"
    assert row["status"] == "queued"


async def test_enqueue_with_payload_and_queue(conn: asyncpg.Connection):
    row = await conn.fetchrow(
        """
        select (job).payload, (job).queue, (job).max_attempts, is_new
        from jobs.enqueue(
            p_name := $1,
            p_payload := $2::jsonb,
            p_queue := $3,
            p_max_attempts := $4
        )
        """,
        "test_job",
        '{"key": "value"}',
        "emails",
        5,
    )
    assert row["is_new"] is True
    # asyncpg returns jsonb as text unless a codec is registered.
    import json as _json

    payload = row["payload"]
    if isinstance(payload, str):
        payload = _json.loads(payload)
    assert payload["key"] == "value"
    assert row["queue"] == "emails"
    assert row["max_attempts"] == 5


async def test_enqueue_idempotency_key_returns_existing(conn: asyncpg.Connection):
    first = await conn.fetchrow(
        """
        select (job).id, is_new
        from jobs.enqueue(p_name := $1, p_idempotency_key := $2)
        """,
        "test_job",
        "unique-key-1",
    )
    assert first["is_new"] is True

    second = await conn.fetchrow(
        """
        select (job).id, is_new
        from jobs.enqueue(p_name := $1, p_idempotency_key := $2)
        """,
        "test_job",
        "unique-key-1",
    )
    assert second["is_new"] is False
    assert second["id"] == first["id"]


async def test_enqueue_different_idempotency_keys_insert_separately(conn: asyncpg.Connection):
    a = await conn.fetchrow(
        """
        select (job).id, is_new
        from jobs.enqueue(p_name := $1, p_idempotency_key := $2)
        """,
        "test_job",
        "key-a",
    )
    b = await conn.fetchrow(
        """
        select (job).id, is_new
        from jobs.enqueue(p_name := $1, p_idempotency_key := $2)
        """,
        "test_job",
        "key-b",
    )
    assert a["is_new"] is True
    assert b["is_new"] is True
    assert a["id"] != b["id"]


async def test_claim_next_claims_queued_job(conn: asyncpg.Connection):
    # ``select jobs.enqueue($1)`` would ask asyncpg to decode the composite
    # ``jobs.jobs`` return type on the wire; the decoder for that OID is not
    # registered globally (it's a framework decision — see PROJECT.md §18
    # 2026-04-22 codec row) so we destructure into scalars at the SELECT level.
    await conn.fetchval(
        "select (job).id from jobs.enqueue($1)",
        "test_job",
    )

    rows = await conn.fetch(
        "select * from jobs.claim_next(p_worker_id := $1)",
        "worker-1",
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "running"
    assert rows[0]["locked_by"] == "worker-1"
    assert rows[0]["attempts"] == 1


async def test_claim_next_skip_locked(conn: asyncpg.Connection):
    await conn.fetchval("select (job).id from jobs.enqueue($1)", "test_job")

    rows = await conn.fetch(
        "select * from jobs.claim_next(p_worker_id := $1)",
        "worker-1",
    )
    assert len(rows) == 1

    rows2 = await conn.fetch(
        "select * from jobs.claim_next(p_worker_id := $1)",
        "worker-2",
    )
    assert len(rows2) == 0


async def test_claim_next_zombie_reclaim(conn: asyncpg.Connection):
    await conn.execute(
        """
        insert into jobs.jobs (name, status, attempts, locked_at, locked_by)
        values ($1, 'running', 1, now() - interval '6 minutes', 'dead-worker')
        """,
        "zombie_job",
    )

    rows = await conn.fetch(
        "select * from jobs.claim_next(p_worker_id := $1, p_visibility_timeout_ms := 300000)",
        "worker-new",
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "running"
    assert rows[0]["locked_by"] == "worker-new"
    assert rows[0]["attempts"] == 2


async def test_claim_next_respects_run_at(conn: asyncpg.Connection):
    await conn.fetchval(
        """
        select (job).id
        from jobs.enqueue(
            p_name := $1,
            p_run_at := now() + interval '1 hour'
        )
        """,
        "future_job",
    )

    rows = await conn.fetch(
        "select * from jobs.claim_next(p_worker_id := $1)",
        "worker-1",
    )
    assert len(rows) == 0


async def test_claim_next_respects_queue(conn: asyncpg.Connection):
    await conn.fetchval(
        "select (job).id from jobs.enqueue(p_name := $1, p_queue := $2)",
        "job_a",
        "queue_a",
    )

    rows = await conn.fetch(
        "select * from jobs.claim_next(p_queue := $1, p_worker_id := $2)",
        "queue_b",
        "worker-1",
    )
    assert len(rows) == 0

    rows = await conn.fetch(
        "select * from jobs.claim_next(p_queue := $1, p_worker_id := $2)",
        "queue_a",
        "worker-1",
    )
    assert len(rows) == 1


async def test_enqueue_with_user_id(conn: asyncpg.Connection):
    user_id = await conn.fetchval(
        """
        insert into auth.users (email, encrypted_password, email_confirmed_at)
        values ($1, $2, now())
        returning id
        """,
        "jobs-test@example.com",
        "irrelevant",
    )

    row = await conn.fetchrow(
        """
        select (job).user_id, is_new
        from jobs.enqueue(p_name := $1, p_user_id := $2)
        """,
        "user_job",
        user_id,
    )
    assert row["is_new"] is True
    assert row["user_id"] == user_id
