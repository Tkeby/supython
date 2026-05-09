"""Admin service layer for the jobs queue surface.

Pure async functions over ``asyncpg.Connection``. No FastAPI imports.
"""

import json
import logging
from uuid import UUID

import asyncpg

from ...jobs import service as jobs_service
from ...jobs.schemas import JobRecord
from ..errors import AdminError
from ..schemas import AdminCronRow, AdminJobRow, AdminJobsPage, PgCronHealth

logger = logging.getLogger(__name__)


def _row_to_admin_job(row: asyncpg.Record) -> AdminJobRow:
    raw_payload = row["payload"]
    if isinstance(raw_payload, str):
        raw_payload = json.loads(raw_payload) if raw_payload else {}
    return AdminJobRow(
        id=row["id"],
        name=row["name"],
        version=row["version"],
        status=row["status"],
        payload=raw_payload,
        queue=row["queue"],
        user_id=row["user_id"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        run_at=row["run_at"],
        locked_at=row["locked_at"],
        locked_by=row["locked_by"],
        role=row["role"],
        finished_at=row["finished_at"],
        created_at=row["created_at"],
        last_error=row.get("last_error"),
    )


def _job_record_to_admin_job(rec: JobRecord) -> AdminJobRow:
    return AdminJobRow(
        id=rec.id,
        name=rec.name,
        version=rec.version,
        status=rec.status,
        payload=rec.payload,
        queue=rec.queue,
        user_id=rec.user_id,
        attempts=rec.attempts,
        max_attempts=rec.max_attempts,
        run_at=rec.run_at,
        locked_at=rec.locked_at,
        locked_by=rec.locked_by,
        role=rec.role,
        finished_at=rec.finished_at,
        created_at=rec.created_at,
        last_error=rec.last_error,
    )


def _row_to_admin_cron(row: asyncpg.Record) -> AdminCronRow:
    raw_payload = row["payload"]
    if isinstance(raw_payload, str):
        raw_payload = json.loads(raw_payload) if raw_payload else {}
    return AdminCronRow(
        id=row["id"],
        name=row["name"],
        cron_expr=row["cron_expr"],
        job_name=row["job_name"],
        job_version=row["job_version"],
        payload=raw_payload,
        queue=row["queue"],
        enabled=row["enabled"],
        last_fire_at=row["last_fire_at"],
        created_at=row["created_at"],
        pg_cron_active=row.get("pg_cron_active"),
    )


async def _fetch_admin_job(conn: asyncpg.Connection, job_id: UUID) -> AdminJobRow:
    row = await conn.fetchrow(
        """
        select id, name, version, status, payload, queue, user_id,
               attempts, max_attempts, run_at, locked_at, locked_by,
               role, finished_at, created_at, last_error
        from jobs.jobs
        where id = $1
        """,
        job_id,
    )
    if row is None:
        raise AdminError("job_not_found", f"job {job_id} not found", 404)
    return _row_to_admin_job(row)


async def list_queue(
    conn: asyncpg.Connection,
    *,
    status: str | None = None,
    queue: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AdminJobsPage:
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

    where = f"where {' and '.join(clauses)}" if clauses else ""

    rows = await conn.fetch(
        f"""
        select id, name, version, status, payload, queue, user_id,
               attempts, max_attempts, run_at, locked_at, locked_by,
               role, finished_at, created_at, last_error
        from jobs.jobs
        {where}
        order by created_at desc
        limit ${idx} offset ${idx + 1}
        """,
        *args,
        limit,
        offset,
    )

    total = await conn.fetchval(
        f"select count(*) from jobs.jobs {where}",
        *args,
    )

    counts = await count_by_status(conn)

    return AdminJobsPage(
        rows=[_row_to_admin_job(r) for r in rows],
        total=total or 0,
        counts=counts,
    )


async def count_by_status(conn: asyncpg.Connection) -> dict[str, int]:
    rows = await conn.fetch(
        """
        select status, count(*) as cnt
        from jobs.jobs
        group by status
        """
    )
    return {r["status"]: r["cnt"] for r in rows}


async def retry_job(conn: asyncpg.Connection, job_id: UUID) -> AdminJobRow:
    try:
        await jobs_service.retry(conn, job_id)
    except jobs_service.JobError as exc:
        raise AdminError(exc.code, exc.message, exc.status) from exc
    return await _fetch_admin_job(conn, job_id)


async def cancel_job(conn: asyncpg.Connection, job_id: UUID) -> AdminJobRow:
    try:
        await jobs_service.cancel(conn, job_id)
    except jobs_service.JobError as exc:
        raise AdminError(exc.code, exc.message, exc.status) from exc
    return await _fetch_admin_job(conn, job_id)


async def list_crons(conn: asyncpg.Connection) -> list[AdminCronRow]:
    pg_cron_installed = await _pg_cron_installed(conn)

    rows = await conn.fetch(
        """
        select id, name, cron_expr, job_name, job_version, payload,
               queue, enabled, last_fire_at, created_at
        from jobs.cron_schedules
        order by name
        """
    )

    pg_cron_map: dict[str, bool] = {}
    if pg_cron_installed:
        cron_rows = await conn.fetch(
            """
            select jobname, active
            from cron.job
            """
        )
        pg_cron_map = {r["jobname"]: r["active"] for r in cron_rows}

    results: list[AdminCronRow] = []
    for r in rows:
        cron = _row_to_admin_cron(r)
        if pg_cron_installed:
            cron.pg_cron_active = pg_cron_map.get(r["name"])
        results.append(cron)

    return results


async def pg_cron_health(conn: asyncpg.Connection) -> PgCronHealth:
    installed = await _pg_cron_installed(conn)
    if not installed:
        return PgCronHealth(installed=False)

    ext_version = await conn.fetchval(
        """
        select extversion from pg_extension where extname = 'pg_cron'
        """
    )

    try:
        active_jobs = (
            await conn.fetchval(
                """
            select count(*) from cron.job where active
            """
            )
            or 0
        )
    except Exception:
        logger.warning("pg_cron_health: cron.job not accessible", exc_info=True)
        active_jobs = 0

    return PgCronHealth(
        installed=True,
        active_jobs=active_jobs,
        extension_version=ext_version,
    )


async def run_cron_now(conn: asyncpg.Connection, cron_name: str) -> AdminJobRow:
    row = await conn.fetchrow(
        """
        select id, name, job_name, job_version, payload, queue, enabled
        from jobs.cron_schedules
        where name = $1
        """,
        cron_name,
    )
    if row is None:
        raise AdminError("cron_not_found", f"cron schedule {cron_name!r} not found", 404)
    if not row["enabled"]:
        raise AdminError("cron_disabled", f"cron schedule {cron_name!r} is disabled", 409)

    raw_payload = row["payload"]
    if isinstance(raw_payload, str):
        raw_payload = json.loads(raw_payload) if raw_payload else {}

    try:
        result = await jobs_service.enqueue(
            conn,
            name=row["job_name"],
            payload=raw_payload,
            queue=row["queue"],
            version=row["job_version"],
        )
    except jobs_service.JobError as exc:
        raise AdminError(exc.code, exc.message, exc.status) from exc

    return _job_record_to_admin_job(result.job)


async def _pg_cron_installed(conn: asyncpg.Connection) -> bool:
    val = await conn.fetchval(
        """
        select exists(
            select 1 from pg_extension where extname = 'pg_cron'
        )
        """
    )
    return bool(val)
