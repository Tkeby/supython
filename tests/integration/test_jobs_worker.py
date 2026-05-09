"""Tests for the Worker dispatcher — success, retry, failure paths."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from supython.jobs.decorators import job
from supython.jobs.registry import reset_registry
from supython.jobs.schemas import JobRecord
from supython.jobs.worker import Worker
from supython.settings import get_settings


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_registry()
    yield
    reset_registry()


def _make_record(**overrides) -> JobRecord:
    from uuid import uuid4

    defaults = {
        "id": uuid4(),
        "name": "test_job",
        "version": 1,
        "status": "running",
        "attempts": 1,
        "max_attempts": 3,
        "backoff": "exponential",
        "backoff_base_s": 5.0,
        "backoff_max_s": 300.0,
    }
    defaults.update(overrides)
    return JobRecord(**defaults)


@pytest.mark.usefixtures("pool")
async def test_worker_dispatch_success(pool):
    handled = []

    @job("test_job", version=1)
    async def handler(ctx, payload):
        handled.append(payload)

    record = _make_record(name="test_job")
    settings = get_settings()
    worker = Worker(settings)

    with patch("supython.jobs.worker.db") as mock_db:
        mock_conn = AsyncMock()
        mock_db.as_service_role.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.as_service_role.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("supython.jobs.worker.build_job_ctx") as mock_ctx:
            mock_ctx.return_value = AsyncMock()

            with patch("supython.jobs.worker.mark_succeeded"):
                await worker._dispatch(record)

    assert len(handled) == 1


@pytest.mark.usefixtures("pool")
async def test_worker_dispatch_unknown_job():
    record = _make_record(name="nonexistent")
    settings = get_settings()
    worker = Worker(settings)

    with patch("supython.jobs.worker.db") as mock_db:
        mock_conn = AsyncMock()
        mock_db.as_service_role.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.as_service_role.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("supython.jobs.worker.mark_failed_final") as mock_fail:
            await worker._dispatch(record)
            mock_fail.assert_called_once()


@pytest.mark.usefixtures("pool")
async def test_worker_dispatch_handler_error_retries():
    @job("flaky_job", version=1)
    async def handler(ctx, payload):
        raise RuntimeError("boom")

    record = _make_record(name="flaky_job", attempts=1, max_attempts=3)
    settings = get_settings()
    worker = Worker(settings)

    with patch("supython.jobs.worker.db") as mock_db:
        mock_conn = AsyncMock()
        mock_db.as_service_role.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.as_service_role.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("supython.jobs.worker.build_job_ctx") as mock_ctx:
            mock_ctx.return_value = AsyncMock()

            with patch("supython.jobs.worker.mark_failed_retry") as mock_retry:
                await worker._dispatch(record)
                mock_retry.assert_called_once()


@pytest.mark.usefixtures("pool")
async def test_worker_dispatch_max_attempts_final():
    @job("dead_job", version=1)
    async def handler(ctx, payload):
        raise RuntimeError("dead")

    record = _make_record(name="dead_job", attempts=3, max_attempts=3)
    settings = get_settings()
    worker = Worker(settings)

    with patch("supython.jobs.worker.db") as mock_db:
        mock_conn = AsyncMock()
        mock_db.as_service_role.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.as_service_role.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("supython.jobs.worker.build_job_ctx") as mock_ctx:
            mock_ctx.return_value = AsyncMock()

            with patch("supython.jobs.worker.mark_failed_final") as mock_fail:
                await worker._dispatch(record)
                mock_fail.assert_called_once()


@pytest.mark.usefixtures("pool")
async def test_worker_respects_concurrency():
    running = []
    max_concurrent = 0

    @job("concurrent_job", version=1)
    async def handler(ctx, payload):
        running.append(1)
        nonlocal max_concurrent
        max_concurrent = max(max_concurrent, len(running))
        await asyncio.sleep(0.1)
        running.pop()

    settings = get_settings()
    settings.jobs_concurrency = 2
    worker = Worker(settings)

    records = [_make_record(name="concurrent_job") for _ in range(5)]
    poll_iter = iter(records)

    async def fake_poll():
        try:
            return [next(poll_iter)]
        except StopIteration:
            return []

    with (
        patch.object(worker, "_poll", fake_poll),
        patch("supython.jobs.worker.db") as mock_db,
        patch("supython.jobs.worker.build_job_ctx") as mock_ctx,
        patch("supython.jobs.worker.mark_succeeded"),
    ):
        mock_conn = AsyncMock()
        mock_db.as_service_role.return_value.__aenter__ = AsyncMock(
            return_value=mock_conn
        )
        mock_db.as_service_role.return_value.__aexit__ = AsyncMock(
            return_value=False
        )
        mock_ctx.return_value = AsyncMock()

        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.15)
        await worker.stop()
        await task

    assert max_concurrent <= 2


@pytest.mark.usefixtures("pool")
async def test_worker_version_fallback():
    @job("fallback_job", version=2)
    async def handler(ctx, payload):
        pass

    record = _make_record(name="fallback_job", version=1)
    settings = get_settings()
    worker = Worker(settings)

    with patch("supython.jobs.worker.db") as mock_db:
        mock_conn = AsyncMock()
        mock_db.as_service_role.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.as_service_role.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("supython.jobs.worker.build_job_ctx") as mock_ctx:
            mock_ctx.return_value = AsyncMock()

            with patch("supython.jobs.worker.mark_succeeded") as mock_ok:
                await worker._dispatch(record)
                mock_ok.assert_called_once()
