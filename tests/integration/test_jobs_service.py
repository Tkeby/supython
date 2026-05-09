"""Tests for jobs.service — enqueue, claim, mark, cancel, list."""

import pytest
import pytest_asyncio

from supython import db
from supython.jobs.service import (
    JobError,
    _compute_backoff,
    cancel,
    claim_next,
    enqueue,
    get_job,
    list_jobs,
    mark_failed_final,
    mark_failed_retry,
    mark_succeeded,
)


@pytest_asyncio.fixture
async def conn(pool):
    async with db.as_service_role() as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def _clean_jobs(conn):
    await conn.execute("delete from jobs.jobs")
    yield
    await conn.execute("delete from jobs.jobs")


async def test_enqueue_returns_is_new(conn):
    result = await enqueue(conn, name="test_job")
    assert result.is_new is True
    assert result.job.name == "test_job"
    assert result.job.status == "queued"


async def test_enqueue_with_payload(conn):
    result = await enqueue(conn, name="test_job", payload={"key": "val"})
    assert result.job.payload == {"key": "val"}


async def test_enqueue_idempotency(conn):
    first = await enqueue(conn, name="test_job", idempotency_key="key-1")
    assert first.is_new is True
    second = await enqueue(conn, name="test_job", idempotency_key="key-1")
    assert second.is_new is False
    assert second.job.id == first.job.id


async def test_claim_next_returns_job(conn):
    await enqueue(conn, name="test_job")
    jobs = await claim_next(conn, worker_id="w1")
    assert len(jobs) == 1
    assert jobs[0].status == "running"
    assert jobs[0].locked_by == "w1"
    assert jobs[0].attempts == 1


async def test_claim_next_empty(conn):
    jobs = await claim_next(conn, worker_id="w1")
    assert jobs == []


async def test_mark_succeeded(conn):
    result = await enqueue(conn, name="test_job")
    await mark_succeeded(conn, result.job.id)
    job = await get_job(conn, result.job.id)
    assert job is not None
    assert job.status == "succeeded"
    assert job.finished_at is not None


async def test_mark_failed_retry(conn):
    result = await enqueue(conn, name="test_job")
    await mark_failed_retry(
        conn,
        result.job.id,
        attempts=1,
        backoff="exponential",
        backoff_base_s=5.0,
        backoff_max_s=300.0,
    )
    job = await get_job(conn, result.job.id)
    assert job is not None
    assert job.status == "queued"
    assert job.run_at is not None


async def test_mark_failed_final(conn):
    result = await enqueue(conn, name="test_job")
    await mark_failed_final(conn, result.job.id)
    job = await get_job(conn, result.job.id)
    assert job is not None
    assert job.status == "failed"
    assert job.finished_at is not None


async def test_cancel(conn):
    result = await enqueue(conn, name="test_job")
    await cancel(conn, result.job.id)
    job = await get_job(conn, result.job.id)
    assert job is not None
    assert job.status == "cancelled"


async def test_cancel_terminal_raises(conn):
    result = await enqueue(conn, name="test_job")
    await mark_succeeded(conn, result.job.id)
    # ``pytest.raises(match=...)`` checks against str(exception), which is the
    # ``JobError.message`` (the ``.code`` attribute is checked below). The
    # pre-grooming assertion matched against ``"cancel_failed"`` (the code)
    # and so was effectively dead.
    with pytest.raises(JobError, match="already terminal") as excinfo:
        await cancel(conn, result.job.id)
    assert excinfo.value.code == "cancel_failed"
    assert excinfo.value.status == 404


async def test_list_jobs(conn):
    await enqueue(conn, name="job_a", queue="q1")
    await enqueue(conn, name="job_b", queue="q2")
    all_jobs = await list_jobs(conn)
    assert len(all_jobs) == 2
    q1_jobs = await list_jobs(conn, queue="q1")
    assert len(q1_jobs) == 1
    assert q1_jobs[0].name == "job_a"


async def test_list_jobs_by_status(conn):
    r = await enqueue(conn, name="test_job")
    await mark_succeeded(conn, r.job.id)
    succeeded = await list_jobs(conn, status="succeeded")
    assert len(succeeded) == 1
    queued = await list_jobs(conn, status="queued")
    assert len(queued) == 0


async def test_get_job(conn):
    result = await enqueue(conn, name="test_job")
    job = await get_job(conn, result.job.id)
    assert job is not None
    assert job.name == "test_job"


async def test_get_job_not_found(conn):
    from uuid import uuid4

    assert await get_job(conn, uuid4()) is None


def test_compute_backoff_exponential():
    from datetime import datetime

    dt = _compute_backoff(1, "exponential", 5.0, 300.0)
    assert isinstance(dt, datetime)

    dt2 = _compute_backoff(3, "exponential", 5.0, 300.0)
    assert dt2 > dt


def test_compute_backoff_linear():
    dt = _compute_backoff(3, "linear", 5.0, 300.0)
    from datetime import datetime

    assert isinstance(dt, datetime)


def test_compute_backoff_constant():
    dt = _compute_backoff(5, "constant", 10.0, 300.0)
    from datetime import datetime

    assert isinstance(dt, datetime)
