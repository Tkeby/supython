"""Realtime service layer.

Pure async functions over ``asyncpg.Connection``. No FastAPI imports.

There are three public entry points used by the rest of the realtime
module:

``enable_table``
    Service-role only.  Wraps the SQL helper ``realtime.enable(regclass,
    text)`` defined in :file:`migrations/0006_realtime_schema.sql`.  This
    upserts ``realtime.enabled_tables`` and (re-)attaches the
    ``realtime_notify`` trigger.

``list_enabled``
    Reads the registry under the caller's role so RLS still applies.
    Returns one :class:`~.schemas.EnabledTable` per row.

``rls_check``
    Per-event per-subscriber visibility probe.  Runs ``select 1 from
    <schema>.<table> where <pk> = $n`` under the subscriber's role +
    claims.  Used by the broker to decide whether a particular row change
    should be forwarded to a particular WebSocket.

The DELETE-visibility short-circuit (matching ``old_record.<owner_column>``
against ``auth.uid()``) is implemented in the broker, not here, because
it does not require a database round-trip — the registry row already
tells us the owner column.
"""

import logging
from typing import Any

import asyncpg

from .. import db
from .schemas import EnabledTable, EnableTableRequest

logger = logging.getLogger(__name__)


class RealtimeError(Exception):
    """Domain error raised by the realtime service layer."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# ---------------------------------------------------------------------------
# Row mappers
# ---------------------------------------------------------------------------


def _row_to_enabled_table(row: asyncpg.Record) -> EnabledTable:
    return EnabledTable(
        schema_name=row["schema_name"],
        table_name=row["table_name"],
        pk_columns=list(row["pk_columns"]),
        owner_column=row["owner_column"],
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# enable_table — service-role only
# ---------------------------------------------------------------------------


async def enable_table(
    conn: asyncpg.Connection,
    payload: EnableTableRequest,
) -> EnabledTable:
    """Opt a table into realtime by attaching the notify trigger.

    *conn* must be a service-role connection (or one whose effective
    privileges include ``execute`` on ``realtime.enable``).  The router
    is responsible for that gating; the service trusts the connection.

    Returns the freshly written :class:`EnabledTable` row so the caller
    can immediately echo it back to the client.
    """
    qualified = payload.table

    try:
        await conn.execute(
            "select realtime.enable($1::regclass, $2)",
            qualified,
            payload.owner_column,
        )
    except asyncpg.UndefinedTableError as exc:
        raise RealtimeError(
            "table_not_found",
            f"table {qualified!r} does not exist",
            status=404,
        ) from exc
    except asyncpg.InsufficientPrivilegeError as exc:
        raise RealtimeError(
            "forbidden",
            "service_role required to enable a table for realtime",
            status=403,
        ) from exc
    except asyncpg.RaiseError as exc:
        raise RealtimeError("invalid_table", str(exc), status=400) from exc

    schema_name, _, table_name = qualified.partition(".")
    row = await conn.fetchrow(
        """
        select schema_name, table_name, pk_columns, owner_column, created_at
        from realtime.enabled_tables
        where schema_name = $1 and table_name = $2
        """,
        schema_name,
        table_name,
    )
    if row is None:
        # The SQL helper returned without raising, but the registry row is
        # missing — should never happen, but treat it as a server fault.
        raise RealtimeError(
            "registry_missing",
            f"realtime.enable({qualified!r}) succeeded but the registry row is missing",
            status=500,
        )
    return _row_to_enabled_table(row)


# ---------------------------------------------------------------------------
# list_enabled
# ---------------------------------------------------------------------------


async def list_enabled(conn: asyncpg.Connection) -> list[EnabledTable]:
    """Return every row from ``realtime.enabled_tables`` visible to *conn*.

    Visibility is governed by the registry's RLS policies; in the v0.4
    schema both ``anon`` and ``authenticated`` may read every row, so the
    list is effectively the same regardless of the caller's role.
    """
    rows = await conn.fetch(
        """
        select schema_name, table_name, pk_columns, owner_column, created_at
        from realtime.enabled_tables
        order by schema_name, table_name
        """
    )
    return [_row_to_enabled_table(r) for r in rows]


async def get_enabled(
    conn: asyncpg.Connection,
    schema_name: str,
    table_name: str,
) -> EnabledTable | None:
    """Return one registry row, or ``None`` if the table is not enabled."""
    row = await conn.fetchrow(
        """
        select schema_name, table_name, pk_columns, owner_column, created_at
        from realtime.enabled_tables
        where schema_name = $1 and table_name = $2
        """,
        schema_name,
        table_name,
    )
    return _row_to_enabled_table(row) if row else None


# ---------------------------------------------------------------------------
# rls_check — per-subscriber visibility probe
# ---------------------------------------------------------------------------


# Quote an SQL identifier defensively.  Schema, table, and PK column names
# all originate from the catalog (via realtime.enable's regclass /
# pg_attribute lookup), so they are already safe.  We still double-quote
# them to handle reserved words and embedded uppercase, and we reject any
# identifier containing a literal double quote since asyncpg / psql will
# happily mis-interpret one.
def _quote_ident(name: str) -> str:
    if '"' in name:
        raise ValueError(f"identifier {name!r} contains a double quote")
    return '"' + name + '"'


async def rls_check(
    conn: asyncpg.Connection,
    *,
    schema_name: str,
    table_name: str,
    pk_columns: list[str],
    pk_values: list[Any],
    timeout: float | None = None,
) -> bool:
    """Probe whether *conn* (already role-scoped) can ``select`` the row.

    ``conn`` MUST come from :func:`db.as_role` so that ``set local role``
    and ``request.jwt.claims`` are in effect; this function does not
    re-scope the connection itself.

    Returns ``True`` if the role's RLS policies expose the row identified
    by ``pk_values`` (in the same order as ``pk_columns``), ``False``
    otherwise.  A timeout or transient error returns ``False`` and is
    logged — never propagated — so a misbehaving subscriber connection
    cannot stall the broker fan-out loop.
    """
    if len(pk_columns) != len(pk_values):
        raise ValueError(
            f"pk_columns/pk_values length mismatch: "
            f"{len(pk_columns)} vs {len(pk_values)}"
        )
    if not pk_columns:
        raise ValueError("at least one pk column is required")

    where_clauses = [
        f"{_quote_ident(col)} = ${i + 1}"
        for i, col in enumerate(pk_columns)
    ]
    sql = (
        f"select 1 from {_quote_ident(schema_name)}.{_quote_ident(table_name)} "
        f"where {' and '.join(where_clauses)} limit 1"
    )
    try:
        row = await conn.fetchrow(sql, *pk_values, timeout=timeout)
    except asyncpg.PostgresError as exc:
        logger.debug(
            "realtime rls_check failed for %s.%s pk=%s: %s",
            schema_name,
            table_name,
            pk_values,
            exc,
        )
        return False
    return row is not None


async def rls_check_with_role(
    role: str,
    claims: dict[str, Any],
    *,
    schema_name: str,
    table_name: str,
    pk_columns: list[str],
    pk_values: list[Any],
    timeout: float | None = None,
) -> bool:
    """Convenience wrapper that opens a role-scoped connection per check.

    The broker reuses an already-acquired connection per subscriber when
    fanning out a single notification across many topics, but for one-off
    checks (tests, REST control plane) this single-shot helper is
    simpler.
    """
    async with db.as_role(role, claims) as conn:
        return await rls_check(
            conn,
            schema_name=schema_name,
            table_name=table_name,
            pk_columns=pk_columns,
            pk_values=pk_values,
            timeout=timeout,
        )
