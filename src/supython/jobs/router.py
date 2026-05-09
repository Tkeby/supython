"""Jobs REST API — versioned under /jobs/v1."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from .. import db
from ..tokens import decode_access_token
from .schemas import EnqueueRequest, EnqueueResult, JobResponse
from .service import JobError, cancel, enqueue, get_job, list_jobs, retry

router = APIRouter(prefix="/jobs/v1", tags=["jobs"])


async def _service_role_required(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[7:]
    try:
        claims = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token") from None
    if claims.get("role") != "service_role":
        raise HTTPException(status_code=403, detail="service_role required")
    return token


def _to_response(record) -> JobResponse:
    return JobResponse(
        id=record.id,
        name=record.name,
        version=record.version,
        status=record.status,
        payload=record.payload,
        queue=record.queue,
        user_id=record.user_id,
        attempts=record.attempts,
        max_attempts=record.max_attempts,
        run_at=record.run_at,
        finished_at=record.finished_at,
        created_at=record.created_at,
        last_error=record.last_error,
    )


@router.post("/enqueue", response_model=EnqueueResult)
async def enqueue_endpoint(
    payload: EnqueueRequest,
    _token: Annotated[str, Depends(_service_role_required)],
) -> EnqueueResult:
    async with db.as_service_role() as conn:
        try:
            return await enqueue(
                conn,
                name=payload.name,
                payload=payload.payload,
                queue=payload.queue,
                idempotency_key=payload.idempotency_key,
                user_id=payload.user_id,
                max_attempts=payload.max_attempts,
                backoff=payload.backoff,
                backoff_base_s=payload.backoff_base_s,
                backoff_max_s=payload.backoff_max_s,
                run_at=payload.run_at,
                version=payload.version,
                role=payload.role,
                claims_from=payload.claims_from,
            )
        except JobError as exc:
            raise HTTPException(
                status_code=exc.status,
                detail={"code": exc.code, "message": exc.message},
            ) from exc


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs_endpoint(
    _token: Annotated[str, Depends(_service_role_required)],
    status: str | None = None,
    queue: str | None = None,
    name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[JobResponse]:
    async with db.as_service_role() as conn:
        records = await list_jobs(
            conn, status=status, queue=queue, name=name, limit=limit, offset=offset
        )
        return [_to_response(r) for r in records]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_endpoint(
    job_id: UUID,
    _token: Annotated[str, Depends(_service_role_required)],
) -> JobResponse:
    async with db.as_service_role() as conn:
        record = await get_job(conn, job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="job not found")
        return _to_response(record)


@router.post("/jobs/{job_id}/cancel", status_code=204)
async def cancel_job_endpoint(
    job_id: UUID,
    _token: Annotated[str, Depends(_service_role_required)],
) -> None:
    async with db.as_service_role() as conn:
        try:
            await cancel(conn, job_id)
        except JobError as exc:
            raise HTTPException(
                status_code=exc.status,
                detail={"code": exc.code, "message": exc.message},
            ) from exc


@router.post("/jobs/{job_id}/retry", status_code=204)
async def retry_job_endpoint(
    job_id: UUID,
    _token: Annotated[str, Depends(_service_role_required)],
) -> None:
    async with db.as_service_role() as conn:
        try:
            await retry(conn, job_id)
        except JobError as exc:
            raise HTTPException(
                status_code=exc.status,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
