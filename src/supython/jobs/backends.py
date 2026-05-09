"""Job backend protocol + default Postgres-queue implementation.

Collapsed from a two-file ``backends/`` package into a single module during the
v0.5 grooming pass: until a second backend actually lands (arq / dramatiq as
optional extras), the package added no structure the Protocol does not already
express. When an additional backend is introduced it should be promoted back
to a package.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

from .. import db
from ..settings import Settings, get_settings
from .schemas import EnqueueResult, JobRecord
from .service import cancel as svc_cancel
from .service import enqueue as svc_enqueue
from .service import get_job as svc_get_job
from .service import list_jobs as svc_list_jobs

if TYPE_CHECKING:  # pragma: no cover
    from .worker import Worker

logger = logging.getLogger(__name__)


@runtime_checkable
class JobBackend(Protocol):
    async def enqueue(self, **kwargs) -> EnqueueResult: ...
    async def run(self) -> None: ...
    async def cancel(self, job_id: UUID) -> None: ...
    async def retry(self, job_id: UUID) -> None: ...
    async def list_jobs(self, **kwargs) -> list[JobRecord]: ...
    async def get_job(self, job_id: UUID) -> JobRecord | None: ...
    async def health_check(self) -> dict: ...


class PgQueueBackend:
    """Default backend — polls ``jobs.jobs`` with ``FOR UPDATE SKIP LOCKED``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._worker: Worker | None = None

    async def enqueue(self, **kwargs) -> EnqueueResult:
        async with db.as_service_role() as conn:
            return await svc_enqueue(conn, **kwargs)

    async def run(self) -> None:
        from .worker import Worker

        self._worker = Worker(self._settings)
        await self._worker.start()

    async def cancel(self, job_id: UUID) -> None:
        async with db.as_service_role() as conn:
            await svc_cancel(conn, job_id)

    async def retry(self, job_id: UUID) -> None:
        from .service import mark_failed_retry

        async with db.as_service_role() as conn:
            record = await svc_get_job(conn, job_id)
            if record is None:
                return
            await mark_failed_retry(
                conn,
                job_id,
                attempts=record.attempts,
                backoff=record.backoff,
                backoff_base_s=record.backoff_base_s,
                backoff_max_s=record.backoff_max_s,
            )

    async def list_jobs(self, **kwargs) -> list[JobRecord]:
        async with db.as_service_role() as conn:
            return await svc_list_jobs(conn, **kwargs)

    async def get_job(self, job_id: UUID) -> JobRecord | None:
        async with db.as_service_role() as conn:
            return await svc_get_job(conn, job_id)

    async def health_check(self) -> dict:
        try:
            async with db.as_service_role() as conn:
                await conn.fetchval("select 1 from jobs.jobs limit 1")
            return {"backend": "pg", "healthy": True}
        except Exception as exc:
            return {"backend": "pg", "healthy": False, "detail": str(exc)}


def get_backend(settings: Settings | None = None) -> JobBackend:
    s = settings or get_settings()
    return PgQueueBackend(s)
