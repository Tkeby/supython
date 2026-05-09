import ipaddress
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request

from ... import db
from ...storage.backends import get_backend
from .. import audit
from ..deps import require_admin
from ..errors import AdminError, to_http
from ..schemas import (
    AdminBucket,
    AdminObjectsPage,
    AdminSignedUrlResponse,
    AdminSignObjectRequest,
)
from . import service_storage

router = APIRouter(prefix="/admin/api/v1/storage", tags=["admin.storage"])


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    try:
        ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    return request.client.host


@router.get("/buckets", response_model=list[AdminBucket])
async def list_buckets(
    _: Annotated[UUID, Depends(require_admin)],
) -> list[AdminBucket]:
    async with db.as_service_role() as conn:
        return await service_storage.list_buckets(conn)


@router.get("/buckets/{bucket}/objects", response_model=AdminObjectsPage)
async def list_bucket_objects(
    bucket: str,
    _: Annotated[UUID, Depends(require_admin)],
    prefix: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AdminObjectsPage:
    try:
        async with db.as_service_role() as conn:
            return await service_storage.list_bucket_objects(
                conn, bucket, prefix, limit, offset
            )
    except AdminError as exc:
        raise to_http(exc) from exc


@router.post("/objects/{object_id}/sign", response_model=AdminSignedUrlResponse)
async def sign_object(
    object_id: UUID,
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
    payload: Annotated[AdminSignObjectRequest | None, Body()] = None,
) -> AdminSignedUrlResponse:
    body = payload or AdminSignObjectRequest()
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        response, bucket_name, path = await service_storage.sign_object(
            object_id,
            body.expires_in,
            body.role,
            body.impersonate_sub,
        )
        async with db.as_service_role() as conn:
            await audit.write(
                conn,
                admin_id=admin_id,
                action="storage.object.sign",
                target=str(object_id),
                payload={
                    "bucket": bucket_name,
                    "path": path,
                    "expires_in": response.expires_in,
                    "signed_under_role": response.signed_under_role,
                },
                ip=ip,
                ua=ua,
            )
    except AdminError as exc:
        raise to_http(exc) from exc
    return response


@router.delete("/objects/{object_id}", status_code=204)
async def delete_object(
    object_id: UUID,
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
) -> None:
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    backend = get_backend()
    try:
        bucket_name, path = await service_storage.delete_object(backend, object_id)
        async with db.as_service_role() as conn:
            await audit.write(
                conn,
                admin_id=admin_id,
                action="storage.object.delete",
                target=str(object_id),
                payload={"bucket": bucket_name, "path": path},
                ip=ip,
                ua=ua,
            )
    except AdminError as exc:
        raise to_http(exc) from exc
