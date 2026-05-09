"""Deep health probes: /livez, /readyz, /health."""

import asyncio
import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import __version__, db
from .settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta"])
CHECK_TIMEOUT_S = 2.0
WORKER_HEARTBEAT_MAX_AGE_S = 30.0

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CheckResult(BaseModel):
    status: str  # "ok" | "fail"
    detail: str | None = None
    latency_ms: float | None = None


class ReadyzResponse(BaseModel):
    status: str  # "ok" | "fail"
    checks: dict[str, CheckResult]


class HealthResponse(BaseModel):
    status: str
    version: str
    checks: dict[str, CheckResult]
    postgrest_url: str
    timestamp: str


class LivezResponse(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Check functions (pure async, no FastAPI deps)
# ---------------------------------------------------------------------------


async def _check_database() -> CheckResult:
    """Run select 1 with one total timeout."""
    started = perf_counter()
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            async with db.acquire() as conn:
                await conn.fetchval("select 1")
    except TimeoutError:
        return CheckResult(status="fail", detail="timeout")
    except Exception as exc:
        return CheckResult(status="fail", detail=str(exc))
    elapsed = (perf_counter() - started) * 1000
    return CheckResult(status="ok", latency_ms=round(elapsed, 1))


async def _check_postgrest() -> CheckResult:
    """HEAD / with one total timeout."""
    settings = get_settings()
    started = perf_counter()
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_S) as client:
                resp = await client.head(f"{settings.postgrest_url.rstrip('/')}/")
        if resp.status_code >= 500:
            return CheckResult(
                status="fail",
                detail=f"postgrest_status={resp.status_code}",
            )
    except TimeoutError:
        return CheckResult(status="fail", detail="timeout")
    except Exception as exc:
        return CheckResult(status="fail", detail=str(exc))
    elapsed = (perf_counter() - started) * 1000
    return CheckResult(status="ok", latency_ms=round(elapsed, 1))


async def _check_broker(broker: Any | None) -> CheckResult:
    """Broker listener task alive and connection open."""
    if broker is None:
        return CheckResult(status="fail", detail="broker_not_started")
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            if not broker.is_healthy:
                return CheckResult(status="fail", detail="listener_not_ready")
            connection_count = broker.connection_count
    except TimeoutError:
        return CheckResult(status="fail", detail="timeout")
    except Exception as exc:
        return CheckResult(status="fail", detail=str(exc))
    return CheckResult(status="ok", detail=f"connections={connection_count}")


async def _check_worker() -> CheckResult:
    """Check freshness of the newest worker heartbeat row."""
    started = perf_counter()
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            async with db.as_service_role() as conn:
                row = await conn.fetchrow(
                    """
                    select
                        count(*)::int as workers,
                        coalesce(sum(inflight), 0)::int as inflight,
                        extract(epoch from now() - max(last_heartbeat))::float as age_s
                    from jobs.worker_heartbeats
                    """
                )
    except TimeoutError:
        return CheckResult(status="fail", detail="timeout")
    except Exception as exc:
        return CheckResult(status="fail", detail=str(exc))

    if row is None or row["workers"] == 0 or row["age_s"] is None:
        return CheckResult(status="fail", detail="no_worker_heartbeat")

    age_s = float(row["age_s"])
    if age_s > WORKER_HEARTBEAT_MAX_AGE_S:
        return CheckResult(status="fail", detail=f"heartbeat_stale age_s={age_s:.1f}")

    elapsed = (perf_counter() - started) * 1000
    return CheckResult(
        status="ok",
        detail=f"workers={row['workers']} inflight={row['inflight']} age_s={age_s:.1f}",
        latency_ms=round(elapsed, 1),
    )


async def _check_pg_cron() -> CheckResult:
    """pg_cron extension present and cron.job readable."""
    started = perf_counter()
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            async with db.as_service_role() as conn:
                has_ext = await conn.fetchval(
                    "select exists(select 1 from pg_extension where extname = 'pg_cron')"
                )
                if not has_ext:
                    return CheckResult(status="fail", detail="pg_cron_extension_missing")
                count = await conn.fetchval("select count(*) from cron.job")
    except TimeoutError:
        return CheckResult(status="fail", detail="timeout")
    except Exception as exc:
        return CheckResult(status="fail", detail=str(exc))
    elapsed = (perf_counter() - started) * 1000
    return CheckResult(
        status="ok",
        detail=f"scheduled_jobs={count}",
        latency_ms=round(elapsed, 1),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def run_checks(request: Request) -> dict[str, CheckResult]:
    """Run all applicable checks concurrently and return results."""
    settings = get_settings()
    app_state = request.app.state

    coros: dict[str, Any] = {
        "database": _check_database(),
        "postgrest": _check_postgrest(),
    }
    if settings.realtime_enabled:
        coros["broker"] = _check_broker(getattr(app_state, "broker", None))
    if settings.jobs_enabled:
        coros["worker"] = _check_worker()
        if settings.jobs_cron_backend == "pg_cron":
            coros["pg_cron"] = _check_pg_cron()

    # Gather all checks concurrently
    names = list(coros.keys())
    results = await asyncio.gather(*coros.values())
    return dict(zip(names, results, strict=True))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/livez", response_model=LivezResponse)
async def livez() -> LivezResponse:
    return LivezResponse(status="ok")


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    checks = await run_checks(request)
    all_ok = all(c.status == "ok" for c in checks.values())
    body = ReadyzResponse(
        status="ok" if all_ok else "fail",
        checks=checks,
    )
    return JSONResponse(
        content=body.model_dump(mode="json"),
        status_code=200 if all_ok else 503,
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = get_settings()
    checks = await run_checks(request)
    all_ok = all(c.status == "ok" for c in checks.values())
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        version=__version__,
        checks=checks,
        postgrest_url=settings.postgrest_url,
        timestamp=datetime.now(UTC).isoformat(),
    )
