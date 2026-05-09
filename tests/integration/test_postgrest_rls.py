"""PostgREST RLS smoke test.

Verifies that a JWT issued by supython is accepted by PostgREST and that
row-level security correctly isolates each user's todos.

Requires `supython up` to have been run (PostgREST on :54321, Postgres on :54322).
Tests skip automatically when PostgREST is not reachable.

NOTE: the test client creates users in the test DB (port 54323), but
PostgREST connects to the dev DB (port 54322). Tests that need PostgREST
to accept writes referencing auth.users must seed the user into the dev
DB via the ``dev_pool`` fixture.
"""

from uuid import UUID

import asyncpg
import httpx
import pytest
import pytest_asyncio

from supython.settings import get_settings

_DEV_DATABASE_URL = "postgresql://supython:supython@localhost:54322/supython"


async def _is_postgrest_up(url: str) -> bool:
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(url, timeout=2.0)
            return r.status_code < 500
    except Exception:
        return False


@pytest_asyncio.fixture(scope="session")
async def postgrest_url() -> str:
    return get_settings().postgrest_url


@pytest_asyncio.fixture(autouse=True)
async def require_postgrest(postgrest_url: str) -> None:
    if not await _is_postgrest_up(postgrest_url):
        pytest.skip("PostgREST not reachable — run `supython up` first")


@pytest_asyncio.fixture(scope="session")
async def dev_pool():
    """Pool connected to the dev DB that PostgREST uses (port 54322)."""
    try:
        p = await asyncpg.create_pool(_DEV_DATABASE_URL, min_size=1, max_size=2)
    except Exception:
        pytest.skip("Dev DB not reachable — run `supython up` first")
        return
    yield p
    await p.close()


async def _signup_and_seed(
    client: httpx.AsyncClient, dev_pool: asyncpg.Pool, email: str
) -> str:
    """Sign up via the test app and seed the user into the dev DB for PostgREST."""
    r = await client.post(
        "/auth/v1/signup",
        json={"email": email, "password": "password123"},
    )
    assert r.status_code == 201
    body = r.json()
    user_id = UUID(body["user"]["id"])
    async with dev_pool.acquire() as conn:
        await conn.execute(
            """
            insert into auth.users (id, email, email_confirmed_at)
            values ($1, $2, now())
            on conflict (id) do nothing
            """,
            user_id,
            email,
        )
    return body["access_token"]


async def _cleanup_dev_users(dev_pool: asyncpg.Pool, *emails: str) -> None:
    async with dev_pool.acquire() as conn:
        await conn.execute(
            "delete from auth.users where email = any($1::text[])",
            list(emails),
        )


async def test_authenticated_user_can_create_and_read_todos(client, postgrest_url, dev_pool):
    email = "rls_alice@example.com"
    token = await _signup_and_seed(client, dev_pool, email)

    try:
        async with httpx.AsyncClient(base_url=postgrest_url) as pg:
            r = await pg.post(
                "/todos",
                json={"title": "buy milk"},
                headers={
                    "authorization": f"Bearer {token}",
                    "prefer": "return=representation",
                    "content-type": "application/json",
                },
            )
            assert r.status_code in (200, 201), r.text

            r2 = await pg.get(
                "/todos",
                headers={"authorization": f"Bearer {token}"},
            )
            assert r2.status_code == 200
            todos = r2.json()
            assert any(t["title"] == "buy milk" for t in todos)
    finally:
        await _cleanup_dev_users(dev_pool, email)


async def test_rls_isolates_users(client, postgrest_url, dev_pool):
    """Alice's todos must not be visible to Bob."""
    alice_email = "rls_alice2@example.com"
    bob_email = "rls_bob2@example.com"
    alice_token = await _signup_and_seed(client, dev_pool, alice_email)
    bob_token = await _signup_and_seed(client, dev_pool, bob_email)

    try:
        async with httpx.AsyncClient(base_url=postgrest_url) as pg:
            await pg.post(
                "/todos",
                json={"title": "alice's secret"},
                headers={
                    "authorization": f"Bearer {alice_token}",
                    "prefer": "return=representation",
                    "content-type": "application/json",
                },
            )

            r = await pg.get(
                "/todos",
                headers={"authorization": f"Bearer {bob_token}"},
            )
            assert r.status_code == 200
            assert all(t["title"] != "alice's secret" for t in r.json())
    finally:
        await _cleanup_dev_users(dev_pool, alice_email, bob_email)


async def test_unauthenticated_request_cannot_read_todos(postgrest_url):
    """Requests without a JWT must not expose any todo rows."""
    async with httpx.AsyncClient(base_url=postgrest_url) as pg:
        r = await pg.get("/todos")
        # anon role has no SELECT grant → 401 / 403 or an empty list
        if r.status_code == 200:
            assert r.json() == [], "Unauthenticated request must not return any todos"
        else:
            assert r.status_code in (401, 403)
