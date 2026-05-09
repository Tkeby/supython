from typing import Annotated
from uuid import UUID

from fastapi import Cookie, HTTPException, Request, status

from .. import db
from . import session as admin_session


async def require_admin(
    request: Request,
    cookie: Annotated[str | None, Cookie(alias=admin_session.SESSION_COOKIE)] = None,
) -> UUID:
    if not cookie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin session required")
    async with db.as_service_role() as conn:
        resolved = await admin_session.resolve(conn, cookie)
    if resolved is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    admin_id, _expires = resolved
    request.state.admin_id = admin_id
    return admin_id
