import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

import asyncpg
from fastapi import FastAPI

from .settings import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def _connection_setup(conn: asyncpg.Connection) -> None:
    timeout_ms = get_settings().db_statement_timeout_ms
    if timeout_ms > 0:
        await conn.execute(f"set statement_timeout = {int(timeout_ms)}")


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = await asyncpg.create_pool(
            s.database_url,
            min_size=s.db_pool_min_size,
            max_size=s.db_pool_max_size,
            setup=_connection_setup,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised. Call init_pool() first.")
    return _pool


@asynccontextmanager
async def acquire() -> AsyncGenerator[asyncpg.Connection, None]:
    pool = get_pool()
    async with pool.acquire() as conn:
        yield cast(asyncpg.Connection, conn)


@asynccontextmanager
async def as_role(role: str, claims: dict[str, Any]) -> AsyncGenerator[asyncpg.Connection, None]:
    """Yield a connection scoped to *role* with *claims* set as the JWT GUC.

    Mirrors PostgREST's per-request role switch so that any SQL executed on
    the yielded connection sees the same RLS verdict as a PostgREST request
    would for the same JWT payload.
    """
    pool = get_pool()

    allowed = get_settings().db_allowed_roles

    if role not in allowed:
        raise ValueError(f"role {role!r} not in {sorted(allowed)}")

    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(f'set local role "{role}"')
        await conn.execute(
            "select set_config('request.jwt.claims', $1, true)",
            json.dumps(claims),
        )
        yield cast(asyncpg.Connection, conn)


@asynccontextmanager
async def as_service_role(
    *,
    claims: dict[str, Any] | None = None,
) -> AsyncGenerator[asyncpg.Connection, None]:
    """Yield a pool connection running as ``service_role`` for the duration.

    Framework-internal housekeeping primitive — distinct from :func:`as_role`,
    which is the JWT-driven switch PostgREST mirrors. ``service_role`` bypasses
    RLS, so the choice of role is made by internal code and never by a JWT's
    ``role`` claim.

    The optional ``claims`` argument sets ``request.jwt.claims`` on the
    session via ``set_config('request.jwt.claims', …, true)`` so helpers
    like ``auth.uid()`` see the caller's identity inside the block. This
    is purely informational: ``service_role`` still bypasses RLS and
    setting claims does not grant or restrict anything — it just makes
    audit / stamping helpers return meaningful values during server-side
    work performed on behalf of a specific user.

    Uses ``SET LOCAL ROLE`` and ``set_config(..., true)`` inside a
    transaction, so the role and GUC reset on ``COMMIT`` before the
    connection returns to the pool.
    """
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("set local role service_role")
        if claims is not None:
            await conn.execute(
                "select set_config('request.jwt.claims', $1, true)",
                json.dumps(claims),
            )
        yield cast(asyncpg.Connection, conn)


def _maybe_enable_slow_callback_warnings() -> None:
    """Turn on asyncio debug mode if SUPYTHON_SLOW_CALLBACK_MS is set.

    The CLI's ``dev`` command sets this env var; production code paths leave
    it unset so the (non-trivial) debug overhead is not paid in prod.
    """
    raw = os.environ.get("SUPYTHON_SLOW_CALLBACK_MS")
    if not raw:
        return
    try:
        threshold_ms = int(raw)
    except ValueError:
        logger.warning("SUPYTHON_SLOW_CALLBACK_MS=%r is not an int; ignoring", raw)
        return
    if threshold_ms <= 0:
        return
    loop = asyncio.get_running_loop()
    loop.slow_callback_duration = threshold_ms / 1000.0
    loop.set_debug(True)
    logger.info(
        "asyncio debug enabled; warning on callbacks > %dms (dev mode)",
        threshold_ms,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _maybe_enable_slow_callback_warnings()
    _created_pool = _pool is None
    await init_pool()
    try:
        yield
    finally:
        if _created_pool:
            await close_pool()
