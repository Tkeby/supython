import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, db, jwks
from .admin import router as admin_api_router
from .admin import spa as admin_spa
from .auth.router import router as auth_router
from .extensions import load_extensions
from .settings_module import UserSettings, load_user_settings
from .functions.loader import get_registry as get_function_registry
from .functions.router import router as functions_router
from .health import router as health_router
from .hooks import on as hook_on
from .logging_config import (
    RequestIdMiddleware,
    RequestLoggingMiddleware,
    configure_logging,
)
from .body_size import BodySizeLimitMiddleware
from .security_headers import SecurityHeadersMiddleware
from .realtime import get_broker
from .realtime.router import router as realtime_router
from .settings import get_settings
from .storage.router import router as storage_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with db.lifespan(app):
        registry = get_function_registry()
        try:
            registry.discover()
        except Exception:
            logger.warning("functions: discover() failed at startup", exc_info=True)

        settings = get_settings()
        jwks_doc = jwks.write_current_jwks(settings.jwt_jwks_path)
        kids = ", ".join(key["kid"] for key in jwks_doc["keys"])
        logger.info("jwt: wrote JWKS path=%s kids=[%s]", settings.jwt_jwks_path, kids)

        broker = get_broker() if settings.realtime_enabled else None
        if broker is not None:
            try:
                await broker.start()
            except Exception:
                logger.exception("realtime: broker failed to start; continuing without realtime")
                broker = None
        app.state.broker = broker

        worker = None
        worker_task = None
        if settings.jobs_enabled and settings.jobs_cron_backend == "pg_cron":
            try:
                from .jobs.cron import sync_pg_cron

                async with db.as_service_role() as conn:
                    await sync_pg_cron(conn)
            except Exception:
                logger.warning("jobs: pg_cron sync failed at startup", exc_info=True)

        if settings.jobs_enabled and settings.jobs_dev_inprocess:
            from .jobs.worker import Worker

            worker = Worker(settings)
            try:
                worker_task = asyncio.create_task(worker.start())
            except Exception:
                logger.warning("jobs: in-process worker failed to start", exc_info=True)

        try:
            yield
        finally:
            if worker is not None:
                try:
                    await worker.stop()
                except Exception:
                    logger.exception("jobs: worker failed to stop cleanly")
            if worker_task is not None:
                worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker_task
            if broker is not None:
                try:
                    await broker.stop()
                except Exception:
                    logger.exception("realtime: broker failed to stop cleanly")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json_format=settings.log_json)

    user = (
        load_user_settings(settings.settings_module)
        if settings.settings_module
        else UserSettings()
    )
    load_extensions([*settings.extensions, *user.extensions])

    app = FastAPI(
        title="supython",
        description="Lightweight Postgres-first BaaS for Python.",
        version=__version__,
        lifespan=_lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    for mw in user.extra_middleware:
        app.add_middleware(mw)

    app.include_router(auth_router)
    app.include_router(storage_router)
    app.include_router(functions_router)
    if settings.realtime_enabled:
        app.include_router(realtime_router)
    if settings.jobs_enabled:
        from .jobs.router import router as jobs_router

        app.include_router(jobs_router)

    app.include_router(health_router)
    app.include_router(admin_api_router)
    admin_spa.mount(app)

    for rt in user.extra_routers:
        app.include_router(rt)

    def _make_hook_decorator(event: str) -> Callable[..., Any]:
        def decorator(fn: Callable[..., Coroutine[Any, Any, None]] | None = None) -> Any:
            return hook_on(event, fn)

        return decorator

    app.on_signup = _make_hook_decorator("signup")
    app.on_login = _make_hook_decorator("login")
    app.on_logout = _make_hook_decorator("logout")

    return app


app = create_app()
