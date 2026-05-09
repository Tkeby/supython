"""Admin service layer for the realtime surface.

Pure async functions over ``asyncpg.Connection``. No FastAPI imports.
"""

import asyncpg

from ...realtime.schemas import EnabledTable


def _row_to_enabled_table(row: asyncpg.Record) -> EnabledTable:
    return EnabledTable(
        schema_name=row["schema_name"],
        table_name=row["table_name"],
        pk_columns=list(row["pk_columns"]),
        owner_column=row["owner_column"],
        created_at=row["created_at"],
    )


async def list_enabled_tables(conn: asyncpg.Connection) -> list[EnabledTable]:
    """Return every row from ``realtime.enabled_tables`` (service_role view)."""
    rows = await conn.fetch(
        """
        select schema_name, table_name, pk_columns, owner_column, created_at
        from realtime.enabled_tables
        order by schema_name, table_name
        """
    )
    return [_row_to_enabled_table(r) for r in rows]
