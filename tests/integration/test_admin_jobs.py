"""Integration tests for /admin/api/v1/jobs endpoints.

Covers:
- GET  /queue                     — auth gate, empty page, pagination, status filter, counts
- POST /{id}/retry                — auth gate, 404, 409, success, audit row
- POST /{id}/cancel               — auth gate, 404, success, audit row
- GET  /crons                     — auth gate, list shape
- GET  /crons/health              — auth gate, shape
- POST /crons/{name}/run-now      — auth gate, 404, 409 disabled, success, audit row
"""

import json

import asyncpg
import httpx
import pytest_asyncio

from supython import passwords
from supython.admin import session as admin_session

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
# Auth gates — all endpoints require admin session
# ---------------------------------------------------------------------------


async def test_queue_requires_admin(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/jobs/queue")
    assert r.status_code == 401


async def test_retry_requires_admin(client: httpx.AsyncClient):
    r = await client.post("/admin/api/v1/jobs/00000000-0000-0000-0000-000000000000/retry")
    assert r.status_code == 401


async def test_cancel_requires_admin(client: httpx.AsyncClient):
    r = await client.post("/admin/api/v1/jobs/00000000-0000-0000-0000-000000000000/cancel")
    assert r.status_code == 401


async def test_crons_requires_admin(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/jobs/crons")
    assert r.status_code == 401


async def test_cron_health_requires_admin(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/jobs/crons/health")
    assert r.status_code == 401


async def test_run_cron_now_requires_admin(client: httpx.AsyncClient):
    r = await client.post("/admin/api/v1/jobs/crons/test-cron/run-now")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /queue — paginated job list
# ---------------------------------------------------------------------------


async def test_queue_returns_empty_page(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    await _login(client, admin_user)

    r = await client.get("/admin/api/v1/jobs/queue")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == []
    assert body["total"] == 0
    assert isinstance(body["counts"], dict)


async def test_queue_returns_jobs_with_counts(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    # Create test jobs via the enqueue function.
    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        for i in range(3):
            await conn.fetchrow(
                """
                select (job).*
                from jobs.enqueue(p_name := $1, p_queue := 'emails')
                """,
                f"test-job-{i}",
            )

    r = await client.get("/admin/api/v1/jobs/queue")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert len(body["rows"]) == 3
    counts = body["counts"]
    assert counts.get("queued", 0) == 3
    # Ensure rows have expected shape.
    row = body["rows"][0]
    assert row["status"] == "queued"
    assert row["name"].startswith("test-job-")


async def test_queue_filters_by_status(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        r1 = await conn.fetchrow("select (job).id from jobs.enqueue(p_name := 'job-a')")
        job_id = r1["id"]
        await conn.execute(
            "update jobs.jobs set status = 'succeeded', finished_at = now() where id = $1",
            job_id,
        )
        await conn.fetchrow("select (job).id from jobs.enqueue(p_name := 'job-b')")

    r = await client.get("/admin/api/v1/jobs/queue?status=succeeded")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["rows"][0]["status"] == "succeeded"

    r = await client.get("/admin/api/v1/jobs/queue?status=queued")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["rows"][0]["status"] == "queued"


async def test_queue_respects_limit_offset(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        for i in range(5):
            await conn.fetchrow(
                "select (job).id from jobs.enqueue(p_name := $1)",
                f"job-{i}",
            )

    r = await client.get("/admin/api/v1/jobs/queue?limit=2&offset=0")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 5
    assert len(body["rows"]) == 2

    r = await client.get("/admin/api/v1/jobs/queue?limit=2&offset=2")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 5
    assert len(body["rows"]) == 2


# ---------------------------------------------------------------------------
# POST /{id}/retry — retry a failed or cancelled job
# ---------------------------------------------------------------------------


async def test_retry_returns_404_for_missing_job(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    await _login(client, admin_user)
    r = await client.post("/admin/api/v1/jobs/00000000-0000-0000-0000-000000000000/retry")
    assert r.status_code == 404
    # The service forwards the underlying JobError code ("retry_failed") as-is.
    assert r.json()["detail"]["code"] == "retry_failed"


async def test_retry_returns_409_for_non_retryable(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        row = await conn.fetchrow("select (job).id from jobs.enqueue(p_name := 'pending-job')")
        job_id = row["id"]

    # A queued job is not retryable.
    r = await client.post(f"/admin/api/v1/jobs/{job_id}/retry")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "retry_failed"


async def test_retry_succeeds_for_failed_job(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        row = await conn.fetchrow("select (job).id from jobs.enqueue(p_name := 'doomed-job')")
        job_id = row["id"]
        await conn.execute(
            "update jobs.jobs set status = 'failed', finished_at = now(), last_error = 'oops' where id = $1",
            job_id,
        )

    r = await client.post(f"/admin/api/v1/jobs/{job_id}/retry")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["last_error"] is None
    assert body["finished_at"] is None

    # Audit row written.
    async with pool.acquire() as conn:
        audit_row = await conn.fetchrow(
            """
            select action, target, payload
            from admin.admin_audit
            where action = 'jobs.retry'
            order by at desc
            limit 1
            """
        )
    assert audit_row is not None
    assert audit_row["action"] == "jobs.retry"
    assert audit_row["target"] == str(job_id)


async def test_retry_succeeds_for_cancelled_job(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        row = await conn.fetchrow("select (job).id from jobs.enqueue(p_name := 'stopped-job')")
        job_id = row["id"]
        await conn.execute(
            "update jobs.jobs set status = 'cancelled', finished_at = now() where id = $1",
            job_id,
        )

    r = await client.post(f"/admin/api/v1/jobs/{job_id}/retry")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"


# ---------------------------------------------------------------------------
# POST /{id}/cancel — cancel a queued job
# ---------------------------------------------------------------------------


async def test_cancel_returns_404_for_terminal_job(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        row = await conn.fetchrow("select (job).id from jobs.enqueue(p_name := 'finished-job')")
        job_id = row["id"]
        await conn.execute(
            "update jobs.jobs set status = 'succeeded', finished_at = now() where id = $1",
            job_id,
        )

    r = await client.post(f"/admin/api/v1/jobs/{job_id}/cancel")
    assert r.status_code == 404, r.text


async def test_cancel_succeeds_for_queued_job(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        row = await conn.fetchrow("select (job).id from jobs.enqueue(p_name := 'abort-job')")
        job_id = row["id"]

    r = await client.post(f"/admin/api/v1/jobs/{job_id}/cancel")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["finished_at"] is not None

    # Audit row written.
    async with pool.acquire() as conn:
        audit_row = await conn.fetchrow(
            """
            select action, target, payload
            from admin.admin_audit
            where action = 'jobs.cancel'
            order by at desc
            limit 1
            """
        )
    assert audit_row is not None
    assert audit_row["action"] == "jobs.cancel"
    assert audit_row["target"] == str(job_id)


# ---------------------------------------------------------------------------
# GET /crons — list cron schedules
# ---------------------------------------------------------------------------


async def test_crons_returns_list(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    # Insert a test cron schedule.
    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        await conn.execute("delete from jobs.cron_schedules")
        await conn.execute(
            """
            insert into jobs.cron_schedules
                (name, cron_expr, job_name, job_version, payload, queue, enabled)
            values ($1, $2, $3, $4, $5::jsonb, $6, $7)
            """,
            "hourly-cleanup",
            "0 * * * *",
            "cleanup-job",
            1,
            json.dumps({"scope": "all"}),
            "default",
            True,
        )

    r = await client.get("/admin/api/v1/jobs/crons")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    cron = body[0]
    assert cron["name"] == "hourly-cleanup"
    assert cron["cron_expr"] == "0 * * * *"
    assert cron["job_name"] == "cleanup-job"
    assert cron["enabled"] is True
    assert cron["payload"] == {"scope": "all"}

    # Clean up.
    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        await conn.execute("delete from jobs.cron_schedules")


# ---------------------------------------------------------------------------
# GET /crons/health — pg_cron health
# ---------------------------------------------------------------------------


async def test_cron_health_returns_shape(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    await _login(client, admin_user)

    r = await client.get("/admin/api/v1/jobs/crons/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "installed" in body
    assert "active_jobs" in body
    assert "extension_version" in body
    assert isinstance(body["installed"], bool)
    assert isinstance(body["active_jobs"], int)


# ---------------------------------------------------------------------------
# POST /crons/{name}/run-now — enqueue a cron's job
# ---------------------------------------------------------------------------


async def test_run_cron_now_returns_404_for_missing(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    await _login(client, admin_user)
    r = await client.post("/admin/api/v1/jobs/crons/no-such-cron/run-now")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "cron_not_found"


async def test_run_cron_now_returns_409_for_disabled(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        await conn.execute("delete from jobs.cron_schedules")
        await conn.execute(
            """
            insert into jobs.cron_schedules
                (name, cron_expr, job_name, job_version, payload, queue, enabled)
            values ($1, $2, $3, $4, $5::jsonb, $6, false)
            """,
            "disabled-cron",
            "*/5 * * * *",
            "disabled-job",
            1,
            "{}",
            "default",
        )

    r = await client.post("/admin/api/v1/jobs/crons/disabled-cron/run-now")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "cron_disabled"

    # Clean up.
    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        await conn.execute("delete from jobs.cron_schedules")


async def test_run_cron_now_enqueues_job(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        await conn.execute("delete from jobs.cron_schedules")
        await conn.execute(
            """
            insert into jobs.cron_schedules
                (name, cron_expr, job_name, job_version, payload, queue, enabled)
            values ($1, $2, $3, $4, $5::jsonb, $6, true)
            """,
            "weekly-report",
            "0 0 * * 0",
            "report-job",
            2,
            json.dumps({"type": "weekly"}),
            "reports",
        )

    r = await client.post("/admin/api/v1/jobs/crons/weekly-report/run-now")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "report-job"
    assert body["version"] == 2
    assert body["status"] == "queued"
    assert body["queue"] == "reports"
    assert body["payload"] == {"type": "weekly"}

    # Audit row written.
    async with pool.acquire() as conn:
        audit_row = await conn.fetchrow(
            """
            select action, target, payload
            from admin.admin_audit
            where action = 'jobs.run_cron_now'
            order by at desc
            limit 1
            """
        )
    assert audit_row is not None
    assert audit_row["action"] == "jobs.run_cron_now"
    assert audit_row["target"] == "weekly-report"

    # Clean up.
    async with pool.acquire() as conn:
        await conn.execute("set local role service_role")
        await conn.execute("delete from jobs.cron_schedules")
