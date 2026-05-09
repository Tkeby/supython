"""Tests for ``supython gen types --lang ts`` — pure Python, no DB."""

import re

from supython.gen.types_ts import (
    _has_default,
    _pg_to_ts,
    _render,
    _render_table_shape,
    _safe_ts_col_name,
)


class _FakeRec:
    def __init__(self, **kwargs):
        self._data = kwargs

    def __getitem__(self, key):
        return self._data[key]


def _col(**kwargs):
    defaults = {
        "column_name": "id",
        "is_nullable": "NO",
        "data_type": "uuid",
        "udt_schema": "pg_catalog",
        "udt_name": "uuid",
        "column_default": None,
        "is_generated": "NEVER",
        "is_identity": "NO",
        "element_data_type": None,
        "element_udt_schema": None,
        "element_udt_name": None,
    }
    return _FakeRec(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# _pg_to_ts — type mapping
# ---------------------------------------------------------------------------


def test_type_mapping():
    cases: list[tuple[dict, str]] = [
        # strings
        ({"udt_name": "text"}, "string"),
        ({"udt_name": "varchar"}, "string"),
        ({"udt_name": "uuid"}, "string"),
        ({"udt_name": "inet"}, "string"),
        ({"udt_name": "bytea"}, "string"),
        # numbers
        ({"udt_name": "int4"}, "number"),
        ({"udt_name": "int8"}, "number"),
        ({"udt_name": "float8"}, "number"),
        ({"udt_name": "numeric"}, "number"),
        # boolean
        ({"udt_name": "bool"}, "boolean"),
        # dates as ISO strings
        ({"udt_name": "timestamptz"}, "string"),
        ({"udt_name": "timestamp"}, "string"),
        ({"udt_name": "date"}, "string"),
        # json
        ({"udt_name": "json"}, "Record<string, unknown>"),
        ({"udt_name": "jsonb"}, "Record<string, unknown>"),
    ]
    for kw, expected in cases:
        result = _pg_to_ts(
            udt_schema=kw.get("udt_schema", "pg_catalog"),
            udt_name=kw.get("udt_name", "text"),
            data_type=kw.get("data_type", "VARCHAR"),
            element=kw.get("element"),
            enum_types=kw.get("enum_types", set()),
        )
        assert result == expected, f"{kw} -> {result!r}, expected {expected!r}"


def test_fallback_unmapped_type():
    result = _pg_to_ts(
        udt_schema="pg_catalog",
        udt_name="hstore",  # not in _TS_TYPE_MAP
        data_type="USER-DEFINED",
        element=None,
        enum_types=set(),
    )
    assert result == "unknown"


def test_enum_mapping():
    enum_types = {("public", "color")}
    result = _pg_to_ts(
        udt_schema="public",
        udt_name="color",
        data_type="USER-DEFINED",
        element=None,
        enum_types=enum_types,
    )
    assert result == "public.color"


def test_array_column():
    result = _pg_to_ts(
        udt_schema="pg_catalog",
        udt_name="_text",
        data_type="ARRAY",
        element=("VARCHAR", "pg_catalog", "text"),
        enum_types=set(),
    )
    assert result == "string[]"


# ---------------------------------------------------------------------------
# _has_default
# ---------------------------------------------------------------------------


def test_has_default_with_column_default():
    c = _col(column_default="gen_random_uuid()")
    assert _has_default(c) is True


def test_has_default_with_generated_always():
    c = _col(is_generated="ALWAYS")
    assert _has_default(c) is True


def test_has_default_with_identity():
    c = _col(is_identity="YES")
    assert _has_default(c) is True


def test_has_default_none():
    c = _col(column_default=None, is_generated="NEVER", is_identity="NO")
    assert _has_default(c) is False


# ---------------------------------------------------------------------------
# _safe_ts_col_name
# ---------------------------------------------------------------------------

def test_keyword_column_sanitized():
    assert _safe_ts_col_name("type") == "type_"
    assert _safe_ts_col_name("class") == "class_"
    assert _safe_ts_col_name("interface") == "interface_"
    assert _safe_ts_col_name("export") == "export_"
    assert _safe_ts_col_name("delete") == "delete_"


def test_non_keyword_column_unchanged():
    assert _safe_ts_col_name("title") == "title"
    assert _safe_ts_col_name("email") == "email"
    assert _safe_ts_col_name("user_id") == "user_id"


# ---------------------------------------------------------------------------
# _render_table_shape — Row / Insert / Update optionality
# ---------------------------------------------------------------------------


def test_nullable_makes_optional_in_row():
    cols = [_col(column_name="note", is_nullable="YES", udt_name="text", data_type="VARCHAR")]
    row_lines, insert_lines, update_lines, rel_lines = _render_table_shape(cols, set(), [])
    assert "note?: string;" in row_lines[0]


def test_non_nullable_is_required_in_row():
    cols = [_col(column_name="title", is_nullable="NO", udt_name="text", data_type="VARCHAR")]
    row_lines, insert_lines, update_lines, rel_lines = _render_table_shape(cols, set(), [])
    assert "title: string;" in row_lines[0]


def test_insert_optional_with_default():
    cols = [
        _col(
            column_name="id",
            is_nullable="NO",
            udt_name="uuid",
            data_type="uuid",
            column_default="gen_random_uuid()",
        )
    ]
    row_lines, insert_lines, update_lines, rel_lines = _render_table_shape(cols, set(), [])
    assert "id?: string;" in insert_lines[0]


def test_insert_required_without_default():
    cols = [
        _col(
            column_name="title",
            is_nullable="NO",
            udt_name="text",
            data_type="VARCHAR",
            column_default=None,
            is_generated="NEVER",
            is_identity="NO",
        )
    ]
    row_lines, insert_lines, update_lines, rel_lines = _render_table_shape(cols, set(), [])
    assert "title: string;" in insert_lines[0]


def test_update_always_optional():
    cols = [
        _col(column_name="id", is_nullable="NO", udt_name="uuid"),
        _col(column_name="title", is_nullable="NO", udt_name="text", data_type="VARCHAR"),
        _col(column_name="note", is_nullable="YES", udt_name="text", data_type="VARCHAR"),
    ]
    row_lines, insert_lines, update_lines, rel_lines = _render_table_shape(cols, set(), [])
    for line in update_lines:
        assert "?:" in line


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------


def test_relationships_rendering():
    cols = [_col(column_name="user_id", is_nullable="NO", udt_name="uuid")]
    rels = [
        {
            "foreignKeyName": "todos_user_id_fkey",
            "columns": ["user_id"],
            "referencedRelation": "users",
            "referencedColumns": ["id"],
        }
    ]
    row_lines, insert_lines, update_lines, rel_lines = _render_table_shape(cols, set(), rels)
    joined = "\n".join(rel_lines)
    assert "foreignKeyName: " in joined
    assert "todos_user_id_fkey" in joined
    assert "'user_id'" in joined
    assert "referencedRelation: " in joined
    assert "users" in joined
    assert "'id'" in joined


def test_empty_relationships_omitted():
    cols = [_col()]
    row_lines, insert_lines, update_lines, rel_lines = _render_table_shape(cols, set(), [])
    assert rel_lines == []


# ---------------------------------------------------------------------------
# _render — full output
# ---------------------------------------------------------------------------

_TODOS_COLS = [
    _col(column_name="id", is_nullable="NO", udt_name="uuid",
         column_default="gen_random_uuid()"),
    _col(column_name="title", is_nullable="NO", udt_name="text",
         data_type="VARCHAR"),
    _col(column_name="done", is_nullable="NO", udt_name="bool",
         data_type="boolean", column_default="false"),
    _col(column_name="created_at", is_nullable="NO", udt_name="timestamptz",
         data_type="timestamptz", column_default="now()"),
]


def test_header_includes_timestamp():
    src = _render(
        schemas=["public"],
        enums={},
        tables=[("public", "todos")],
        columns={("public", "todos"): _TODOS_COLS},
        relationships={},
    )
    assert "Generated by " in src
    assert "Gen names: public" not in src
    assert "Generated at: " in src


def test_single_schema_no_prefix():
    src = _render(
        schemas=["auth"],
        enums={},
        tables=[("auth", "users")],
        columns={("auth", "users"): _TODOS_COLS},
        relationships={},
    )
    assert "export interface Database {" in src
    assert "auth" in src
    # Table name is not prefixed in single-schema mode
    assert "users" in src
    assert "Tables" in src


def test_empty_schema_does_not_crash():
    src = _render(
        schemas=["public"],
        enums={},
        tables=[],
        columns={},
        relationships={},
    )
    assert "export interface Database {" in src
    assert "Tables: {" in src
    assert "Views: {" in src


def test_export_type_for_enums():
    src = _render(
        schemas=["public"],
        enums={("public", "color"): ["red", "green"]},
        tables=[("public", "todos")],
        columns={("public", "todos"): _TODOS_COLS},
        relationships={},
    )
    assert 'export type Color = "red" | "green";' in src
    assert "public.color" not in src


def test_multi_schema_enum_rendering():
    src = _render(
        schemas=["public", "auth"],
        enums={
            ("public", "color"): ["red", "green"],
            ("auth", "role"): ["admin", "member"],
        },
        tables=[],
        columns={},
        relationships={},
    )
    assert '"red" | "green"' in src
    assert '"admin" | "member"' in src
    assert "export type Color" in src
    assert "export type AuthRole" in src
    # Enum values listed in schema Enums block
    assert "Enums:" in src
    assert 'color: "red" | "green"' in src
    assert 'role: "admin" | "member"' in src


def test_relationships_in_output():
    src = _render(
        schemas=["public"],
        enums={},
        tables=[("public", "todos")],
        columns={("public", "todos"): _TODOS_COLS},
        relationships={
            ("public", "todos"): [
                {
                    "foreignKeyName": "todos_user_id_fkey",
                    "columns": ["user_id"],
                    "referencedRelation": "users",
                    "referencedColumns": ["id"],
                }
            ]
        },
    )
    assert "Relationships: [" in src
    assert "foreignKeyName" in src
    assert "todos_user_id_fkey" in src


def test_row_insert_update_present():
    src = _render(
        schemas=["public"],
        enums={},
        tables=[("public", "todos")],
        columns={("public", "todos"): _TODOS_COLS},
        relationships={},
    )
    assert "Row:" in src
    assert "Insert:" in src
    assert "Update:" in src
    # Non-nullable, no-default title is required in Insert
    assert "title: string;" in src
    # done has default false — should be optional in Insert
    found = re.search(r"done:.*boolean", src)
    assert found is not None


def test_missing_table_omitted():
    src = _render(
        schemas=["public"],
        enums={},
        tables=[("public", "todos")],
        columns={},  # no column data for todos
        relationships={},
    )
    assert "todos" not in src
