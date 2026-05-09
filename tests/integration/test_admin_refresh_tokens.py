"""Integration tests for /admin/api/v1/auth/refresh-tokens endpoints."""

import asyncpg
import pytest_asyncio

from supython import passwords
from supython.admin import session as admin_session


@pytest_asyncio.fixture
async def admin_user(pool: asyncpg.Pool):
    email = "ops@example.com"
    password = "correct horse battery staple"
    pw_hash = passwords.hash_password(password)
    async with pool.acquire() as conn:
        await conn.execute("delete from admin.admin_sessions")
        await conn.execute("delete from admin.admin_audit")
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
        await conn.execute("delete from admin.admin_audit")
        await conn.execute("delete from admin.admin_users")


@pytest_asyncio.fixture
async def auth_users(pool: asyncpg.Pool):
    """Create two users, each with a refresh token."""
    async with pool.acquire() as conn:
        u1 = await conn.fetchval(
            "insert into auth.users (email, encrypted_password) values ($1, $2) returning id",
            "alice@example.com",
            "x",
        )
        t1 = await conn.fetchval(
            "insert into auth.refresh_tokens (user_id, token) values ($1, $2) returning id",
            u1,
            "tok-alice-001",
        )
        u2 = await conn.fetchval(
            "insert into auth.users (email, encrypted_password) values ($1, $2) returning id",
            "bob@example.com",
            "x",
        )
        t2 = await conn.fetchval(
            "insert into auth.refresh_tokens (user_id, token) values ($1, $2) returning id",
            u2,
            "tok-bob-001",
        )
    return {
        "alice": {"id": u1, "token_id": t1},
        "bob": {"id": u2, "token_id": t2},
    }


async def _login(client, admin_user) -> None:
    r = await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert r.status_code == 200, r.text
    assert client.cookies.get(admin_session.SESSION_COOKIE) is not None


async def test_list_refresh_tokens_requires_admin(client):
    r = await client.get("/admin/api/v1/auth/refresh-tokens")
    assert r.status_code == 401


async def test_list_refresh_tokens_returns_all(client, admin_user, auth_users):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/auth/refresh-tokens")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert len(body["rows"]) == 2


async def test_list_refresh_tokens_filter_by_user(client, admin_user, auth_users):
    await _login(client, admin_user)
    alice_id = str(auth_users["alice"]["id"])
    r = await client.get(f"/admin/api/v1/auth/refresh-tokens?user_id={alice_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["rows"][0]["user_id"] == alice_id


async def test_list_refresh_tokens_pagination(client, admin_user, auth_users):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/auth/refresh-tokens?limit=1&offset=0")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert len(body["rows"]) == 1


async def test_revoke_single_token(client, admin_user, auth_users, pool):
    await _login(client, admin_user)
    token_id = auth_users["alice"]["token_id"]
    r = await client.delete(f"/admin/api/v1/auth/refresh-tokens/{token_id}")
    assert r.status_code == 204

    async with pool.acquire() as conn:
        revoked = await conn.fetchval(
            "select revoked from auth.refresh_tokens where id = $1",
            token_id,
        )
    assert revoked is True


async def test_revoke_token_writes_dual_audit(client, admin_user, auth_users, pool):
    await _login(client, admin_user)
    token_id = auth_users["alice"]["token_id"]
    r = await client.delete(f"/admin/api/v1/auth/refresh-tokens/{token_id}")
    assert r.status_code == 204

    async with pool.acquire() as conn:
        admin_action = await conn.fetchval(
            "select action from admin.admin_audit where target = $1 order by at desc limit 1",
            str(token_id),
        )
        user_event = await conn.fetchval(
            "select event from auth.audit_log where user_id = $1 order by created_at desc limit 1",
            auth_users["alice"]["id"],
        )
    assert admin_action == "auth.refresh_token.revoke"
    assert user_event == "refresh_token.revoked"


async def test_revoke_token_404(client, admin_user):
    await _login(client, admin_user)
    r = await client.delete("/admin/api/v1/auth/refresh-tokens/99999")
    assert r.status_code == 404
