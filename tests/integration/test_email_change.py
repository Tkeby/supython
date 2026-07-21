"""Email change with dual confirmation: PUT /user → both inboxes confirm."""

import json

import asyncpg
import httpx

OLD_EMAIL = "old-addr@example.com"
NEW_EMAIL = "new-addr@example.com"
PASSWORD = "password123"


async def _signup(client: httpx.AsyncClient, email: str = OLD_EMAIL) -> dict:
    r = await client.post(
        "/auth/v1/signup", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 201
    return r.json()


async def _request_change(
    client: httpx.AsyncClient, access: str, new_email: str = NEW_EMAIL
) -> httpx.Response:
    return await client.put(
        "/auth/v1/user",
        json={"email": new_email},
        headers={"Authorization": f"Bearer {access}"},
    )


async def _change_tokens(pool: asyncpg.Pool) -> dict[str, str]:
    """Return {recipient_email: raw_token} for the two change emails."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "select payload from jobs.jobs where name = 'send_auth_email' "
            "order by created_at desc limit 2"
        )
    out: dict[str, str] = {}
    for row in rows:
        p = row["payload"]
        payload = p if isinstance(p, dict) else json.loads(p)
        out[payload["to"][0]] = payload["text"].split("?token=")[-1].strip()
    return out


async def _verify(client: httpx.AsyncClient, token: str) -> httpx.Response:
    return await client.post(f"/auth/v1/email_change/verify?token={token}")


async def test_full_dual_confirmation_flow(client, pool):
    tokens = await _signup(client)
    r = await _request_change(client, tokens["access_token"])
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["new_email"] == NEW_EMAIL
    assert body["email_change_sent_at"]

    sides = await _change_tokens(pool)
    assert set(sides) == {OLD_EMAIL, NEW_EMAIL}

    # First side alone doesn't apply the change.
    r = await _verify(client, sides[OLD_EMAIL])
    assert r.status_code == 202
    assert r.json()["status"] == "pending_other_confirmation"
    async with pool.acquire() as conn:
        assert await conn.fetchval(
            "select 1 from auth.users where email = $1", OLD_EMAIL
        )

    # Second side completes it and issues a session for the updated account.
    r = await _verify(client, sides[NEW_EMAIL])
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == NEW_EMAIL
    assert body["access_token"]

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select email, email_change, email_change_confirm_status, email_confirmed_at
            from auth.users where email = $1
            """,
            NEW_EMAIL,
        )
    assert row is not None
    assert row["email_change"] is None
    assert row["email_change_confirm_status"] == 0
    assert row["email_confirmed_at"] is not None

    # Audit trail: requested + completed.
    async with pool.acquire() as conn:
        events = {
            r["event"]
            for r in await conn.fetch(
                "select event from auth.audit_log where event like 'email_change%'"
            )
        }
    assert events == {"email_change_requested", "email_change_completed"}


async def test_order_does_not_matter(client, pool):
    tokens = await _signup(client)
    await _request_change(client, tokens["access_token"])
    sides = await _change_tokens(pool)

    assert (await _verify(client, sides[NEW_EMAIL])).status_code == 202
    r = await _verify(client, sides[OLD_EMAIL])
    assert r.status_code == 200
    assert r.json()["user"]["email"] == NEW_EMAIL


async def test_change_tokens_are_single_use(client, pool):
    tokens = await _signup(client)
    await _request_change(client, tokens["access_token"])
    sides = await _change_tokens(pool)

    assert (await _verify(client, sides[OLD_EMAIL])).status_code == 202
    r = await _verify(client, sides[OLD_EMAIL])
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_token"


async def test_change_to_taken_email_is_409(client, pool):
    await _signup(client, NEW_EMAIL)
    tokens = await _signup(client, OLD_EMAIL)
    r = await _request_change(client, tokens["access_token"])
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "email_taken"


async def test_change_to_same_email_is_400(client):
    tokens = await _signup(client)
    r = await _request_change(client, tokens["access_token"], OLD_EMAIL)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "email_change_invalid"


async def test_re_request_supersedes_old_tokens(client, pool):
    tokens = await _signup(client)
    await _request_change(client, tokens["access_token"])
    old_sides = await _change_tokens(pool)

    r = await _request_change(client, tokens["access_token"], "third@example.com")
    assert r.status_code == 200

    # Tokens from the first request are gone.
    r = await _verify(client, old_sides[OLD_EMAIL])
    assert r.status_code == 400


async def test_requires_bearer(client):
    r = await client.put("/auth/v1/user", json={"email": NEW_EMAIL})
    assert r.status_code == 401


async def test_garbage_token_is_400(client):
    r = await _verify(client, "not-a-token")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_token"
