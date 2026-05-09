"""Framework-agnostic async service functions for the jobs queue.

All functions take an asyncpg.Connection and raise JobError on failure.
No FastAPI imports here — this module is testable without HTTP.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from .schemas import EnqueueResult, JobRecord

logger = logging.getLogger(__name__)


class JobError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _row_to_record(row: asyncpg.Record) -> JobRecord:
    # asyncpg hands back jsonb columns as unparsed text unless a codec is
    # registered; registering a codec globally would touch every connection
    # in the pool, so we decode at the edge here instead.
    raw_payload = row["payload"]
    if isinstance(raw_payload, str):
        raw_payload = json.loads(raw_payload) if raw_payload else {}
    return JobRecord(
        id=row["id"],
        name=row["name"],
        version=row["version"],
        payload=raw_payload,
        queue=row["queue"],
        idempotency_key=row["idempotency_key"],
        user_id=row["user_id"],
        status=row["status"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        backoff=row["backoff"],
        backoff_base_s=row["backoff_base_s"],
        backoff_max_s=row["backoff_max_s"],
        run_at=row["run_at"],
        locked_at=row["locked_at"],
        locked_by=row["locked_by"],
        role=row["role"],
        claims_from=row["claims_from"],
        finished_at=row["finished_at"],
        created_at=row["created_at"],
        last_error=row.get("last_error"),
    )


async def enqueue(
    conn: asyncpg.Connection,
    *,
    name: str,
    payload: dict | None = None,
    queue: str = "default",
    idempotency_key: str | None = None,
    user_id: UUID | None = None,
    max_attempts: int = 3,
    backoff: str = "exponential",
    backoff_base_s: float = 5.0,
    backoff_max_s: float = 300.0,
    run_at: datetime | None = None,
    version: int = 1,
    role: str = "service_role",
    claims_from: str | None = None,
) -> EnqueueResult:
    row = await conn.fetchrow(
        """
        select (job).*, is_new
        from jobs.enqueue(
            p_name := $1,
            p_payload := $2::jsonb,
            p_queue := $3,
            p_idempotency_key := $4,
            p_user_id := $5,
            p_max_attempts := $6,
            p_backoff := $7,
            p_backoff_base_s := $8,
            p_backoff_max_s := $9,
            p_run_at := $10,
            p_version := $11,
            p_role := $12,
            p_claims_from := $13
        )
        """,
        name,
        json.dumps(payload or {}),
        queue,
        idempotency_key,
        user_id,
        max_attempts,
        backoff,
        backoff_base_s,
        backoff_max_s,
        run_at,
        version,
        role,
        claims_from,
    )
    if row is None:
        raise JobError("enqueue_failed", "enqueue returned no rows", 500)

    # ``jobs.enqueue`` has named OUT columns (``job jobs.jobs``, ``is_new bool``).
    # ``(job).*`` expands the composite to the jobs.jobs column set so the row
    # we get back is already the full record — no second round-trip needed.
    return EnqueueResult(
        job=_row_to_record(row),
        is_new=row["is_new"],
    )


async def claim_next(
    conn: asyncpg.Connection,
    *,
    queue: str = "default",
    worker_id: str = "worker-0",
    visibility_timeout_ms: int = 300000,
    zombie_batch: int = 10,
) -> list[JobRecord]:
    rows = await conn.fetch(
        """
        select *
        from jobs.claim_next(
            p_queue := $1,
            p_worker_id := $2,
            p_visibility_timeout_ms := $3,
            p_zombie_batch := $4
        )
        """,
        queue,
        worker_id,
        visibility_timeout_ms,
        zombie_batch,
    )
    return [_row_to_record(r) for r in rows]


async def mark_succeeded(conn: asyncpg.Connection, job_id: UUID) -> None:
    await conn.execute(
        """
        update jobs.jobs
        set status = 'succeeded', finished_at = now()
        where id = $1
        """,
        job_id,
    )


async def mark_failed_retry(
    conn: asyncpg.Connection,
    job_id: UUID,
    *,
    attempts: int,
    backoff: str,
    backoff_base_s: float,
    backoff_max_s: float,
    last_error: str | None = None,
) -> None:
    next_run = _compute_backoff(attempts, backoff, backoff_base_s, backoff_max_s)
    await conn.execute(
        """
        update jobs.jobs
        set status = 'queued',
            run_at = $2,
            locked_at = null,
            locked_by = null,
            last_error = $3
        where id = $1
        """,
        job_id,
        next_run,
        last_error,
    )


async def mark_failed_final(
    conn: asyncpg.Connection,
    job_id: UUID,
    *,
    last_error: str | None = None,
) -> None:
    await conn.execute(
        """
        update jobs.jobs
        set status = 'failed', finished_at = now(), last_error = $2
        where id = $1
        """,
        job_id,
        last_error,
    )


_RETRYABLE_STATUSES = ("failed", "cancelled")


async def retry(conn: asyncpg.Connection, job_id: UUID) -> None:
    result = await conn.execute(
        """
        update jobs.jobs
        set status = 'queued',
            run_at = now(),
            locked_at = null,
            locked_by = null,
            last_error = null,
            finished_at = null
        where id = $1 and status = any($2::text[])
        """,
        job_id,
        list(_RETRYABLE_STATUSES),
    )
    if result == "UPDATE 0":
        exists = await conn.fetchval(
            "select 1 from jobs.jobs where id = $1", job_id
        )
        if not exists:
            raise JobError("retry_failed", "job not found", 404)
        raise JobError(
            "retry_failed",
            f"job is not in a retryable state (must be one of {list(_RETRYABLE_STATUSES)})",
            409,
        )


async def cancel(conn: asyncpg.Connection, job_id: UUID) -> None:
    result = await conn.execute(
        """
        update jobs.jobs
        set status = 'cancelled', finished_at = now()
        where id = $1 and status in ('queued', 'running')
        """,
        job_id,
    )
    if result == "UPDATE 0":
        raise JobError("cancel_failed", "job not found or already terminal", 404)


async def list_jobs(
    conn: asyncpg.Connection,
    *,
    status: str | None = None,
    queue: str | None = None,
    name: str | None = None,
    user_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[JobRecord]:
    clauses: list[str] = []
    args: list = []
    idx = 1

    if status is not None:
        clauses.append(f"status = ${idx}")
        args.append(status)
        idx += 1
    if queue is not None:
        clauses.append(f"queue = ${idx}")
        args.append(queue)
        idx += 1
    if name is not None:
        clauses.append(f"name = ${idx}")
        args.append(name)
        idx += 1
    if user_id is not None:
        clauses.append(f"user_id = ${idx}")
        args.append(user_id)
        idx += 1

    where = f"where {' and '.join(clauses)}" if clauses else ""
    rows = await conn.fetch(
        f"""
        select * from jobs.jobs
        {where}
        order by created_at desc
        limit ${idx} offset ${idx + 1}
        """,
        *args,
        limit,
        offset,
    )
    return [_row_to_record(r) for r in rows]


async def get_job(conn: asyncpg.Connection, job_id: UUID) -> JobRecord | None:
    row = await conn.fetchrow("select * from jobs.jobs where id = $1", job_id)
    return _row_to_record(row) if row else None


def _compute_backoff(
    attempts: int,
    backoff: str,
    base_s: float,
    max_s: float,
) -> datetime:
    if backoff == "constant":
        delay = base_s
    elif backoff == "linear":
        delay = base_s * attempts
    else:
        delay = min(base_s * (2 ** (attempts - 1)), max_s)
    return datetime.now(UTC) + timedelta(seconds=delay)
