from fastapi import APIRouter

from .auth import router as auth_router
from .auth_templates import router as auth_templates_router
from .auth_users import router as auth_users_router
from .db import router as db_router
from .functions import router as functions_router
from .jobs import router as jobs_router
from .ops import router as ops_router
from .realtime import router as realtime_router
from .storage import router as storage_router
from .system import router as system_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(auth_templates_router)
router.include_router(auth_users_router)
router.include_router(system_router)
router.include_router(db_router)
router.include_router(storage_router)
router.include_router(functions_router)
router.include_router(jobs_router)
router.include_router(realtime_router)
router.include_router(ops_router)
