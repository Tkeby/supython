"""Cron scheduling — ``pg_cron`` synchronisation only.

The in-process ``croniter`` fallback moved to :mod:`.cron_inproc` so that
the ``croniter`` import (an optional extra, see the v0.5 decision log) is
only touched when ``jobs_cron_backend == 'inproc'``. This module has no
optional-dep imports and is safe to load at app startup.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator

import asyncpg

from .registry import get_registry

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def _as_login_role(conn: asyncpg.Connection) -> AsyncIterator[None]:
    """Temporarily step out of a NOLOGIN role for pg_cron scheduling.

    pg_cron stamps ``current_user`` on the ``cron.job`` row at schedule
    time and uses that role to initialise a background worker on every
    tick. The caller of :func:`sync_pg_cron` is expected to be in
    ``service_role``, which is ``NOLOGIN`` (see
    ``migrations/0001_extensions_and_roles.sql``); every tick would then
    FATAL with ``role "service_role" is not permitted to log in`` and
    the schedule would silently never fire.

    We hop back to the connection's pre-``service_role`` identity for
    just the ``cron.schedule`` / ``cron.unschedule`` call. That identity
    is whichever role opened the asyncpg connection (see
    ``DATABASE_URL``) and is therefore guaranteed LOGIN-capable.

    Uses ``SET LOCAL`` when the caller is inside a transaction so the
    hop doesn't leak past a ``db.as_service_role()`` block into the
    pooled connection.
    """
    prev_role = await conn.fetchval("select current_user")
    in_txn = conn.is_in_transaction()
    scope = "local " if in_txn else ""
    await conn.execute(f"set {scope}role none")
    try:
        yield
    finally:
        await conn.execute(f'set {scope}role "{prev_role}"')


async def sync_pg_cron(
    conn: asyncpg.Connection,
    *,
    allow_empty: bool = False,
) -> None:
    """Upsert ``pg_cron`` schedule rows from the registry and remove stale ones.

    The caller is expected to have entered ``db.as_service_role()`` (or
    the CLI equivalent) before invoking this — the ``jobs.cron_schedules``
    table is owned by ``service_role``. For the actual ``cron.schedule``
    / ``cron.unschedule`` calls we transiently hop back to a LOGIN role
    via :func:`_as_login_role` so pg_cron's background worker can
    initialise a session at tick time.

    When pg_cron is installed, errors from ``cron.schedule`` propagate
    to the caller.

    When pg_cron is NOT installed the metadata row is still upserted so
    the in-process scheduler (or a manual runner) can pick it up, and
    ``cron.schedule`` is skipped entirely.

    Raises ``ValueError`` when the in-process registry has no ``@cron``
    definitions but ``jobs.cron_schedules`` is non-empty. That mismatch
    almost always means the caller forgot to import the user's
    ``EXTENSIONS`` before syncing, and proceeding would wipe every row
    (and unschedule every pg_cron entry). Pass ``allow_empty=True`` to
    intentionally clear the table.
    """
    registry = get_registry()
    cron_defns = list(registry.iter_crons())

    has_pg_cron = await conn.fetchval(
        "select exists(select 1 from pg_extension where extname = 'pg_cron')"
    )

    if not cron_defns and not allow_empty:
        existing_count = await conn.fetchval(
            "select count(*) from jobs.cron_schedules"
        )
        if existing_count:
            raise ValueError(
                f"registry has no @cron definitions but jobs.cron_schedules "
                f"holds {existing_count} row(s) — refusing to sync, since "
                f"this would wipe the table and unschedule every pg_cron "
                f"entry. Pass allow_empty=True to confirm, or check that "
                f"the module containing your @cron decorators is listed in "
                f"EXTENSIONS / SUPYTHON_SETTINGS_MODULE."
            )

    for cron_defn in cron_defns:
        await conn.execute(
            """
            insert into jobs.cron_schedules
                (name, cron_expr, job_name, job_version, payload, queue, enabled)
            values ($1, $2, $3, $4, $5::jsonb, $6, true)
            on conflict (name) do update set
                cron_expr   = excluded.cron_expr,
                job_name    = excluded.job_name,
                job_version = excluded.job_version,
                payload     = excluded.payload,
                queue       = excluded.queue,
                enabled     = excluded.enabled
            """,
            cron_defn.name,
            cron_defn.cron_expr,
            cron_defn.job_name,
            cron_defn.job_version,
            json.dumps(cron_defn.payload),
            cron_defn.queue,
        )

        if not has_pg_cron:
            continue

        # Build the pg_cron command via ``format(..., %L, %L, %L)`` so
        # Postgres handles quoting/escaping of the payload JSON and text
        # args instead of interpolating them from Python. This closes
        # the pre-grooming bug where f-string interpolation produced
        # invalid JSON for any non-trivial payload.
        command = await conn.fetchval(
            """
            select format(
                'select jobs.enqueue(p_name := %L, p_payload := %L::jsonb, p_queue := %L)',
                $1::text, $2::text, $3::text
            )
            """,
            cron_defn.job_name,
            json.dumps(cron_defn.payload),
            cron_defn.queue,
        )

        async with _as_login_role(conn):
            await conn.execute(
                "select cron.schedule($1, $2, $3)",
                cron_defn.name,
                cron_defn.cron_expr,
                command,
            )

    registered_names = {c.name for c in cron_defns}
    existing = await conn.fetch("select name from jobs.cron_schedules")
    for row in existing:
        if row["name"] in registered_names:
            continue
        if has_pg_cron:
            async with _as_login_role(conn):
                # Stale metadata may no longer have a matching cron.job
                # row (e.g. manually unscheduled); tolerate that single
                # case. Everything else — permission denied, syntax
                # error, etc. — indicates a misconfiguration and is
                # surfaced to the caller.
                try:
                    await conn.execute(
                        "select cron.unschedule($1)", row["name"]
                    )
                except asyncpg.exceptions.RaiseError as exc:
                    if "could not find" not in str(exc):
                        raise
                    logger.debug(
                        "jobs.cron.unschedule_noop",
                        extra={"cron_name": row["name"]},
                    )
        await conn.execute(
            "delete from jobs.cron_schedules where name = $1",
            row["name"],
        )
