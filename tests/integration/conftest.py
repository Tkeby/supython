"""Fixtures for the integration test suite.

These tests need a live Postgres on the DSN configured by `DATABASE_URL`
(default: the test stack on port 54323 — see `docker-compose.test.yml`).

Run with `supython test up && supython test run tests/integration` (or
just `supython test run`, which forwards extra args to pytest). When the
database is unreachable, the `pool` fixture skips this entire package so
unit tests in `tests/unit/` keep running unaffected.

Pool lifecycle:
- A single asyncpg pool is created once per session and injected into
  `supython.db` so the FastAPI app can call `db.acquire()` without the
  ASGI lifespan hook (ASGITransport does not send lifespan events).
- Each test gets a clean slate: `clean_auth_tables` deletes all auth
  rows before and after every test.
"""

import os

import asyncpg
import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

# Ensure symmetric secrets are available for integration tests
os.environ.setdefault("OAUTH_STATE_SECRET", "a" * 48)
os.environ.setdefault("STORAGE_SIGNED_URL_SECRET", "a" * 48)

from supython import db as _db
from supython.app import create_app
from supython.settings import get_settings


@pytest_asyncio.fixture(scope="session")
async def pool() -> asyncpg.Pool:
    """Single asyncpg pool for the entire integration session.

    Injected into supython.db so all service calls share one pool without
    requiring the ASGI lifespan to fire.
    Skips the entire integration package when the database is not
    reachable — unit tests under `tests/unit/` keep running.
    """
    s = get_settings()
    # Guardrail: integration fixtures wipe schemas (auth.users, admin.admin_users,
    # …) between tests. If DATABASE_URL points at the dev DB on port 54322 it
    # will silently destroy local data. Refuse unless the DSN targets the test
    # stack on 54323 or the operator opts in explicitly.
    if ":54323" not in s.database_url and not os.environ.get("SUPYTHON_ALLOW_DEV_DB_TESTS"):
        pytest.skip(
            "integration tests require the test DB on port 54323 "
            "(run via `supython test run`); set SUPYTHON_ALLOW_DEV_DB_TESTS=1 to override"
        )
    try:
        p = await asyncpg.create_pool(s.database_url, min_size=1, max_size=5)
    except Exception as exc:
        pytest.skip(f"Postgres not reachable — run `supython test up` first ({exc})")
        return  # type: ignore[return-value]
    _db._pool = p
    yield p
    await p.close()
    _db._pool = None


# The framework no longer ships a demo ``public.todos`` table — it owns only its
# own schemas (auth, storage, realtime, jobs). Much of the integration suite
# exercises that table, so the suite provisions it itself, acting as the
# "client" and mirroring a scaffolded project's first migration. Idempotent so
# it is safe across repeated sessions and any leftover state.
_DEMO_TODOS_DDL = """
create table if not exists public.todos (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null default auth.uid()
                    references auth.users (id) on delete cascade,
    title       text not null check (length(title) > 0),
    done        boolean not null default false,
    created_at  timestamptz not null default now()
);

alter table public.todos enable row level security;

drop policy if exists "todos: owner can read"   on public.todos;
drop policy if exists "todos: owner can insert" on public.todos;
drop policy if exists "todos: owner can update" on public.todos;
drop policy if exists "todos: owner can delete" on public.todos;

create policy "todos: owner can read"   on public.todos for select to authenticated using      (user_id = auth.uid());
create policy "todos: owner can insert" on public.todos for insert to authenticated with check (user_id = auth.uid());
create policy "todos: owner can update" on public.todos for update to authenticated using      (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "todos: owner can delete" on public.todos for delete to authenticated using      (user_id = auth.uid());

grant select, insert, update, delete on public.todos to authenticated;
"""


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _demo_todos_table(pool: asyncpg.Pool):
    """Provision a clean demo ``public.todos`` for the suite (once per session).

    Drop-then-create so every session starts from a known-clean table — some
    gen-types tests add temporary columns, and a prior aborted run could
    otherwise leave them behind for a plain ``create table if not exists`` to
    silently inherit.
    """
    async with pool.acquire() as conn:
        await conn.execute("drop table if exists public.todos cascade")
        await conn.execute(_DEMO_TODOS_DDL)
    yield


@pytest.fixture(scope="session")
def app(pool: asyncpg.Pool):
    """FastAPI application instance shared across the session."""
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    """HTTP client wired to the ASGI app (no real network).

    Uses an ``https://`` base URL so secure cookies (e.g. the admin session
    cookie set with ``secure=True``) survive round-trips through the httpx
    cookie jar. The ASGI transport ignores the scheme — it just hands the
    request to the app — so this is a pure cookie-jar concern.
    """
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
        follow_redirects=False,
    ) as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def clean_auth_tables(pool: asyncpg.Pool):
    """Wipe all auth tables before each test to guarantee isolation."""
    async with pool.acquire() as conn:
        await conn.execute("delete from jobs.jobs")
        await conn.execute("delete from admin.backups")
        await conn.execute("delete from auth.rate_limit_buckets")
        # audit_log has ON DELETE SET NULL, so wipe it first
        await conn.execute("delete from auth.audit_log")
        # Users cascade-delete identities, one_time_tokens, refresh_tokens
        await conn.execute("delete from auth.users")
    yield
    async with pool.acquire() as conn:
        await conn.execute("delete from jobs.jobs")
        await conn.execute("delete from admin.backups")
        await conn.execute("delete from auth.rate_limit_buckets")
        await conn.execute("delete from auth.audit_log")
        await conn.execute("delete from auth.users")


@pytest_asyncio.fixture(autouse=True)
async def _assert_no_role_leak(pool):
    """Post-test sentinel: verify no SET ROLE leaked into the pool."""
    yield
    async with pool.acquire() as c:
        current, session = await c.fetchrow("select current_user::text, session_user::text")
    assert current == session, (
        f"role leaked into pool: current_user={current!r}, session_user={session!r}"
    )


# ---------------------------------------------------------------------------
# pg_cron availability check
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def pg_cron_available(pool: asyncpg.Pool) -> bool:
    """True when pg_cron extension is installed and functional."""
    try:
        val = await pool.fetchval("select count(*) from pg_extension where extname = 'pg_cron'")
        return val is not None and val > 0
    except Exception:
        return False


@pytest.fixture
def skip_without_pg_cron(pg_cron_available: bool):
    """Skip test when pg_cron is not available."""
    if not pg_cron_available:
        pytest.skip("pg_cron extension not available")
