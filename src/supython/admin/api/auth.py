import ipaddress
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from ... import db
from .. import audit
from .. import session as admin_session
from ..errors import AdminError, to_http
from ..schemas import LoginRequest, SessionResponse
from . import service_auth

router = APIRouter(prefix="/admin/api/v1/auth", tags=["admin.auth"])


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    try:
        ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    return request.client.host


@router.post("/login", response_model=SessionResponse)
async def login(
    payload: LoginRequest, request: Request, response: Response
) -> SessionResponse:
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        async with db.as_service_role() as conn:
            admin_id, email = await service_auth.authenticate(
                conn, payload.email, payload.password
            )
            token, expires = await admin_session.issue(
                conn, admin_id=admin_id, ip=ip, ua=ua
            )
            await service_auth.touch_last_login(conn, admin_id)
            await audit.write(
                conn,
                admin_id=admin_id,
                action="admin.login",
                target=payload.email,
                payload={"email": payload.email},
                ip=ip,
                ua=ua,
            )
    except AdminError as exc:
        async with db.as_service_role() as audit_conn:
            await audit.write(
                audit_conn,
                admin_id=None,
                action="admin.login.failed",
                target=payload.email,
                payload={"email": payload.email, "error_code": exc.code},
                ip=ip,
                ua=ua,
            )
        raise to_http(exc) from exc
    response.set_cookie(
        admin_session.SESSION_COOKIE,
        token,
        max_age=int(admin_session.SESSION_TTL.total_seconds()),
        httponly=True,
        secure=True,
        samesite="strict",
        path=admin_session.SESSION_PATH,
    )
    return SessionResponse(admin_id=admin_id, email=email, expires_at=expires)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    cookie: Annotated[str | None, Cookie(alias=admin_session.SESSION_COOKIE)] = None,
) -> None:
    if cookie:
        ip = _client_ip(request)
        ua = request.headers.get("user-agent")
        async with db.as_service_role() as conn:
            resolved = await admin_session.resolve(conn, cookie)
            if resolved is not None:
                admin_id, _expires = resolved
                await audit.write(
                    conn,
                    admin_id=admin_id,
                    action="admin.logout",
                    target=None,
                    payload={},
                    ip=ip,
                    ua=ua,
                )
            await admin_session.revoke(conn, cookie)
    response.delete_cookie(admin_session.SESSION_COOKIE, path=admin_session.SESSION_PATH)


@router.get("/session", response_model=SessionResponse)
async def session(
    request: Request,
    cookie: Annotated[str | None, Cookie(alias=admin_session.SESSION_COOKIE)] = None,
) -> SessionResponse:
    if not cookie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin session required")
    async with db.as_service_role() as conn:
        resolved = await admin_session.resolve(conn, cookie)
        if resolved is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
        admin_id, expires = resolved
        info = await service_auth.fetch_admin(conn, admin_id)
    if info is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin user not found")
    email, _last_login = info
    request.state.admin_id = admin_id
    return SessionResponse(admin_id=admin_id, email=email, expires_at=expires)
