import ipaddress
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request

from ... import db
from .. import audit
from ..deps import require_admin
from ..errors import AdminError, to_http
from ..schemas import (
    DryRunRequest,
    DryRunResponse,
    MigrationRecord,
    RlsPolicy,
    RowsPage,
    SchemaInfo,
    SqlExecRequest,
    SqlExecResponse,
    TableInfo,
)
from . import service_db

router = APIRouter(prefix="/admin/api/v1/db", tags=["admin.db"])


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    try:
        ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    return request.client.host


@router.get("/schemas", response_model=list[SchemaInfo])
async def list_schemas(
    _: Annotated[UUID, Depends(require_admin)],
) -> list[SchemaInfo]:
    async with db.as_service_role() as conn:
        return await service_db.list_schemas(conn)


@router.get("/tables/{schema}", response_model=list[TableInfo])
async def list_tables(
    schema: str,
    _: Annotated[UUID, Depends(require_admin)],
) -> list[TableInfo]:
    try:
        async with db.as_service_role() as conn:
            return await service_db.list_tables(conn, schema)
    except AdminError as exc:
        raise to_http(exc) from exc


@router.get("/tables/{schema}/{table}/rows", response_model=RowsPage)
async def read_rows(
    schema: str,
    table: str,
    _: Annotated[UUID, Depends(require_admin)],
    limit: int = 50,
    offset: int = 0,
    order: str | None = None,
    role: Literal["service_role", "authenticated", "anon"] = "service_role",
    impersonate_sub: UUID | None = None,
) -> RowsPage:
    try:
        if role == "service_role":
            async with db.as_service_role() as conn:
                return await service_db.read_rows(conn, schema, table, limit, offset, order)
        claims = service_db.preview_claims(role, impersonate_sub)
        async with db.as_role(role, claims) as conn:
            return await service_db.read_rows(conn, schema, table, limit, offset, order)
    except AdminError as exc:
        raise to_http(exc) from exc


@router.post("/sql/execute", response_model=SqlExecResponse)
async def run_sql(
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
    payload: Annotated[SqlExecRequest, Body()],
) -> SqlExecResponse:
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        async with db.as_service_role() as conn:
            try:
                result = await service_db.execute_sql(conn, payload)
            except AdminError as exc:
                # Audit the failed attempt on a fresh connection so the poisoned
                # transaction is not reused.
                async with db.as_service_role() as audit_conn:
                    await audit.write(
                        audit_conn,
                        admin_id=admin_id,
                        action="sql.execute.failed",
                        target=None,
                        payload={
                            "statement": payload.statement[:2048],
                            "error_code": exc.code,
                        },
                        ip=ip,
                        ua=ua,
                    )
                raise
            await audit.write(
                conn,
                admin_id=admin_id,
                action="sql.execute",
                target=None,
                payload={
                    "statement": payload.statement[:2048],
                    "row_count": result.row_count,
                },
                ip=ip,
                ua=ua,
            )
        return result
    except AdminError as exc:
        raise to_http(exc) from exc


@router.get("/rls/{schema}/{table}", response_model=list[RlsPolicy])
async def list_policies(
    schema: str,
    table: str,
    _: Annotated[UUID, Depends(require_admin)],
) -> list[RlsPolicy]:
    try:
        async with db.as_service_role() as conn:
            return await service_db.list_policies(conn, schema, table)
    except AdminError as exc:
        raise to_http(exc) from exc


@router.post("/rls/dry-run", response_model=DryRunResponse)
async def dry_run_policy(
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
    payload: Annotated[DryRunRequest, Body()],
) -> DryRunResponse:
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        async with db.as_service_role() as conn:
            result = await service_db.dry_run_policy(conn, payload.ddl, payload.sample_query)
            await audit.write(
                conn,
                admin_id=admin_id,
                action="rls.dry_run",
                target=None,
                payload={
                    "ddl": payload.ddl[:2048],
                    "sample_query": payload.sample_query[:2048],
                },
                ip=ip,
                ua=ua,
            )
            return result
    except AdminError as exc:
        raise to_http(exc) from exc


@router.get("/migrations", response_model=list[MigrationRecord])
async def list_migrations(
    _: Annotated[UUID, Depends(require_admin)],
) -> list[MigrationRecord]:
    try:
        async with db.as_service_role() as conn:
            return await service_db.list_migrations(conn)
    except AdminError as exc:
        raise to_http(exc) from exc
