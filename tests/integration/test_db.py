"""Tests for the ``db`` module helpers."""

import json

import asyncpg
import pytest

from supython import db


@pytest.mark.usefixtures("pool")
async def test_as_service_role_without_claims_leaves_guc_empty():
    async with db.as_service_role() as conn:
        val = await conn.fetchval(
            "select current_setting('request.jwt.claims', true)"
        )
        assert val is None or val == ""


@pytest.mark.usefixtures("pool")
async def test_as_service_role_with_claims_sets_guc():
    claims = {"sub": "11111111-1111-1111-1111-111111111111", "role": "authenticated"}
    async with db.as_service_role(claims=claims) as conn:
        val = await conn.fetchval(
            "select current_setting('request.jwt.claims', true)"
        )
        assert json.loads(val) == claims


@pytest.mark.usefixtures("pool")
async def test_as_service_role_claims_reset_on_exit():
    claims = {"sub": "22222222-2222-2222-2222-222222222222"}
    async with db.as_service_role(claims=claims) as conn:
        pass

    async with db.acquire() as conn:
        val = await conn.fetchval(
            "select current_setting('request.jwt.claims', true)"
        )
        assert val is None or val == ""


@pytest.mark.usefixtures("pool")
async def test_as_service_role_resets_role_and_guc_on_exception():
    claims = {"sub": "33333333-3333-3333-3333-333333333333"}
    with pytest.raises(RuntimeError, match="boom"):
        async with db.as_service_role(claims=claims) as conn:
            role = await conn.fetchval("select current_user::text")
            assert role == "service_role"
            val = await conn.fetchval(
                "select current_setting('request.jwt.claims', true)"
            )
            assert json.loads(val) == claims
            raise RuntimeError("boom")

    async with db.acquire() as conn:
        role = await conn.fetchval("select current_user::text")
        session = await conn.fetchval("select session_user::text")
        assert role == session
        val = await conn.fetchval(
            "select current_setting('request.jwt.claims', true)"
        )
        assert val is None or val == ""


@pytest.mark.usefixtures("pool")
async def test_as_role_sets_role_and_guc():
    claims = {"sub": "44444444-4444-4444-4444-444444444444", "role": "authenticated"}
    async with db.as_role("authenticated", claims) as conn:
        role = await conn.fetchval("select current_user::text")
        assert role == "authenticated"
        val = await conn.fetchval(
            "select current_setting('request.jwt.claims', true)"
        )
        assert json.loads(val) == claims


@pytest.mark.usefixtures("pool")
async def test_as_role_resets_role_and_guc_on_exit():
    claims = {"sub": "55555555-5555-5555-5555-555555555555", "role": "authenticated"}
    async with db.as_role("authenticated", claims) as conn:
        pass

    async with db.acquire() as conn:
        role = await conn.fetchval("select current_user::text")
        session = await conn.fetchval("select session_user::text")
        assert role == session
        val = await conn.fetchval(
            "select current_setting('request.jwt.claims', true)"
        )
        assert val is None or val == ""


@pytest.mark.usefixtures("pool")
async def test_as_role_resets_role_and_guc_on_exception():
    claims = {"sub": "66666666-6666-6666-6666-666666666666", "role": "authenticated"}
    with pytest.raises(RuntimeError, match="boom"):
        async with db.as_role("authenticated", claims) as conn:
            role = await conn.fetchval("select current_user::text")
            assert role == "authenticated"
            val = await conn.fetchval(
                "select current_setting('request.jwt.claims', true)"
            )
            assert json.loads(val) == claims
            raise RuntimeError("boom")

    async with db.acquire() as conn:
        role = await conn.fetchval("select current_user::text")
        session = await conn.fetchval("select session_user::text")
        assert role == session
        val = await conn.fetchval(
            "select current_setting('request.jwt.claims', true)"
        )
        assert val is None or val == ""


@pytest.mark.usefixtures("pool")
async def test_connection_setup_applies_statement_timeout(monkeypatch):
    settings = type("S", (), {"db_statement_timeout_ms": 50})()
    monkeypatch.setattr(db, "get_settings", lambda: settings)

    async with db.acquire() as conn:
        try:
            await db._connection_setup(conn)
            timeout = await conn.fetchval("show statement_timeout")
            assert timeout == "50ms"
            with pytest.raises(asyncpg.exceptions.QueryCanceledError):
                await conn.fetchval("select pg_sleep(1)")
        finally:
            await conn.execute("set statement_timeout = 0")
