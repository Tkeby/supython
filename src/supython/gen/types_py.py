"""Render a typed ``db_schema.py`` from Postgres schema introspection.

Public entry point: :func:`render_types_py`. The returned string is the full
contents of a self-contained Python module with one ``StrEnum`` per Postgres
enum and one ``@dataclass`` + matching ``TypedDict`` per table or view in the
selected schemas.

The generator opens its own asyncpg connection and closes it before returning;
it does not depend on the supython service running.
"""

import keyword
import re
from datetime import UTC, datetime

import asyncpg

from ..settings import get_settings
from ._introspect import _fetch_columns, _fetch_enums, _fetch_tables

_SIMPLE_MAP: dict[str, tuple[str, str | None]] = {
    "text": ("str", None),
    "varchar": ("str", None),
    "bpchar": ("str", None),
    "char": ("str", None),
    "citext": ("str", None),
    "name": ("str", None),
    "int2": ("int", None),
    "int4": ("int", None),
    "int8": ("int", None),
    "float4": ("float", None),
    "float8": ("float", None),
    "numeric": ("Decimal", "Decimal"),
    "money": ("Decimal", "Decimal"),
    "bool": ("bool", None),
    "uuid": ("UUID", "UUID"),
    "timestamptz": ("datetime", "datetime"),
    "timestamp": ("datetime", "datetime"),
    "date": ("date", "date"),
    "time": ("time", "time"),
    "timetz": ("time", "time"),
    "interval": ("timedelta", "timedelta"),
    "bytea": ("bytes", None),
    "json": ("dict[str, Any]", "Any"),
    "jsonb": ("dict[str, Any]", "Any"),
    "inet": ("str", None),
    "cidr": ("str", None),
    "macaddr": ("str", None),
    "tsvector": ("str", None),
    "tsquery": ("str", None),
    "bit": ("str", None),
    "varbit": ("str", None),
    "oid": ("int", None),
}


def _safe_col_name(name: str) -> str:
    if keyword.iskeyword(name) or keyword.issoftkeyword(name):
        return f"{name}_"
    return name


async def render_types_py(schemas: list[str]) -> str:
    """Connect to ``DATABASE_URL`` and return a rendered ``db_schema.py`` module."""
    s = get_settings()
    conn = await asyncpg.connect(s.database_url)
    try:
        enums = await _fetch_enums(conn, schemas)
        tables = await _fetch_tables(conn, schemas)
        columns = await _fetch_columns(conn, schemas)
    finally:
        await conn.close()
    return _render(schemas, enums, tables, columns)



def _class_name(schema: str, table: str, schemas: list[str]) -> str:
    base = "".join(part.capitalize() for part in re.split(r"[_\-]", table) if part)
    if not base:
        base = "Table"
    if schema == "public" or len(schemas) == 1:
        return base
    return f"{schema.capitalize()}{base}"


