import ipaddress
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request

from ... import db
from .. import audit
from ..deps import require_admin
from ..errors import AdminError, to_http
from ..schemas import (
    AdminAuditPage,
    AdminUserDetail,
    AdminUsersPage,
    BanRequest,
    RefreshTokensPage,
)
from . import service_auth_users

router = APIRouter(prefix="/admin/api/v1/auth", tags=["admin.auth.users"])


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    try:
        ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    return request.client.host


@router.get("/users", response_model=AdminUsersPage)
async def list_users(
    _: Annotated[UUID, Depends(require_admin)],
    search: str | None = None,
    confirmed: bool | None = None,
    banned: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AdminUsersPage:
    try:
        async with db.as_service_role() as conn:
            return await service_auth_users.search_users(
                conn, search, confirmed, banned, limit, offset
            )
    except AdminError as exc:
        raise to_http(exc) from exc


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user(
    user_id: UUID,
    _: Annotated[UUID, Depends(require_admin)],
) -> AdminUserDetail:
    try:
        async with db.as_service_role() as conn:
            return await service_auth_users.get_user_detail(conn, user_id)
    except AdminError as exc:
        raise to_http(exc) from exc


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: UUID,
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
    payload: Annotated[BanRequest | None, Body()] = None,
) -> dict[str, str]:
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    duration = payload.duration_seconds if payload else None
    try:
        async with db.as_service_role() as conn:
            banned_until = await service_auth_users.ban_user(conn, user_id, duration)
            await service_auth_users.write_user_audit(
                conn,
                user_id=user_id,
                event="user.banned",
                payload={"banned_until": banned_until.isoformat()},
                ip=ip,
                ua=ua,
            )
            await audit.write(
                conn,
                admin_id=admin_id,
                action="auth.user.ban",
                target=str(user_id),
                payload={"banned_until": banned_until.isoformat()},
                ip=ip,
                ua=ua,
            )
    except AdminError as exc:
        raise to_http(exc) from exc
    return {"banned_until": banned_until.isoformat()}


@router.post("/users/{user_id}/unban", status_code=204)
async def unban_user(
    user_id: UUID,
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
) -> None:
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        async with db.as_service_role() as conn:
            await service_auth_users.unban_user(conn, user_id)
            await service_auth_users.write_user_audit(
                conn,
                user_id=user_id,
                event="user.unbanned",
                payload={},
                ip=ip,
                ua=ua,
            )
            await audit.write(
                conn,
                admin_id=admin_id,
                action="auth.user.unban",
                target=str(user_id),
                payload={},
                ip=ip,
                ua=ua,
            )
    except AdminError as exc:
        raise to_http(exc) from exc


@router.post("/users/{user_id}/force-logout")
async def force_logout(
    user_id: UUID,
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
) -> dict[str, int]:
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        async with db.as_service_role() as conn:
            revoked = await service_auth_users.force_logout(conn, user_id)
            await service_auth_users.write_user_audit(
                conn,
                user_id=user_id,
                event="user.force_logout",
                payload={"revoked": revoked},
                ip=ip,
                ua=ua,
            )
            await audit.write(
                conn,
                admin_id=admin_id,
                action="auth.user.force_logout",
                target=str(user_id),
                payload={"revoked": revoked},
                ip=ip,
                ua=ua,
            )
    except AdminError as exc:
        raise to_http(exc) from exc
    return {"revoked": revoked}


@router.get("/refresh-tokens", response_model=RefreshTokensPage)
async def list_refresh_tokens(
    _: Annotated[UUID, Depends(require_admin)],
    user_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> RefreshTokensPage:
    try:
        async with db.as_service_role() as conn:
            return await service_auth_users.list_refresh_tokens(conn, user_id, limit, offset)
    except AdminError as exc:
        raise to_http(exc) from exc


@router.delete("/refresh-tokens/{token_id}", status_code=204)
async def revoke_refresh_token(
    token_id: int,
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
) -> None:
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        async with db.as_service_role() as conn:
            user_id = await service_auth_users.revoke_refresh_token(conn, token_id)
            await service_auth_users.write_user_audit(
                conn,
                user_id=user_id,
                event="refresh_token.revoked",
                payload={"token_id": token_id},
                ip=ip,
                ua=ua,
            )
            await audit.write(
                conn,
                admin_id=admin_id,
                action="auth.refresh_token.revoke",
                target=str(token_id),
                payload={"token_id": token_id, "user_id": str(user_id)},
                ip=ip,
                ua=ua,
            )
    except AdminError as exc:
        raise to_http(exc) from exc


@router.get("/audit", response_model=AdminAuditPage)
async def list_audit(
    _: Annotated[UUID, Depends(require_admin)],
    event: str | None = None,
    ip: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AdminAuditPage:
    try:
        async with db.as_service_role() as conn:
            return await service_auth_users.list_audit_log(
                conn, event, ip, from_date, to_date, limit, offset
            )
    except AdminError as exc:
        raise to_http(exc) from exc
