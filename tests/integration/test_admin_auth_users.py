"""Integration tests for /admin/api/v1/auth/users endpoints."""

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
    """Create a regular auth.users row with a refresh token + identity."""
    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            """
            insert into auth.users (email, encrypted_password)
            values ($1, $2)
            returning id
            """,
            "alice@example.com",
            "x",
        )
        token_id = await conn.fetchval(
            """
            insert into auth.refresh_tokens (user_id, token)
            values ($1, $2)
            returning id
            """,
            user_id,
            "tok-" + str(user_id),
        )
        await conn.execute(
            """
            insert into auth.identities (user_id, provider, provider_user_id, identity_data)
            values ($1, 'email', $2, '{}'::jsonb)
            """,
            user_id,
            "alice@example.com",
        )
    return {"id": user_id, "email": "alice@example.com", "token_id": token_id}


async def _login(client, admin_user) -> None:
    r = await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert r.status_code == 200, r.text
    assert client.cookies.get(admin_session.SESSION_COOKIE) is not None


async def test_list_users_requires_admin(client):
    r = await client.get("/admin/api/v1/auth/users")
    assert r.status_code == 401


async def test_list_users_returns_page(client, admin_user, auth_user):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/auth/users")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert any(row["email"] == auth_user["email"] for row in body["rows"])


async def test_list_users_search_filters(client, admin_user, auth_user, pool):
    async with pool.acquire() as conn:
        await conn.execute(
            "insert into auth.users (email, encrypted_password) values ($1, $2)",
            "bob@example.com",
            "x",
        )
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/auth/users?search=alice")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["email"] == "alice@example.com"


async def test_list_users_filters_by_confirmed(client, admin_user, auth_user, pool):
    """`confirmed=true` returns only users with non-null email_confirmed_at."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into auth.users (email, encrypted_password, email_confirmed_at)
            values ($1, $2, now())
            """,
            "carol@example.com",
            "x",
        )
    await _login(client, admin_user)

    r_confirmed = await client.get("/admin/api/v1/auth/users?confirmed=true")
    assert r_confirmed.status_code == 200
    emails = {row["email"] for row in r_confirmed.json()["rows"]}
    assert "carol@example.com" in emails
    assert auth_user["email"] not in emails

    r_unconfirmed = await client.get("/admin/api/v1/auth/users?confirmed=false")
    assert r_unconfirmed.status_code == 200
    emails = {row["email"] for row in r_unconfirmed.json()["rows"]}
    assert auth_user["email"] in emails
    assert "carol@example.com" not in emails


async def test_list_users_filters_by_banned(client, admin_user, auth_user, pool):
    """`banned=true` returns only users with banned_until in the future."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            update auth.users
            set banned_until = now() + interval '1 day'
            where id = $1
            """,
            auth_user["id"],
        )
        await conn.execute(
            "insert into auth.users (email, encrypted_password) values ($1, $2)",
            "dave@example.com",
            "x",
        )
    await _login(client, admin_user)

    r_banned = await client.get("/admin/api/v1/auth/users?banned=true")
    assert r_banned.status_code == 200
    emails = {row["email"] for row in r_banned.json()["rows"]}
    assert auth_user["email"] in emails
    assert "dave@example.com" not in emails

    r_active = await client.get("/admin/api/v1/auth/users?banned=false")
    assert r_active.status_code == 200
    emails = {row["email"] for row in r_active.json()["rows"]}
    assert "dave@example.com" in emails
    assert auth_user["email"] not in emails


async def test_list_users_filters_compose(client, admin_user, auth_user, pool):
    """search + confirmed + banned compose with AND."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into auth.users (email, encrypted_password, email_confirmed_at)
            values ($1, $2, now())
            """,
            "alice-confirmed@example.com",
            "x",
        )
    await _login(client, admin_user)

    r = await client.get(
        "/admin/api/v1/auth/users?search=alice&confirmed=true&banned=false"
    )
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["email"] == "alice-confirmed@example.com"


async def test_get_user_detail(client, admin_user, auth_user):
    await _login(client, admin_user)
    r = await client.get(f"/admin/api/v1/auth/users/{auth_user['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == auth_user["email"]
    assert len(body["identities"]) == 1
    assert body["identities"][0]["provider"] == "email"
    assert isinstance(body["recent_audit"], list)


async def test_get_user_404(client, admin_user):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/auth/users/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


async def test_ban_user_default_24h(client, admin_user, auth_user, pool):
    await _login(client, admin_user)
    r = await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/ban")
    assert r.status_code == 200, r.text
    assert "banned_until" in r.json()

    async with pool.acquire() as conn:
        banned_until = await conn.fetchval(
            "select banned_until from auth.users where id = $1",
            auth_user["id"],
        )
        admin_action = await conn.fetchval(
            "select action from admin.admin_audit where target = $1 order by at desc limit 1",
            str(auth_user["id"]),
        )
        user_event = await conn.fetchval(
            "select event from auth.audit_log where user_id = $1 order by created_at desc limit 1",
            auth_user["id"],
        )
    assert banned_until is not None
    assert admin_action == "auth.user.ban"
    assert user_event == "user.banned"


async def test_ban_user_custom_duration(client, admin_user, auth_user, pool):
    await _login(client, admin_user)
    r = await client.post(
        f"/admin/api/v1/auth/users/{auth_user['id']}/ban",
        json={"duration_seconds": 60},
    )
    assert r.status_code == 200, r.text
    async with pool.acquire() as conn:
        banned_until = await conn.fetchval(
            "select banned_until from auth.users where id = $1",
            auth_user["id"],
        )
    assert banned_until is not None


async def test_ban_user_404(client, admin_user):
    await _login(client, admin_user)
    r = await client.post("/admin/api/v1/auth/users/00000000-0000-0000-0000-000000000000/ban")
    assert r.status_code == 404


async def test_unban_user_clears_window(client, admin_user, auth_user, pool):
    await _login(client, admin_user)
    await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/ban")
    r = await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/unban")
    assert r.status_code == 204

    async with pool.acquire() as conn:
        banned_until = await conn.fetchval(
            "select banned_until from auth.users where id = $1",
            auth_user["id"],
        )
        admin_action = await conn.fetchval(
            "select action from admin.admin_audit where target = $1 order by at desc limit 1",
            str(auth_user["id"]),
        )
    assert banned_until is None
    assert admin_action == "auth.user.unban"


async def test_force_logout_revokes_tokens(client, admin_user, auth_user, pool):
    await _login(client, admin_user)
    r = await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/force-logout")
    assert r.status_code == 200, r.text
    assert r.json()["revoked"] == 1

    async with pool.acquire() as conn:
        revoked = await conn.fetchval(
            "select revoked from auth.refresh_tokens where id = $1",
            auth_user["token_id"],
        )
        admin_action = await conn.fetchval(
            "select action from admin.admin_audit where target = $1 order by at desc limit 1",
            str(auth_user["id"]),
        )
        user_event = await conn.fetchval(
            "select event from auth.audit_log where user_id = $1 order by created_at desc limit 1",
            auth_user["id"],
        )
    assert revoked is True
    assert admin_action == "auth.user.force_logout"
    assert user_event == "user.force_logout"


async def test_force_logout_idempotent(client, admin_user, auth_user):
    await _login(client, admin_user)
    first = await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/force-logout")
    assert first.status_code == 200
    second = await client.post(f"/admin/api/v1/auth/users/{auth_user['id']}/force-logout")
    assert second.status_code == 200
    assert second.json()["revoked"] == 0
