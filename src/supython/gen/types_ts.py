"""Render a TypeScript ``Database`` interface from Postgres schema introspection.

Public entry point: :func:`render_types_ts`. The returned string is a full
TypeScript module exporting a ``Database`` interface compatible with
``@supabase/postgrest-js`` and ``@supython/sdk``.

The generator opens its own asyncpg connection and closes it before returning;
it does not depend on the supython service running.
"""

from datetime import UTC, datetime

import asyncpg

from ..settings import get_settings
from ._introspect import (
    _fetch_columns,
    _fetch_enums,
    _fetch_relationships,
    _fetch_tables,
)
from .types_py import _class_name

_TS_TYPE_MAP: dict[str, str] = {
    # strings
    "text": "string",
    "varchar": "string",
    "bpchar": "string",
    "char": "string",
    "citext": "string",
    "name": "string",
    "inet": "string",
    "cidr": "string",
    "macaddr": "string",
    "tsvector": "string",
    "tsquery": "string",
    "bit": "string",
    "varbit": "string",
    "uuid": "string",
    "bytea": "string",
    "oid": "string",
    # numbers
    "int2": "number",
    "int4": "number",
    "int8": "number",
    "float4": "number",
    "float8": "number",
    "numeric": "number",
    "money": "number",
    # boolean
    "bool": "boolean",
    # dates/times as ISO strings
    "timestamptz": "string",
    "timestamp": "string",
    "date": "string",
    "time": "string",
    "timetz": "string",
    "interval": "string",
    # json
    "json": "Record<string, unknown>",
    "jsonb": "Record<string, unknown>",
}

# TypeScript reserved words that cannot be used as bare identifiers
_TS_KEYWORDS: set[str] = {
    # strict mode reserved
    "break",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "debugger",
    "default",
    "delete",
    "do",
    "else",
    "enum",
    "export",
    "extends",
    "false",
    "finally",
    "for",
    "function",
    "if",
    "import",
    "in",
    "instanceof",
    "new",
    "null",
    "return",
    "super",
    "switch",
    "this",
    "throw",
    "true",
    "try",
    "typeof",
    "var",
    "void",
    "while",
    "with",
    "implements",
    "interface",
    "let",
    "package",
    "private",
    "protected",
    "public",
    "static",
    "yield",
    "await",
    "abstract",
    "as",
    "asserts",
    "async",
    "constructor",
    "declare",
    "from",
    "get",
    "infer",
    "intrinsic",
    "is",
    "keyof",
    "module",
    "namespace",
    "never",
    "of",
    "readonly",
    "require",
    "set",
    "type",
    "unique",
    "unknown",
}


def _safe_ts_col_name(name: str) -> str:
    """Append _ if column name is a TS reserved word."""
    if name in _TS_KEYWORDS:
        return f"{name}_"
    return name


def _pg_to_ts(
    udt_schema: str,
    udt_name: str,
    data_type: str,
    element: tuple[str, str, str] | None,
    enum_types: set[tuple[str, str]],
) -> str:
    """Return TypeScript type annotation string."""
    if data_type == "ARRAY" and element is not None:
        elem_type = _pg_to_ts(element[1], element[2], element[0], None, enum_types)
        return f"{elem_type}[]"

    if data_type == "USER-DEFINED" and (udt_schema, udt_name) in enum_types:
        # Enum type - will be rendered as "schema.name" union type
        return f"{udt_schema}.{udt_name}"

    if udt_name in _TS_TYPE_MAP:
        return _TS_TYPE_MAP[udt_name]

    return "unknown"


def _has_default(col: asyncpg.Record) -> bool:
    """Return True if column has a default value, is generated, or is identity."""
    return (
        col["column_default"] is not None
        or col["is_generated"] != "NEVER"
        or col["is_identity"] == "YES"
    )


