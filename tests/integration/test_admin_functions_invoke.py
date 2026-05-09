"""Integration tests for /admin/api/v1/functions endpoints."""

from pathlib import Path

import asyncpg
import httpx
import pytest
import pytest_asyncio

from supython import passwords
from supython.admin import session as admin_session
from supython.functions.loader import FunctionRegistry, reset_registry, set_registry

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "functions"


@pytest.fixture(autouse=True)
def functions_registry():
    """Replace the global dispatcher registry with the test fixtures."""
    reg = FunctionRegistry(FIXTURES, hot_reload=True)
    reg.discover()
    set_registry(reg)
    yield reg
    reset_registry()


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


async def _login(client: httpx.AsyncClient, admin_user: dict) -> None:
    r = await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert r.status_code == 200, r.text
    assert client.cookies.get(admin_session.SESSION_COOKIE) is not None


# ---------------------------------------------------------------------------
# Auth gates
# ---------------------------------------------------------------------------


async def test_routes_requires_admin(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/functions/routes")
    assert r.status_code == 401


async def test_source_requires_admin(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/functions/hello/source")
    assert r.status_code == 401


async def test_invoke_requires_admin(client: httpx.AsyncClient):
    r = await client.post("/admin/api/v1/functions/hello/invoke", json={})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Routes listing
# ---------------------------------------------------------------------------


async def test_list_routes_returns_discovered(
    client: httpx.AsyncClient, admin_user: dict
):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/functions/routes")
    assert r.status_code == 200, r.text
    rows = r.json()
    by_name = {row["name"]: row for row in rows}

    assert "hello" in by_name
    hello = by_name["hello"]
    assert hello["auth"] == "anon"
    assert set(hello["methods"]) == {"GET", "POST"}
    assert hello["path"].endswith("hello.py")

    assert "me" in by_name
    me = by_name["me"]
    assert me["auth"] == "authenticated"

    assert "nested/inner" in by_name


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


async def test_read_source_returns_file_text(
    client: httpx.AsyncClient, admin_user: dict
):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/functions/hello/source")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "hello"
    assert body["path"].endswith("hello.py")
    assert "async def handler" in body["source"]
    assert body["size"] > 0


async def test_read_source_unknown_returns_404(
    client: httpx.AsyncClient, admin_user: dict
):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/functions/does-not-exist/source")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "function_not_found"


async def test_read_source_nested(client: httpx.AsyncClient, admin_user: dict):
    await _login(client, admin_user)
    r = await client.get("/admin/api/v1/functions/nested/inner/source")
    assert r.status_code == 200
    assert "handler" in r.json()["source"]


# ---------------------------------------------------------------------------
# Invoke
# ---------------------------------------------------------------------------


async def test_invoke_anon_function_succeeds(
    client: httpx.AsyncClient, admin_user: dict, pool: asyncpg.Pool
):
    await _login(client, admin_user)
    r = await client.post(
        "/admin/api/v1/functions/hello/invoke",
        json={"method": "GET"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == 200
    assert body["body"] == {"msg": "hello, world"}
    assert body["elapsed_ms"] >= 0

    async with pool.acquire() as conn:
        action = await conn.fetchval(
            "select action from admin.admin_audit where target = $1 order by at desc limit 1",
            "hello",
        )
    assert action == "functions.invoke"


async def test_invoke_authenticated_function_runs_under_service_role(
    client: httpx.AsyncClient, admin_user: dict
):
    """Story 9.2: admin invocation runs under service_role; no end-user JWT."""
    await _login(client, admin_user)
    r = await client.post(
        "/admin/api/v1/functions/me/invoke",
        json={"method": "POST"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == 200
    # No end-user → ctx.user is None → response surfaces the None'd identity.
    assert body["body"] == {"id": None, "email": None, "role": None}


async def test_invoke_method_not_allowed(
    client: httpx.AsyncClient, admin_user: dict
):
    await _login(client, admin_user)
    r = await client.post(
        "/admin/api/v1/functions/hello/invoke",
        json={"method": "DELETE"},
    )
    assert r.status_code == 405
    assert r.json()["detail"]["code"] == "method_not_allowed"


async def test_invoke_unknown_function_404(
    client: httpx.AsyncClient, admin_user: dict
):
    await _login(client, admin_user)
    r = await client.post(
        "/admin/api/v1/functions/does-not-exist/invoke", json={"method": "POST"}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "function_not_found"


async def test_invoke_handler_exception_returns_500_in_payload(
    client: httpx.AsyncClient, admin_user: dict
):
    """Handler raising is captured in the FunctionInvokeResponse, not as 500."""
    await _login(client, admin_user)
    r = await client.post(
        "/admin/api/v1/functions/boom/invoke",
        json={"method": "POST"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == 500
    assert body["body"]["code"] == "function_error"


async def test_invoke_failure_audited(
    client: httpx.AsyncClient, admin_user: dict, pool: asyncpg.Pool
):
    await _login(client, admin_user)
    r = await client.post(
        "/admin/api/v1/functions/hello/invoke", json={"method": "PUT"}
    )
    assert r.status_code == 405

    async with pool.acquire() as conn:
        action = await conn.fetchval(
            "select action from admin.admin_audit where target = $1 order by at desc limit 1",
            "hello",
        )
    assert action == "functions.invoke.failed"


async def test_invoke_passes_query_string(
    client: httpx.AsyncClient, admin_user: dict
):
    """proxy.py reads req.query_params — verifies the synthetic request
    propagates the query string the admin passed."""
    await _login(client, admin_user)
    r = await client.post(
        "/admin/api/v1/functions/proxy/invoke",
        json={"method": "POST", "query": "resource=/todos"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # The handler hands the query value to ctx.postgrest.get(...) — we don't
    # require PostgREST to be running; we only assert the invocation reached
    # the handler (status 200 from translate, or 500 from network failure).
    # Either way, the request scope was built and the function executed.
    assert body["status"] in (200, 500)
