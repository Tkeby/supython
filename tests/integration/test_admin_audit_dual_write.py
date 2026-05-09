"""Integration tests verifying every admin mutation appears in both
``auth.audit_log`` (user-facing) and ``admin.admin_audit`` (operator-facing).

Also covers the ``GET /admin/api/v1/auth/audit`` endpoint (listing + event filter).
"""

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
async def auth_user(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "insert into auth.users (email, encrypted_password) values ($1, $2) returning id",
            "alice@example.com",
            "x",
        )
        await conn.fetchval(
            "insert into auth.refresh_tokens (user_id, token) values ($1, $2) returning id",
            user_id,
            "tok-audit-test",
        )
    return {"id": user_id, "email": "alice@example.com"}


async def _login(client, admin_user) -> None:
    r = await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert r.status_code == 200, r.text
    assert client.cookies.get(admin_session.SESSION_COOKIE) is not None


# ── Dual-write assertions ──────────────────────────────────────────


async def test_ban_writes_both_logs(client, admin_user, auth_user, pool):
    await _login(client, admin_user)
    r = await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/ban")
    assert r.status_code == 200

    async with pool.acquire() as conn:
        admin_row = await conn.fetchrow(
            "select action, target from admin.admin_audit where target = $1 order by at desc limit 1",
            str(auth_user["id"]),
        )
        user_row = await conn.fetchrow(
            "select event, user_id from auth.audit_log where user_id = $1 order by created_at desc limit 1",
            auth_user["id"],
        )
    assert admin_row is not None
    assert admin_row["action"] == "auth.user.ban"
    assert user_row is not None
    assert user_row["event"] == "user.banned"


async def test_unban_writes_both_logs(client, admin_user, auth_user, pool):
    await _login(client, admin_user)
    await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/ban")
    r = await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/unban")
    assert r.status_code == 204

    async with pool.acquire() as conn:
        admin_action = await conn.fetchval(
            "select action from admin.admin_audit where target = $1 order by at desc limit 1",
            str(auth_user["id"]),
        )
    assert admin_action == "auth.user.unban"


async def test_force_logout_writes_both_logs(client, admin_user, auth_user, pool):
    await _login(client, admin_user)
    r = await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/force-logout")
    assert r.status_code == 200

    async with pool.acquire() as conn:
        admin_row = await conn.fetchrow(
            "select action, target from admin.admin_audit where target = $1 order by at desc limit 1",
            str(auth_user["id"]),
        )
        user_row = await conn.fetchrow(
            "select event, user_id from auth.audit_log where user_id = $1 order by created_at desc limit 1",
            auth_user["id"],
        )
    assert admin_row["action"] == "auth.user.force_logout"
    assert user_row["event"] == "user.force_logout"


# ── Audit log listing ──────────────────────────────────────────────


async def test_list_audit_requires_admin(client):
    r = await client.get("/admin/api/v1/auth/audit")
    assert r.status_code == 401


async def test_list_audit_returns_page(client, admin_user, auth_user):
    await _login(client, admin_user)
    # Perform a mutation to create an audit entry
    await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/ban")

    r = await client.get("/admin/api/v1/auth/audit")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert len(body["rows"]) >= 1


async def test_list_audit_filter_by_event(client, admin_user, auth_user):
    await _login(client, admin_user)
    await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/ban")
    await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/unban")

    r = await client.get("/admin/api/v1/auth/audit?event=user.banned")
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert len(rows) >= 1
    assert all(row["event"] == "user.banned" for row in rows)


async def test_list_audit_pagination(client, admin_user, auth_user):
    await _login(client, admin_user)
    await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/ban")
    await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/unban")

    r = await client.get("/admin/api/v1/auth/audit?limit=1&offset=0")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 2
    assert len(body["rows"]) == 1


async def test_audit_empty_when_no_events(client, admin_user):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/auth/audit")
    assert r.status_code == 200
    assert r.json()["total"] == 0
