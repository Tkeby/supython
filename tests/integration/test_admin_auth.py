"""Integration tests for the admin auth flow."""

import asyncpg
import pytest_asyncio

from supython import passwords
from supython.admin import session as admin_session


@pytest_asyncio.fixture
async def admin_user(pool: asyncpg.Pool):
    """Create one admin user; clean up after test."""
    email = "admin@example.com"
    password = "correct horse battery staple"
    pw_hash = passwords.hash_password(password)
    async with pool.acquire() as conn:
        await conn.execute("delete from admin.admin_sessions")
        await conn.execute("delete from admin.admin_users")
        admin_id = await conn.fetchval(
            """
            insert into admin.admin_users (email, password_hash, is_root)
            values ($1, $2, true)
            returning id
            """,
            email,
            pw_hash,
        )
    yield {"id": admin_id, "email": email, "password": password}
    async with pool.acquire() as conn:
        await conn.execute("delete from admin.admin_sessions")
        await conn.execute("delete from admin.admin_users")


async def test_login_sets_session_cookie(client, admin_user):
    resp = await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == admin_user["email"]
    assert body["admin_id"] == str(admin_user["id"])
    assert "expires_at" in body

    cookie = resp.cookies.get(admin_session.SESSION_COOKIE)
    assert cookie is not None and len(cookie) > 0


async def test_login_rejects_bad_password(client, admin_user):
    resp = await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"


async def test_session_endpoint_requires_cookie(client):
    resp = await client.get("/admin/api/v1/auth/session")
    assert resp.status_code == 401


async def test_session_endpoint_returns_session_after_login(client, admin_user):
    login = await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert login.status_code == 200

    me = await client.get("/admin/api/v1/auth/session")
    assert me.status_code == 200
    body = me.json()
    assert body["admin_id"] == str(admin_user["id"])
    # expires_at must come from admin_sessions, so it is in the future.
    assert body["expires_at"] > login.json()["expires_at"][:10]  # same date prefix or later


async def test_logout_clears_session(client, admin_user):
    await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    out = await client.post("/admin/api/v1/auth/logout")
    assert out.status_code == 204

    # The /session call must now 401.
    me = await client.get("/admin/api/v1/auth/session")
    assert me.status_code == 401


async def test_admin_status_requires_session(client):
    resp = await client.get("/admin/api/v1/system/status")
    assert resp.status_code == 401


async def test_admin_status_returns_after_login(client, admin_user):
    await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    resp = await client.get("/admin/api/v1/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "pool_size" in body
    assert "jwks_kid" in body
    assert "broker" in body
    assert "jobs" in body
