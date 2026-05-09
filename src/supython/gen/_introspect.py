"""Shared Postgres schema introspection queries used by type generators.

Both ``types_py.py`` (Python dataclasses) and ``types_ts.py`` (TypeScript
``Database`` interface) use these functions to fetch metadata from
``information_schema`` and ``pg_catalog``.
"""

import asyncpg


async def _fetch_enums(
    conn: asyncpg.Connection, schemas: list[str]
) -> dict[tuple[str, str], list[str]]:
    rows = await conn.fetch(
        """
        select n.nspname  as schema,
               t.typname  as name,
               e.enumlabel as label
        from pg_type t
        join pg_enum e       on e.enumtypid = t.oid
        join pg_namespace n  on n.oid = t.typnamespace
        where n.nspname = any($1::text[])
        order by n.nspname, t.typname, e.enumsortorder
        """,
        list(schemas),
    )
    out: dict[tuple[str, str], list[str]] = {}
    for r in rows:
        out.setdefault((r["schema"], r["name"]), []).append(r["label"])
    return out


async def _fetch_tables(
    conn: asyncpg.Connection, schemas: list[str]
) -> list[tuple[str, str]]:
    rows = await conn.fetch(
        """
        select table_schema, table_name
        from information_schema.tables
        where table_schema = any($1::text[])
          and table_type in ('BASE TABLE', 'VIEW')
        order by table_schema, table_name
        """,
        list(schemas),
    )
    return [(r["table_schema"], r["table_name"]) for r in rows]


async def _fetch_columns(
    conn: asyncpg.Connection, schemas: list[str]
) -> dict[tuple[str, str], list[asyncpg.Record]]:
    rows = await conn.fetch(
        """
        select c.table_schema,
               c.table_name,
               c.column_name,
               c.ordinal_position,
               c.is_nullable,
               c.data_type,
               c.udt_schema,
               c.udt_name,
               c.column_default,
               c.is_generated,
               c.is_identity,
               e.data_type   as element_data_type,
               e.udt_schema  as element_udt_schema,
               e.udt_name    as element_udt_name
        from information_schema.columns c
        join information_schema.tables t
          on t.table_catalog = c.table_catalog
         and t.table_schema  = c.table_schema
         and t.table_name    = c.table_name
        left join information_schema.element_types e
          on  e.object_catalog            = c.table_catalog
          and e.object_schema             = c.table_schema
          and e.object_name               = c.table_name
          and e.object_type               = case t.table_type
                                                when 'VIEW' then 'VIEW'
                                                else 'TABLE'
                                            end
          and e.collection_type_identifier = c.dtd_identifier
        where c.table_schema = any($1::text[])
          and t.table_type in ('BASE TABLE', 'VIEW')
        order by c.table_schema, c.table_name, c.ordinal_position
        """,
        list(schemas),
    )
    grouped: dict[tuple[str, str], list[asyncpg.Record]] = {}
    for r in rows:
        grouped.setdefault((r["table_schema"], r["table_name"]), []).append(r)
    return grouped


async def _fetch_relationships(
    conn: asyncpg.Connection, schemas: list[str]
) -> dict[tuple[str, str], list[dict[str, any]]]:  # type: ignore[no-any-return]
    rows = await conn.fetch(
        """
        select
            n.nspname as table_schema,
            c.relname as table_name,
            con.conname as constraint_name,
            (
                select array_agg(a.attname order by ord)
                from unnest(con.conkey) with ordinality as t(attnum, ord)
                join pg_attribute a
                    on a.attnum = t.attnum and a.attrelid = con.conrelid
            ) as columns,
            ref_c.relname as foreign_table_name,
            (
                select array_agg(a.attname order by ord)
                from unnest(con.confkey) with ordinality as t(attnum, ord)
                join pg_attribute a
                    on a.attnum = t.attnum and a.attrelid = con.confrelid
            ) as foreign_columns
        from pg_constraint con
        join pg_class c on c.oid = con.conrelid
        join pg_namespace n on n.oid = c.relnamespace
        join pg_class ref_c on ref_c.oid = con.confrelid
        where con.contype = 'f'
          and n.nspname = any($1::text[])
        order by n.nspname, c.relname, con.conname
        """,
        list(schemas),
    )
    out: dict[tuple[str, str], list[dict[str, any]]] = {}  # type: ignore[no-any-return]
    for r in rows:
        key = (r["table_schema"], r["table_name"])
        out.setdefault(key, []).append(
            {
                "foreignKeyName": r["constraint_name"],
                "columns": r["columns"],
                "referencedRelation": r["foreign_table_name"],
                "referencedColumns": r["foreign_columns"],
            }
        )
    return out
