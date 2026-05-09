"""Tiny SQL migration runner for framework DDL only.

Applies every `*.sql` file shipped under ``supython/migrations`` in
lexical order, recording each filename in ``supython.migrations`` so it
runs exactly once. This is intentionally minimal and intentionally
scoped: it owns the framework's own schemas (``auth``, ``storage``,
``realtime``, ``jobs``, ``supython``), not your application's schema
history.

The framework migrations ship inside the installed wheel
(``src/supython/migrations/``) so ``supython migrate`` works from any
working directory — no repo checkout required.

For app-level migrations, supython recommends **dbmate** (single Go
binary, raw SQL, no Python deps) — see ``docs/migrations.md``. atlas and
sqitch are documented as alternates. Alembic is deliberately not
recommended (no ORM → no autogeneration → no value-add over dbmate).
"""

import asyncio
import logging
from pathlib import Path

import asyncpg

from .settings import get_settings

logger = logging.getLogger(__name__)

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


async def _ensure_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        create schema if not exists supython;
        create table if not exists supython.migrations (
            name        text primary key,
            applied_at  timestamptz not null default now()
        );
        """
    )


async def run_migrations(directory: Path | None = None) -> list[str]:
    """Apply pending migrations. Returns the list of newly applied filenames."""
    target = directory or DEFAULT_MIGRATIONS_DIR
    if not target.exists():
        raise FileNotFoundError(f"Migrations directory not found: {target}")

    files = sorted(p for p in target.glob("*.sql"))
    applied: list[str] = []

    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        await _ensure_table(conn)
        existing = {
            r["name"]
            for r in await conn.fetch("select name from supython.migrations")
        }
        for path in files:
            if path.name in existing:
                continue
            sql = path.read_text()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "insert into supython.migrations (name) values ($1)",
                    path.name,
                )
            applied.append(path.name)
            logger.info("migration applied: %s", path.name)
    finally:
        await conn.close()

    return applied


def run_sync(directory: Path | None = None) -> list[str]:
    return asyncio.run(run_migrations(directory))
