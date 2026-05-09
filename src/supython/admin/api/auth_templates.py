from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from ... import db
from .. import audit
from ..deps import require_admin
from ..errors import AdminError, to_http
from ..schemas import EmailTemplate, EmailTemplateUpdate
from . import service_auth_templates

router = APIRouter(prefix="/admin/api/v1/auth", tags=["admin.auth.templates"])


@router.get("/templates", response_model=list[EmailTemplate])
async def list_templates(
    _: Annotated[UUID, Depends(require_admin)],
) -> list[EmailTemplate]:
    try:
        async with db.as_service_role() as conn:
            return await service_auth_templates.list_templates(conn)
    except AdminError as exc:
        raise to_http(exc) from exc


@router.get("/templates/{name}", response_model=EmailTemplate)
async def get_template(
    name: str,
    _: Annotated[UUID, Depends(require_admin)],
) -> EmailTemplate:
    try:
        async with db.as_service_role() as conn:
            return await service_auth_templates.get_template(conn, name)
    except AdminError as exc:
        raise to_http(exc) from exc


@router.patch("/templates/{name}", response_model=EmailTemplate)
async def update_template(
    name: str,
    payload: EmailTemplateUpdate,
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
) -> EmailTemplate:
    try:
        async with db.as_service_role() as conn:
            result = await service_auth_templates.update_template(
                conn,
                name,
                payload.subject,
                payload.text_body,
            )
    except AdminError as exc:
        raise to_http(exc) from exc

    async with db.as_service_role() as conn:
        await audit.write(
            conn,
            admin_id=admin_id,
            action="auth.template.update",
            target=name,
            payload=payload.model_dump(exclude_none=True),
            ip=request.client.host if request.client else None,
            ua=request.headers.get("user-agent"),
        )
    return result