def _render_table_shape(
    cols: list[asyncpg.Record],
    enum_types: set[tuple[str, str]],
    relationships: list[dict],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Render Row, Insert, Update, and Relationships lines for a table.

    Returns (row_lines, insert_lines, update_lines, relationships_lines).
    """
    row_lines: list[str] = []
    insert_lines: list[str] = []
    update_lines: list[str] = []

    for c in cols:
        element = None
        if c["element_data_type"]:
            element = (
                c["element_data_type"],
                c["element_udt_schema"],
                c["element_udt_name"],
            )
        ts_type = _pg_to_ts(
            c["udt_schema"],
            c["udt_name"],
            c["data_type"],
            element,
            enum_types,
        )

        col_name = _safe_ts_col_name(c["column_name"])
        nullable = c["is_nullable"] == "YES"
        has_default = _has_default(c)

        # Row: required if NOT NULL
        row_optional = nullable
        row_lines.append(
            f"        {col_name}{'?' if row_optional else ''}: {ts_type};"
        )

        # Insert: required if NOT NULL and no default
        insert_optional = nullable or has_default
        insert_lines.append(
            f"        {col_name}{'?' if insert_optional else ''}: {ts_type};"
        )

        # Update: always optional
        update_lines.append(f"        {col_name}?: {ts_type};")

    # Relationships
    rel_lines: list[str] = []
    if relationships:
        for rel in relationships:
            columns = rel["columns"]
            referenced = rel["referencedRelation"]
            ref_cols = rel["referencedColumns"]
            rel_lines.append("      {")
            fk_name = rel["foreignKeyName"]
            rel_lines.append(f'        foreignKeyName: "{fk_name}";')
            cols_str = ", ".join(repr(c) for c in columns)
            rel_lines.append(f"        columns: [{cols_str}];")
            rel_lines.append(f'        referencedRelation: "{referenced}";')
            ref_str = ", ".join(repr(c) for c in ref_cols)
            rel_lines.append(f"        referencedColumns: [{ref_str}];")
            rel_lines.append("      },")

    return row_lines, insert_lines, update_lines, rel_lines


def _render(
    schemas: list[str],
    enums: dict[tuple[str, str], list[str]],
    tables: list[tuple[str, str]],
    columns: dict[tuple[str, str], list[asyncpg.Record]],
    relationships: dict[tuple[str, str], list[dict]],
) -> str:
    """Render the full TypeScript Database interface."""
    # Build enum type names set
    enum_types: set[tuple[str, str]] = set(enums.keys())

    # Group tables by schema
    by_schema: dict[str, list[tuple[str, str]]] = {}
    for schema, table in tables:
        by_schema.setdefault(schema, []).append((schema, table))

    body: list[str] = []

    # Emit enum type aliases at top level
    for (schema, name), labels in sorted(enums.items()):
        enum_name = _class_name(schema, name, schemas)
        label_union = " | ".join(f'"{lbl}"' for lbl in labels)
        body.append(f"export type {enum_name} = {label_union};")
        body.append("")

    # Start Database interface
    body.append("export interface Database {")

    for schema in sorted(schemas):
        schema_tables = by_schema.get(schema, [])

        body.append(f"  {schema}: {{")

        # Tables section
        body.append("    Tables: {")
        for s, table in schema_tables:
            cols = columns.get((s, table), [])
            if not cols:
                continue

            rels = relationships.get((s, table), [])

            row_lines, insert_lines, update_lines, rel_lines = _render_table_shape(
                cols, enum_types, rels
            )

            body.append(f"      {table}: {{")
            body.append("        Row: {")
            body.extend(row_lines)
            body.append("        };")
            body.append("        Insert: {")
            body.extend(insert_lines)
            body.append("        };")
            body.append("        Update: {")
            body.extend(update_lines)
            body.append("        };")

            if rel_lines:
                body.append("        Relationships: [")
                body.extend(rel_lines)
                body.append("        ];")

            body.append("      };")
        body.append("    };")

        # Views section - deferred (needs table_type tracking to separate
        # from BASE TABLE entries already rendered in Tables above)
        body.append("    Views: {")
        body.append("    };")

        # Functions section (RPC) - deferred
        body.append("    Functions: {")
        body.append("    };")

        # Enums section - export as type aliases at schema level
        schema_enums = [
            (s, n) for s, n in enums if s == schema
        ]
        if schema_enums:
            body.append("    Enums: {")
            for s, name in sorted(schema_enums):
                enum_name = _class_name(s, name, schemas)
                labels = enums[(s, name)]
                label_union = " | ".join(f'"{lbl}"' for lbl in labels)
                body.append(f"      {name}: {label_union};")
            body.append("    };")
        else:
            body.append("    Enums: {")
            body.append("    };")

        body.append("  };")

    body.append("}")

    # Build final output
    lines: list[str] = []
    lines.append("// Generated by `supython gen types --lang ts`. Do not edit.")
    lines.append("//")
    lines.append(f"// Schemas: {', '.join(schemas)}")
    lines.append(f"// Generated at: {datetime.now(UTC).isoformat()}")
    lines.append("")
    lines.extend(body)
    lines.append("")

    return "\n".join(lines)


async def render_types_ts(schemas: list[str]) -> str:
    """Connect to ``DATABASE_URL`` and return a rendered TypeScript ``Database`` interface."""
    s = get_settings()
    conn = await asyncpg.connect(s.database_url)
    try:
        enums = await _fetch_enums(conn, schemas)
        tables = await _fetch_tables(conn, schemas)
        columns = await _fetch_columns(conn, schemas)
        relationships = await _fetch_relationships(conn, schemas)
    finally:
        await conn.close()
    return _render(schemas, enums, tables, columns, relationships)


__all__ = ["render_types_ts"]
