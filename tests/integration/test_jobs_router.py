"""Tests for the jobs REST router — list, get, cancel, retry."""

from uuid import UUID

import pytest
import pytest_asyncio

from supython import tokens
from supython.jobs.registry import reset_registry
from supython.jobs.service import enqueue


@pytest_asyncio.fixture
async def conn(pool):
    async with pool.acquire() as c:
        await c.execute("set role service_role")
        try:
            yield c
        finally:
            await c.execute("reset role")


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_registry()
    yield
    reset_registry()


@pytest_asyncio.fixture(autouse=True)
async def _clean_jobs(conn):
    await conn.execute("delete from jobs.jobs")
    yield
    await conn.execute("delete from jobs.jobs")


def _service_role_token():
    return tokens.issue_access_token(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        email="service@test.com",
        role="service_role",
    )[0]


def _user_token():
    return tokens.issue_access_token(
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        email="user@test.com",
        role="authenticated",
    )[0]


async def test_enqueue_endpoint(client, conn):
    token = _service_role_token()
    resp = await client.post(
        "/jobs/v1/enqueue",
        json={"name": "test_job", "payload": {"x": 1}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_new"] is True
    assert data["job"]["name"] == "test_job"


async def test_list_jobs_endpoint(client, conn):
    await enqueue(conn, name="list_test")
    token = _service_role_token()
    resp = await client.get(
        "/jobs/v1/jobs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


async def test_get_job_endpoint(client, conn):
    result = await enqueue(conn, name="get_test")
    token = _service_role_token()
    resp = await client.get(
        f"/jobs/v1/jobs/{result.job.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "get_test"


async def test_cancel_job_endpoint(client, conn):
    result = await enqueue(conn, name="cancel_test")
    token = _service_role_token()
    resp = await client.post(
        f"/jobs/v1/jobs/{result.job.id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204


async def test_non_service_role_cancel_rejected(client, conn):
    result = await enqueue(conn, name="forbidden_test")
    token = _user_token()
    resp = await client.post(
        f"/jobs/v1/jobs/{result.job.id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_retry_failed_job(client, conn):
    result = await enqueue(conn, name="retry_test")
    await conn.execute(
        "update jobs.jobs set status = 'failed', last_error = 'boom' where id = $1",
        result.job.id,
    )
    token = _service_role_token()
    resp = await client.post(
        f"/jobs/v1/jobs/{result.job.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    row = await conn.fetchrow(
        "select status, last_error from jobs.jobs where id = $1", result.job.id
    )
    assert row["status"] == "queued"
    assert row["last_error"] is None


async def test_retry_cancelled_job(client, conn):
    result = await enqueue(conn, name="retry_cancel_test")
    await conn.execute(
        "update jobs.jobs set status = 'cancelled' where id = $1",
        result.job.id,
    )
    token = _service_role_token()
    resp = await client.post(
        f"/jobs/v1/jobs/{result.job.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    row = await conn.fetchrow("select status from jobs.jobs where id = $1", result.job.id)
    assert row["status"] == "queued"


async def test_retry_succeeded_returns_409(client, conn):
    result = await enqueue(conn, name="retry_succ_test")
    await conn.execute(
        "update jobs.jobs set status = 'succeeded' where id = $1",
        result.job.id,
    )
    token = _service_role_token()
    resp = await client.post(
        f"/jobs/v1/jobs/{result.job.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "retry_failed"


async def test_retry_running_returns_409(client, conn):
    result = await enqueue(conn, name="retry_run_test")
    await conn.execute(
        "update jobs.jobs set status = 'running' where id = $1",
        result.job.id,
    )
    token = _service_role_token()
    resp = await client.post(
        f"/jobs/v1/jobs/{result.job.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


async def test_retry_queued_returns_409(client, conn):
    result = await enqueue(conn, name="retry_q_test")
    token = _service_role_token()
    resp = await client.post(
        f"/jobs/v1/jobs/{result.job.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


async def test_retry_not_found_returns_404(client, conn):
    token = _service_role_token()
    resp = await client.post(
        f"/jobs/v1/jobs/{UUID('00000000-0000-0000-0000-000000000099')}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
