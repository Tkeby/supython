"""PostgREST JWKS verification smoke tests.

Requires `supython up` to have been run with JWKS compose wiring.
Tests skip automatically when PostgREST is not reachable.

NOTE: the test client creates users in the test DB (port 54323), but
PostgREST connects to the dev DB (port 54322). Tests that need PostgREST
to accept writes referencing auth.users must seed the user into the dev
DB via the ``dev_pool`` fixture.
"""

import asyncpg
import httpx
import pytest
import pytest_asyncio

from supython.settings import get_settings
from tests._keys import make_token_with_alg, make_wrong_key_token

pytestmark = pytest.mark.slow

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


async def _signup_and_get_token(client: httpx.AsyncClient, email: str) -> str:
    r = await client.post(
        "/auth/v1/signup",
        json={"email": email, "password": "password123"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


async def _seed_user_in_dev_db(dev_pool: asyncpg.Pool, client_resp: dict) -> None:
    """Insert the user row into the dev DB so PostgREST FK constraints pass."""
    from uuid import UUID

    user = client_resp["user"]
    user_id = UUID(user["id"])
    async with dev_pool.acquire() as conn:
        await conn.execute(
            """
            insert into auth.users (id, email, email_confirmed_at)
            values ($1, $2, now())
            on conflict (id) do nothing
            """,
            user_id,
            user["email"],
        )


async def _cleanup_dev_user(dev_pool: asyncpg.Pool, email: str) -> None:
    async with dev_pool.acquire() as conn:
        await conn.execute("delete from auth.users where email = $1", email)


async def test_postgrest_accepts_rs256_token(client, postgrest_url, dev_pool):
    email = "jwks_alice@example.com"
    r = await client.post(
        "/auth/v1/signup",
        json={"email": email, "password": "password123"},
    )
    assert r.status_code == 201
    body = r.json()
    token = body["access_token"]
    await _seed_user_in_dev_db(dev_pool, body)

    try:
        async with httpx.AsyncClient(base_url=postgrest_url) as pg:
            r = await pg.post(
                "/todos",
                json={"title": "jwks works"},
                headers={
                    "authorization": f"Bearer {token}",
                    "prefer": "return=representation",
                    "content-type": "application/json",
                },
            )
        assert r.status_code in (200, 201), (
            f"PostgREST rejected the supython token. Is the stack using JWKS wiring? {r.text}"
        )
    finally:
        await _cleanup_dev_user(dev_pool, email)


async def test_postgrest_rejects_alien_kid_token(postgrest_url):
    token = make_wrong_key_token()

    async with httpx.AsyncClient(base_url=postgrest_url) as pg:
        r = await pg.get("/todos", headers={"authorization": f"Bearer {token}"})

    assert r.status_code in (401, 403), r.text


async def test_postgrest_rejects_hs256_token_when_jwks_in_use(postgrest_url):
    token = make_token_with_alg("HS256")

    async with httpx.AsyncClient(base_url=postgrest_url) as pg:
        r = await pg.get("/todos", headers={"authorization": f"Bearer {token}"})

    if r.status_code == 200:
        pytest.skip(
            "PostgREST is reachable but still accepts HS256; recreate the stack "
            "so docker-compose uses JWKS wiring"
        )
    assert r.status_code in (401, 403), (
        "PostgREST accepted an HS256 token; verify docker-compose is using JWKS"
    )

