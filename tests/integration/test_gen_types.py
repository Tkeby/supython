"""Tests for ``supython gen types`` (``--lang py`` and ``--lang ts``).

Hits the live test database (the same one the rest of the suite uses), adds
a temp enum / nullable column / dummy schema object, renders the module,
``exec()``-s it (Python) or asserts substrings (TypeScript), and asserts shape.
"""

import ast
import os
import typing
from dataclasses import fields, is_dataclass
from enum import StrEnum
from pathlib import Path
from unittest.mock import patch

import asyncpg
import pytest
import pytest_asyncio
from typer.testing import CliRunner

from supython.cli import app
from supython.gen import render_types_py, render_types_ts


@pytest.fixture(autouse=True)
def clean_auth_tables():
    """Override the global DB-cleaning fixture: gen tests don't need clean auth rows."""
    yield


@pytest_asyncio.fixture
async def temp_schema(pool: asyncpg.Pool):
    """Add a temp enum + nullable column to ``public.todos``; drop them on exit."""
    async with pool.acquire() as conn:
        await conn.execute("drop type if exists public.color cascade")
        await conn.execute("create type public.color as enum ('red', 'green')")
        await conn.execute("alter table public.todos add column note text")
        await conn.execute("alter table public.todos add column tags text[]")
    try:
        yield
    finally:
        async with pool.acquire() as conn:
            await conn.execute("alter table public.todos drop column if exists note")
            await conn.execute("alter table public.todos drop column if exists tags")
            await conn.execute("drop type if exists public.color cascade")


@pytest_asyncio.fixture
async def keyword_column(pool: asyncpg.Pool):
    """Add a column named ``type`` (a Python keyword) to ``public.todos``."""
    async with pool.acquire() as conn:
        await conn.execute("alter table public.todos add column type text")
    try:
        yield
    finally:
        async with pool.acquire() as conn:
            await conn.execute("alter table public.todos drop column if exists type")


def _exec(src: str) -> dict:
    ns: dict = {}
    exec(compile(src, "<generated>", "exec"), ns)
    return ns


async def test_render_public_schema_emits_dataclass_and_typeddict(temp_schema):
    src = await render_types_py(schemas=["public"])

    ast.parse(src)

    ns = _exec(src)

    Todos = ns["Todos"]
    assert is_dataclass(Todos)

    field_names = {f.name for f in fields(Todos)}
    assert {"id", "user_id", "title", "done", "created_at", "note", "tags"} <= field_names

    hints = typing.get_type_hints(Todos)
    import datetime as _dt
    import uuid as _uuid

    assert hints["id"] is _uuid.UUID
    assert hints["title"] is str
    assert hints["done"] is bool
    assert hints["created_at"] is _dt.datetime
    assert hints["note"] == (str | None)
    assert hints["tags"] == (list[str] | None)

    TodosRow = ns["TodosRow"]
    assert typing.is_typeddict(TodosRow)
    row_hints = typing.get_type_hints(TodosRow)
    assert row_hints["id"] is _uuid.UUID
    assert row_hints["note"] == (str | None)
    assert row_hints["tags"] == (list[str] | None)
    assert set(row_hints) == field_names


async def test_render_emits_strenum_for_user_defined_type(temp_schema):
    src = await render_types_py(schemas=["public"])

    ns = _exec(src)

    Color = ns["Color"]
    assert issubclass(Color, StrEnum)
    members = {m.value for m in Color}
    assert members == {"red", "green"}


async def test_render_multi_schema_prefixes_non_public(temp_schema):
    src = await render_types_py(schemas=["public", "auth"])

    ast.parse(src)

    ns = _exec(src)

    assert "Todos" in ns
    assert is_dataclass(ns["Todos"])

    assert "AuthUsers" in ns, "auth.users should be prefixed in multi-schema mode"
    assert is_dataclass(ns["AuthUsers"])
    assert typing.is_typeddict(ns["AuthUsersRow"])


async def test_render_single_schema_does_not_prefix(temp_schema):
    src = await render_types_py(schemas=["auth"])
    ns = _exec(src)

    assert "Users" in ns, "single-schema mode must not prefix even when not 'public'"
    assert "AuthUsers" not in ns


