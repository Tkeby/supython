from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from ... import db, jwks
from ...settings import get_settings
from ..deps import require_admin
from ..schemas import SystemStatus, SystemVersion

router = APIRouter(prefix="/admin/api/v1/system", tags=["admin.system"])


@router.get("/status", response_model=SystemStatus)
async def system_status(
    _: Annotated[UUID, Depends(require_admin)],
) -> SystemStatus:
    settings = get_settings()
    pool = db.get_pool()
    jwks_doc = jwks.dump_jwks(jwks.load_verification_keyset())
    kids = [k["kid"] for k in jwks_doc.get("keys", [])]
    kid = kids[0] if kids else ""
    return SystemStatus(
        pool_size=pool.get_size(),
        jwks_kid=kid,
        broker=settings.realtime_enabled,
        jobs=settings.jobs_enabled,
    )


@router.get("/version", response_model=SystemVersion)
async def system_version(
    _: Annotated[UUID, Depends(require_admin)],
) -> SystemVersion:
    from ... import __version__

    return SystemVersion(version=__version__)
