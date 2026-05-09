import re
from typing import Any, Literal
from uuid import UUID, uuid4

import asyncpg

from ..errors import AdminError
from ..schemas import (
    DryRunResponse,
    MigrationRecord,
    RlsPolicy,
    RowsPage,
    SchemaInfo,
    SqlExecRequest,
    SqlExecResponse,
    TableInfo,
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DDL_ALLOWED = re.compile(r"^\s*(create|drop|alter)\s+policy\b", re.IGNORECASE | re.DOTALL)


def _safe_value(v: Any) -> Any:
    """Ensure values are JSON-serializable (bytes → hex, else identity)."""
    if isinstance(v, bytes):
        return r"\x" + v.hex()
    return v


def _check_ident(kind: str, value: str) -> None:
    if not _IDENT_RE.match(value):
        raise AdminError(f"invalid_{kind}", f"invalid {kind} name: {value}", 400)


def _qident(schema: str, table: str) -> str:
    _check_ident("schema", schema)
    _check_ident("table", table)
    return f'"{schema}"."{table}"'


async def list_schemas(conn: asyncpg.Connection) -> list[SchemaInfo]:
    rows = await conn.fetch(
        """
        select n.nspname as name,
               pg_catalog.pg_get_userbyid(n.nspowner) as owner,
               n.nspname not in ('pg_catalog', 'information_schema') as is_user
        from pg_catalog.pg_namespace n
        where n.nspname not like 'pg_%'
        order by n.nspname
        """,
    )
    return [SchemaInfo(**dict(r)) for r in rows]


async def list_tables(conn: asyncpg.Connection, schema: str) -> list[TableInfo]:
    _check_ident("schema", schema)
    rows = await conn.fetch(
        """
        select c.relname as name,
               c.relrowsecurity as rls_enabled
        from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname = $1
          and c.relkind = 'r'
        order by c.relname
        """,
        schema,
    )
    return [TableInfo(**dict(r)) for r in rows]


async def read_rows(
    conn: asyncpg.Connection,
    schema: str,
    table: str,
    limit: int,
    offset: int,
    order: str | None,
) -> RowsPage:
    qident = _qident(schema, table)
    order_sql = ""
    if order:
        if not all(c.isalnum() or c in "_," for c in order):
            raise AdminError("invalid_order", f"invalid order clause: {order}", 400)
        order_sql = f" order by {order}"
    try:
        rows = await conn.fetch(
            f"select * from {qident}{order_sql} limit $1 offset $2",
            limit,
            offset,
        )
        total = await conn.fetchval(f"select count(*) from {qident}")
    except asyncpg.UndefinedTableError as exc:
        raise AdminError("not_found", str(exc), 404) from exc
    except asyncpg.PostgresError as exc:
        raise AdminError("sql_error", str(exc), 400) from exc
    cols = list(rows[0].keys()) if rows else []
    return RowsPage(
        columns=cols,
        rows=[[_safe_value(r[c]) for c in cols] for r in rows],
        total=total or 0,
    )


def preview_claims(role: Literal["authenticated", "anon"], sub: UUID | None) -> dict[str, Any]:
    if role == "authenticated" and sub is None:
        raise AdminError(
            "preview_sub_required",
            "authenticated preview needs impersonate_sub",
            422,
        )
    return {
        "role": role,
        "sub": str(sub) if sub else str(uuid4()),
        "aud": "authenticated" if role == "authenticated" else "anon",
    }


async def execute_sql(conn: asyncpg.Connection, payload: SqlExecRequest) -> SqlExecResponse:
    async with conn.transaction():
        if payload.read_only:
            await conn.execute("set local transaction read only")
        try:
            rows = await conn.fetch(payload.statement)
        except asyncpg.PostgresError as exc:
            raise AdminError("sql_error", str(exc), 400) from exc
    cols = list(rows[0].keys()) if rows else []
    return SqlExecResponse(
        columns=cols,
        rows=[[_safe_value(r[c]) for c in cols] for r in rows],
        row_count=len(rows),
    )


async def list_policies(conn: asyncpg.Connection, schema: str, table: str) -> list[RlsPolicy]:
    _qident(schema, table)
    try:
        rows = await conn.fetch(
            """
            select schemaname, tablename, policyname, permissive,
                   roles, cmd, qual, with_check
            from pg_policies
            where schemaname = $1 and tablename = $2
            order by policyname
            """,
            schema,
            table,
        )
    except asyncpg.PostgresError as exc:
        raise AdminError("sql_error", str(exc), 400) from exc
    return [RlsPolicy(**dict(r)) for r in rows]


async def dry_run_policy(conn: asyncpg.Connection, ddl: str, sample_query: str) -> DryRunResponse:
    if not _DDL_ALLOWED.match(ddl):
        raise AdminError(
            "invalid_ddl",
            "dry-run only accepts (create|drop|alter) policy statements",
            422,
        )
    if len(ddl) > 8192:
        raise AdminError("invalid_ddl", "ddl too long", 422)

    class _Rollback(Exception):
        def __init__(self, rows: list[asyncpg.Record]) -> None:
            self.rows = rows

    try:
        async with conn.transaction():
            await conn.execute(ddl)
            rows = await conn.fetch(sample_query)
            raise _Rollback(rows)
    except _Rollback as rb:
        cols = list(rb.rows[0].keys()) if rb.rows else []
        return DryRunResponse(
            columns=cols,
            rows=[[_safe_value(r[c]) for c in cols] for r in rb.rows],
        )
    except asyncpg.PostgresError as exc:
        raise AdminError("sql_error", str(exc), 400) from exc


async def list_migrations(conn: asyncpg.Connection) -> list[MigrationRecord]:
    out: list[MigrationRecord] = []
    try:
        supython_rows = await conn.fetch(
            """
            select name as version, applied_at
            from supython.migrations
            order by name
            """
        )
    except asyncpg.PostgresError as exc:
        raise AdminError("sql_error", str(exc), 400) from exc
    out.extend(
        MigrationRecord(version=r["version"], applied_at=r["applied_at"], source="supython")
        for r in supython_rows
    )

    try:
        has_dbmate = await conn.fetchval(
            "select to_regclass('public.schema_migrations') is not null"
        )
        if has_dbmate:
            dbmate_rows = await conn.fetch(
                "select version from public.schema_migrations order by version"
            )
            out.extend(
                MigrationRecord(version=r["version"], applied_at=None, source="dbmate")
                for r in dbmate_rows
            )
    except asyncpg.PostgresError as exc:
        raise AdminError("sql_error", str(exc), 400) from exc
    return out
