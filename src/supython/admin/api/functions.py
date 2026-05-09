import ipaddress
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request

from ... import db
from .. import audit
from ..deps import require_admin
from ..errors import AdminError, to_http
from ..schemas import (
    FunctionInvokeRequest,
    FunctionInvokeResponse,
    FunctionRoute,
    FunctionSourceResponse,
)
from . import service_functions

router = APIRouter(prefix="/admin/api/v1/functions", tags=["admin.functions"])


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    try:
        ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    return request.client.host


@router.get("/routes", response_model=list[FunctionRoute])
async def list_routes(
    _: Annotated[UUID, Depends(require_admin)],
) -> list[FunctionRoute]:
    return service_functions.list_routes()


@router.get("/{name:path}/source", response_model=FunctionSourceResponse)
async def read_source(
    name: str,
    _: Annotated[UUID, Depends(require_admin)],
) -> FunctionSourceResponse:
    try:
        return service_functions.read_source(name)
    except AdminError as exc:
        raise to_http(exc) from exc


@router.post("/{name:path}/invoke", response_model=FunctionInvokeResponse)
async def invoke(
    name: str,
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
    payload: Annotated[FunctionInvokeRequest | None, Body()] = None,
) -> FunctionInvokeResponse:
    body = payload or FunctionInvokeRequest()
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        result = await service_functions.invoke_function(name, body)
    except AdminError as exc:
        async with db.as_service_role() as conn:
            await audit.write(
                conn,
                admin_id=admin_id,
                action="functions.invoke.failed",
                target=name,
                payload={
                    "method": body.method.upper(),
                    "error_code": exc.code,
                },
                ip=ip,
                ua=ua,
            )
        raise to_http(exc) from exc

    async with db.as_service_role() as conn:
        await audit.write(
            conn,
            admin_id=admin_id,
            action="functions.invoke",
            target=name,
            payload={
                "method": body.method.upper(),
                "status": result.status,
                "elapsed_ms": result.elapsed_ms,
            },
            ip=ip,
            ua=ua,
        )
    return result