def _safe_enum_attr(label: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", label).upper()
    if not s or s[0].isdigit():
        s = "_" + s
    return s


def _pg_to_py(
    udt_schema: str,
    udt_name: str,
    data_type: str,
    element: tuple[str, str, str] | None,
    enum_classes: dict[tuple[str, str], str],
    imports: set[str],
) -> tuple[str, str | None]:
    """Return (annotation, unmapped_comment_or_None)."""
    if data_type == "ARRAY" and element is not None:
        elem_ann, elem_unmapped = _pg_to_py(
            element[1], element[2], element[0], None, enum_classes, imports
        )
        return f"list[{elem_ann}]", elem_unmapped

    if data_type == "USER-DEFINED" and (udt_schema, udt_name) in enum_classes:
        return enum_classes[(udt_schema, udt_name)], None

    if udt_name in _SIMPLE_MAP:
        ann, imp = _SIMPLE_MAP[udt_name]
        if imp:
            imports.add(imp)
        return ann, None

    imports.add("Any")
    return "Any", f"unmapped: {udt_schema}.{udt_name}"


def _render(
    schemas: list[str],
    enums: dict[tuple[str, str], list[str]],
    tables: list[tuple[str, str]],
    columns: dict[tuple[str, str], list[asyncpg.Record]],
) -> str:
    imports: set[str] = set()

    enum_classes: dict[tuple[str, str], str] = {
        (schema, name): _class_name(schema, name, schemas)
        for (schema, name) in enums
    }

    body: list[str] = []

    for (schema, name), labels in sorted(enums.items()):
        cls = enum_classes[(schema, name)]
        body.append("")
        body.append(f"# --- enum {schema}.{name} {'-' * (60 - len(schema) - len(name))}")
        body.append("")
        body.append(f"class {cls}(StrEnum):")
        for lbl in labels:
            body.append(f"    {_safe_enum_attr(lbl)} = {lbl!r}")

    has_table = False
    for schema, table in tables:
        cols = columns.get((schema, table), [])
        if not cols:
            continue
        has_table = True
        cls = _class_name(schema, table, schemas)

        rendered_cols: list[tuple[str, str, bool, str | None]] = []
        for c in cols:
            element = None
            if c["element_data_type"]:
                element = (
                    c["element_data_type"],
                    c["element_udt_schema"],
                    c["element_udt_name"],
                )
            ann, unmapped = _pg_to_py(
                c["udt_schema"],
                c["udt_name"],
                c["data_type"],
                element,
                enum_classes,
                imports,
            )
            nullable = c["is_nullable"] == "YES"
            col_name = _safe_col_name(c["column_name"])
            rendered_cols.append((col_name, ann, nullable, unmapped))

        body.append("")
        body.append(f"# --- {schema}.{table} {'-' * (64 - len(schema) - len(table))}")
        body.append("")
        body.append("@dataclass(kw_only=True, slots=True)")
        body.append(f"class {cls}:")
        for col_name, ann, nullable, unmapped in rendered_cols:
            line = (
                f"    {col_name}: {ann} | None = None"
                if nullable
                else f"    {col_name}: {ann}"
            )
            if unmapped:
                line += f"  # {unmapped}"
            body.append(line)

        body.append("")
        body.append("    @classmethod")
        body.append(f'    def from_record(cls, record: Mapping[str, Any]) -> "{cls}":')
        body.append("        fields = cls.__dataclass_fields__")
        body.append(
            "        return cls(**{f: v for f, v in record.items() if f in fields})"
        )

        has_kw = any(
            _safe_col_name(c["column_name"]) != c["column_name"]
            for c in cols
        )
        if has_kw:
            _emit_typeddict_functional(body, cls, rendered_cols)
        else:
            _emit_typeddict_class(body, cls, rendered_cols)

    header: list[str] = []
    header.append('"""Generated by `supython gen types --lang py`. Do not edit.')
    header.append("")
    header.append(f"Schemas: {', '.join(schemas)}")
    header.append(f"Generated at: {datetime.now(UTC).isoformat()}")
    header.append('"""')

    import_lines: list[str] = []
    if has_table:
        import_lines.append("from collections.abc import Mapping")
        import_lines.append("from dataclasses import dataclass")

    datetime_syms = sorted(
        {i for i in imports if i in {"datetime", "date", "time", "timedelta"}}
    )
    if datetime_syms:
        import_lines.append(f"from datetime import {', '.join(datetime_syms)}")
    if "Decimal" in imports:
        import_lines.append("from decimal import Decimal")
    if enums:
        import_lines.append("from enum import StrEnum")
    typing_syms: set[str] = set()
    if "Any" in imports or has_table:
        typing_syms.add("Any")
    if has_table:
        typing_syms.add("TypedDict")
    if typing_syms:
        import_lines.append(f"from typing import {', '.join(sorted(typing_syms))}")
    if "UUID" in imports:
        import_lines.append("from uuid import UUID")

    parts: list[str] = []
    parts.extend(header)
    if import_lines:
        parts.append("")
        parts.extend(import_lines)
    parts.extend(body)
    return "\n".join(parts).rstrip() + "\n"


def _emit_typeddict_class(
    body: list[str],
    cls: str,
    rendered_cols: list[tuple[str, str, bool, str | None]],
) -> None:
    body.append("")
    body.append(f"class {cls}Row(TypedDict):")
    for col_name, ann, nullable, _ in rendered_cols:
        body.append(
            f"    {col_name}: {ann} | None" if nullable else f"    {col_name}: {ann}"
        )


def _emit_typeddict_functional(
    body: list[str],
    cls: str,
    rendered_cols: list[tuple[str, str, bool, str | None]],
) -> None:
    body.append(f"{cls}Row = TypedDict(\"{cls}Row\", {{")
    for col_name, ann, nullable, _ in rendered_cols:
        ann_str = f"{ann} | None" if nullable else ann
        body.append(f'    "{col_name}": {ann_str},')
    body.append("})")


__all__ = ["render_types_py"]