async def test_render_emits_from_record(temp_schema):
    src = await render_types_py(schemas=["public"])

    ast.parse(src)

    ns = _exec(src)

    Todos = ns["Todos"]
    assert hasattr(Todos, "from_record")

    class FakeRecord:
        def items(self):
            import uuid as _uuid

            return [
                ("id", _uuid.uuid4()),
                ("user_id", _uuid.uuid4()),
                ("title", "test"),
                ("done", False),
                ("created_at", None),
                ("note", None),
                ("tags", None),
                ("extra_col_ignored", 42),
            ]

    todo = Todos.from_record(FakeRecord())
    assert todo.title == "test"
    assert todo.done is False


async def test_render_keyword_column_gets_underscore_suffix(temp_schema, keyword_column):
    src = await render_types_py(schemas=["public"])

    ast.parse(src, filename="<generated>")

    ns = _exec(src)

    Todos = ns["Todos"]
    field_names = {f.name for f in fields(Todos)}
    assert "type_" in field_names
    assert "type" not in field_names

    TodosRow = ns["TodosRow"]
    row_hints = typing.get_type_hints(TodosRow)
    assert "type_" in row_hints
    assert "type" not in row_hints


async def test_render_header_includes_timestamp(temp_schema):
    src = await render_types_py(schemas=["public"])
    assert "Generated at:" in src
    assert "Schemas: public" in src


async def test_render_inet_column(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        await conn.execute("alter table public.todos add column ip_addr inet")
    try:
        src = await render_types_py(schemas=["public"])
        ns = _exec(src)
        hints = typing.get_type_hints(ns["Todos"])
        assert hints["ip_addr"] == (str | None)
    finally:
        async with pool.acquire() as conn:
            await conn.execute("alter table public.todos drop column if exists ip_addr")


async def test_cli_writes_parseable_file(temp_schema, tmp_path: Path, pool):
    out = tmp_path / "subdir" / "types.py"
    runner = CliRunner()

    prev = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(
            app,
            ["gen", "types", "--lang", "py", "--schema", "public", "--out", str(out)],
        )
    finally:
        os.chdir(prev)

    assert result.exit_code == 0, result.output
    assert out.is_file()
    text = out.read_text()
    ast.parse(text)
    assert "class Todos" in text
    assert "from_record" in text


async def test_cli_rejects_unsupported_lang(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["gen", "types", "--lang", "go", "--out", str(tmp_path / "types.py")],
    )
    assert result.exit_code != 0
    assert "py" in (result.output + (result.stderr or ""))


async def test_cli_reports_db_connection_error(tmp_path: Path):
    runner = CliRunner()
    with patch("supython.gen.types_py.get_settings") as mock_settings:
        mock_settings.return_value.database_url = "postgresql://nope@localhost:99999/nope"
        result = runner.invoke(
            app,
            ["gen", "types", "--lang", "py", "--out", str(tmp_path / "types.py")],
        )
    assert result.exit_code != 0
    assert "could not connect" in result.output


# ---------------------------------------------------------------------------
# TypeScript integration tests
# ---------------------------------------------------------------------------


async def test_render_ts_public_schema(temp_schema):
    src = await render_types_ts(schemas=["public"])

    assert "export interface Database {" in src
    assert "public" in src
    assert "Tables:" in src
    assert "todos:" in src
    assert "Row:" in src
    assert "Insert:" in src
    assert "Update:" in src
    assert "id: string;" in src
    assert "title: string;" in src
    assert "done: boolean;" in src


async def test_cli_writes_ts_file(temp_schema, tmp_path: Path, pool):
    out = tmp_path / "subdir" / "types.ts"
    runner = CliRunner()

    prev = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(
            app,
            ["gen", "types", "--lang", "ts", "--schema", "public", "--out", str(out)],
        )
    finally:
        os.chdir(prev)

    assert result.exit_code == 0, result.output
    assert out.is_file()
    text = out.read_text()
    assert "export interface Database {" in text
    assert "todos:" in text


async def test_cli_default_out_for_ts(temp_schema, tmp_path: Path, pool):
    runner = CliRunner()

    prev = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(
            app,
            ["gen", "types", "--lang", "ts", "--schema", "public"],
        )
    finally:
        os.chdir(prev)

    assert result.exit_code == 0, result.output
    out = tmp_path / "types.ts"
    assert out.is_file()
    text = out.read_text()
    assert "export interface Database {" in text
