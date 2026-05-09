"""Job worker — polls the queue and dispatches handlers.

Worst-case time-to-retry after a rolling deploy is
    jobs_drain_timeout_s + jobs_visibility_timeout_s
(~5.5 min on defaults), because a dying worker drains in-flight jobs before
exiting, and any that were mid-flight become zombies reclaimable after the
visibility timeout.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any
from uuid import UUID

from .. import db
from ..settings import Settings
from .context import build_job_ctx
from .registry import get_registry
from .service import (
    claim_next,
    mark_failed_final,
    mark_failed_retry,
    mark_succeeded,
)

if TYPE_CHECKING:  # pragma: no cover
    from .backends import JobBackend

logger = logging.getLogger(__name__)


def _build_claims(record, defn) -> dict[str, Any] | None:
    if defn.role == "service_role":
        return None
    claims: dict[str, Any] = {"role": defn.role, "aud": "authenticated"}
    if defn.claims_from:
        value = getattr(record, defn.claims_from, None)
        if value is not None:
            claims["sub"] = str(value)
    return claims


def _db_ctx(record, defn):
    claims = _build_claims(record, defn)
    if claims is None:
        return db.as_service_role()
    logger.info(
        "jobs.dispatch.role_switch",
        extra={
            "job_id": str(record.id),
            "job_name": record.name,
            "role": defn.role,
            "claims_from": defn.claims_from,
        },
    )
    return db.as_role(defn.role, claims)


class Worker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self._inflight: set[asyncio.Task] = set()
        self._stopping = False
        self._backend: JobBackend | None = None
        self._sem = asyncio.Semaphore(settings.jobs_concurrency)

    @property
    def stopping(self) -> bool:
        return self._stopping

    async def start(self) -> None:
        from .backends import get_backend

        self._backend = get_backend(self.settings)
        logger.info(
            "jobs.worker.start",
            extra={"worker_id": self.worker_id, "backend": "pg"},
        )
        poll_interval = self.settings.jobs_poll_interval_s
        while not self._stopping:
            try:
                jobs = await self._poll()
            except Exception:
                logger.exception("jobs.worker.poll_error")
                await asyncio.sleep(poll_interval)
                continue
            for record in jobs:
                await self._sem.acquire()
                task = asyncio.create_task(self._dispatch_with_release(record))
                self._inflight.add(task)
                task.add_done_callback(self._inflight.discard)
            await self._heartbeat(len(self._inflight))
            if not jobs:
                await asyncio.sleep(poll_interval)

    async def stop(self) -> None:
        self._stopping = True
        logger.info("jobs.worker.stopping", extra={"worker_id": self.worker_id})
        if self._inflight:
            done, pending = await asyncio.wait(
                self._inflight, timeout=self.settings.jobs_drain_timeout_s
            )
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        logger.info("jobs.worker.stopped", extra={"worker_id": self.worker_id})

    async def _heartbeat(self, inflight: int) -> None:
        """Upsert heartbeat row so /readyz can check worker freshness."""
        try:
            async with db.as_service_role() as conn:
                await conn.execute(
                    """
                    insert into jobs.worker_heartbeats (worker_id, last_heartbeat, inflight)
                    values ($1, now(), $2)
                    on conflict (worker_id) do update set
                        last_heartbeat = now(),
                        inflight = excluded.inflight
                    """,
                    self.worker_id,
                    inflight,
                )
        except Exception:
            logger.debug("jobs.worker.heartbeat_failed", exc_info=True)

    async def _poll(self):
        async with db.as_service_role() as conn:
            return await claim_next(
                conn,
                queue=self.settings.jobs_queue_default,
                worker_id=self.worker_id,
                visibility_timeout_ms=int(self.settings.jobs_visibility_timeout_s * 1000),
                zombie_batch=self.settings.jobs_visibility_reclaim_batch,
            )

    async def _dispatch_with_release(self, record) -> None:
        try:
            await self._dispatch(record)
        finally:
            self._sem.release()

    async def _dispatch(self, record) -> None:
        job_id: UUID = record.id
        name: str = record.name
        attempt: int = record.attempts

        logger.info(
            "jobs.dispatch.start",
            extra={"job_id": str(job_id), "job_name": name, "attempt": attempt},
        )

        registry = get_registry()
        defn = registry.get(name, record.version)
        if defn is None:
            defn = registry.get_latest(name)
        if defn is None:
            async with db.as_service_role() as conn:
                await mark_failed_final(
                    conn, job_id, last_error=f"unknown job: {name}"
                )
            logger.error(
                "jobs.dispatch.failed_final",
                extra={"job_id": str(job_id), "job_name": name, "reason": "unknown_job"},
            )
            return

        try:
            async with _db_ctx(record, defn) as conn:
                ctx = build_job_ctx(
                    conn=conn,
                    job_id=job_id,
                    attempt=attempt,
                    name=name,
                )
                if defn.accepts_payload:
                    await defn.handler(ctx, record.payload or {})
                else:
                    await defn.handler(ctx)
                await mark_succeeded(conn, job_id)
            logger.info(
                "jobs.dispatch.ok",
                extra={"job_id": str(job_id), "job_name": name, "attempt": attempt},
            )
        except Exception as exc:
            error_msg = str(exc)
            logger.warning(
                "jobs.dispatch.retry",
                extra={
                    "job_id": str(job_id),
                    "job_name": name,
                    "attempt": attempt,
                    "error": error_msg,
                },
            )
            async with db.as_service_role() as conn:
                if attempt >= record.max_attempts:
                    await mark_failed_final(conn, job_id, last_error=error_msg)
                    logger.error(
                        "jobs.dispatch.failed_final",
                        extra={
                            "job_id": str(job_id),
                            "job_name": name,
                            "reason": "max_attempts_exceeded",
                        },
                    )
                else:
                    await mark_failed_retry(
                        conn,
                        job_id,
                        attempts=attempt,
                        backoff=record.backoff,
                        backoff_base_s=record.backoff_base_s,
                        backoff_max_s=record.backoff_max_s,
                        last_error=error_msg,
                    )
