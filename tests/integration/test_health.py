"""Tests for the deep health probes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from supython.health import (
    CheckResult,
    _check_broker,
    _check_database,
    _check_pg_cron,
    _check_postgrest,
    _check_worker,
    run_checks,
)

# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("pool")
async def test_check_database_ok():
    result = await _check_database()
    assert result.status == "ok"
    assert result.latency_ms is not None
    assert result.latency_ms >= 0


async def test_check_postgrest_reachable_or_not():
    # PostgREST may or may not be running in the test environment.
    result = await _check_postgrest()
    assert result.status in ("ok", "fail")
    if result.status == "ok":
        assert result.latency_ms is not None


async def test_check_broker_none():
    result = await _check_broker(None)
    assert result.status == "fail"
    assert result.detail == "broker_not_started"


async def test_check_broker_healthy():
    broker = MagicMock()
    broker.is_healthy = True
    broker.connection_count = 5
    result = await _check_broker(broker)
    assert result.status == "ok"
    assert result.detail == "connections=5"


async def test_check_broker_unhealthy():
    broker = MagicMock()
    broker.is_healthy = False
    result = await _check_broker(broker)
    assert result.status == "fail"
    assert result.detail == "listener_not_ready"


@pytest_asyncio.fixture
async def clean_worker_heartbeats(pool):
    async with pool.acquire() as conn:
        await conn.execute("delete from jobs.worker_heartbeats")
    yield
    async with pool.acquire() as conn:
        await conn.execute("delete from jobs.worker_heartbeats")


@pytest.mark.usefixtures("pool", "clean_worker_heartbeats")
async def test_check_worker_no_heartbeat():
    result = await _check_worker()
    assert result.status == "fail"
    assert result.detail == "no_worker_heartbeat"


@pytest.mark.usefixtures("pool", "clean_worker_heartbeats")
async def test_check_worker_with_fresh_heartbeat(pool):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into jobs.worker_heartbeats (worker_id, last_heartbeat, inflight)
            values ('test-worker', now(), 3)
            """
        )
    result = await _check_worker()
    assert result.status == "ok"
    assert "workers=1" in result.detail
    assert "inflight=3" in result.detail


@pytest.mark.usefixtures("pool", "clean_worker_heartbeats")
async def test_check_worker_stale_heartbeat(pool):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into jobs.worker_heartbeats (worker_id, last_heartbeat, inflight)
            values ('test-worker', now() - interval '60 seconds', 0)
            """
        )
    result = await _check_worker()
    assert result.status == "fail"
    assert "heartbeat_stale" in result.detail


@pytest.mark.usefixtures("pool", "skip_without_pg_cron")
async def test_check_pg_cron():
    result = await _check_pg_cron()
    assert result.status == "ok"
    assert "scheduled_jobs=" in result.detail


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


async def test_livez(client):
    resp = await client.get("/livez")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


async def test_readyz_200_when_healthy(client):
    with patch(
        "supython.health.run_checks",
        new=AsyncMock(
            return_value={
                "database": CheckResult(status="ok", latency_ms=1.0),
                "postgrest": CheckResult(status="ok", latency_ms=2.0),
            }
        ),
    ):
        resp = await client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "checks" in data


async def test_readyz_503_when_unhealthy(client):
    with patch(
        "supython.health.run_checks",
        new=AsyncMock(
            return_value={
                "database": CheckResult(status="ok", latency_ms=1.0),
                "postgrest": CheckResult(status="fail", detail="timeout"),
            }
        ),
    ):
        resp = await client.get("/readyz")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "fail"
    assert data["checks"]["postgrest"]["status"] == "fail"


async def test_health_returns_full_detail(client):
    with patch(
        "supython.health.run_checks",
        new=AsyncMock(
            return_value={
                "database": CheckResult(status="ok", latency_ms=1.0),
                "postgrest": CheckResult(status="ok", latency_ms=2.0),
            }
        ),
    ):
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "checks" in data
    assert "postgrest_url" in data
    assert "timestamp" in data


async def test_health_degraded_when_check_fails(client):
    with patch(
        "supython.health.run_checks",
        new=AsyncMock(
            return_value={
                "database": CheckResult(status="ok", latency_ms=1.0),
                "postgrest": CheckResult(status="fail", detail="timeout"),
            }
        ),
    ):
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def test_run_checks_includes_broker_when_realtime_enabled(app):
    original_broker = getattr(app.state, "broker", None)
    mock_broker = MagicMock()
    mock_broker.is_healthy = True
    mock_broker.connection_count = 2
    app.state.broker = mock_broker

    mock_request = MagicMock()
    mock_request.app = app

    try:
        with patch("supython.health.get_settings") as mock_settings:
            s = MagicMock()
            s.realtime_enabled = True
            s.jobs_enabled = False
            s.jobs_cron_backend = "pg_cron"
            mock_settings.return_value = s

            with patch(
                "supython.health._check_database",
                new=AsyncMock(return_value=CheckResult(status="ok")),
            ), patch(
                "supython.health._check_postgrest",
                new=AsyncMock(return_value=CheckResult(status="ok")),
            ):
                result = await run_checks(mock_request)

        assert "broker" in result
        assert result["broker"].status == "ok"
        assert result["broker"].detail == "connections=2"
    finally:
        app.state.broker = original_broker


async def test_run_checks_includes_worker_and_pg_cron_when_jobs_enabled(app):
    mock_request = MagicMock()
    mock_request.app = app

    with patch("supython.health.get_settings") as mock_settings:
        s = MagicMock()
        s.realtime_enabled = False
        s.jobs_enabled = True
        s.jobs_cron_backend = "pg_cron"
        mock_settings.return_value = s

        with patch(
            "supython.health._check_database",
            new=AsyncMock(return_value=CheckResult(status="ok")),
        ), patch(
            "supython.health._check_postgrest",
            new=AsyncMock(return_value=CheckResult(status="ok")),
        ), patch(
            "supython.health._check_worker",
            new=AsyncMock(return_value=CheckResult(status="ok")),
        ), patch(
            "supython.health._check_pg_cron",
            new=AsyncMock(return_value=CheckResult(status="ok")),
        ):
            result = await run_checks(mock_request)

    assert "worker" in result
    assert "pg_cron" in result
    assert result["worker"].status == "ok"
    assert result["pg_cron"].status == "ok"


async def test_run_checks_skips_optional_when_disabled(app):
    mock_request = MagicMock()
    mock_request.app = app

    with patch("supython.health.get_settings") as mock_settings:
        s = MagicMock()
        s.realtime_enabled = False
        s.jobs_enabled = False
        s.jobs_cron_backend = "pg_cron"
        mock_settings.return_value = s

        with patch(
            "supython.health._check_database",
            new=AsyncMock(return_value=CheckResult(status="ok")),
        ), patch(
            "supython.health._check_postgrest",
            new=AsyncMock(return_value=CheckResult(status="ok")),
        ):
            result = await run_checks(mock_request)

    assert set(result.keys()) == {"database", "postgrest"}
