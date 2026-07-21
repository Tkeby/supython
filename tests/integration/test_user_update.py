"""PUT /auth/v1/user — authenticated password change."""

import httpx

EMAIL = "changepw@example.com"
OLD = "oldpassword123"
NEW = "newpassword456"


async def _signup(client: httpx.AsyncClient, email: str = EMAIL) -> dict:
    r = await client.post(
        "/auth/v1/signup", json={"email": email, "password": OLD}
    )
    assert r.status_code == 201
    return r.json()


async def _put_user(
    client: httpx.AsyncClient, access: str, body: dict
) -> httpx.Response:
    return await client.put(
        "/auth/v1/user",
        json=body,
        headers={"Authorization": f"Bearer {access}"},
    )


async def test_password_change_happy_path(client):
    tokens = await _signup(client)
    r = await _put_user(
        client,
        tokens["access_token"],
        {"password": NEW, "current_password": OLD},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"] != tokens["refresh_token"]

    # New password works, old one doesn't.
    r = await client.post("/auth/v1/token", json={"email": EMAIL, "password": NEW})
    assert r.status_code == 200
    r = await client.post("/auth/v1/token", json={"email": EMAIL, "password": OLD})
    assert r.status_code == 401


async def test_password_change_revokes_other_sessions(client):
    s1 = await _signup(client)
    r = await client.post("/auth/v1/token", json={"email": EMAIL, "password": OLD})
    s2 = r.json()

    r = await _put_user(
        client, s1["access_token"], {"password": NEW, "current_password": OLD}
    )
    assert r.status_code == 200
    fresh = r.json()["refresh_token"]

    # Both pre-change sessions are dead; only the returned pair survives.
    for dead in (s1["refresh_token"], s2["refresh_token"]):
        rr = await client.post("/auth/v1/refresh", json={"refresh_token": dead})
        assert rr.status_code == 401
    rr = await client.post("/auth/v1/refresh", json={"refresh_token": fresh})
    assert rr.status_code == 200


async def test_wrong_current_password_is_401(client):
    tokens = await _signup(client)
    r = await _put_user(
        client,
        tokens["access_token"],
        {"password": NEW, "current_password": "not-the-password"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invalid_credentials"


async def test_missing_current_password_is_401(client):
    tokens = await _signup(client)
    r = await _put_user(client, tokens["access_token"], {"password": NEW})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invalid_credentials"


async def test_passwordless_user_can_set_first_password(client, pool):
    """An OAuth-only / invite account (no password) sets one with just a bearer."""
    from supython import tokens as tokens_mod

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            insert into auth.users (email, activated_at, email_confirmed_at)
            values ('pwless@example.com', now(), now())
            returning id, email
            """
        )
    access, _ttl = tokens_mod.issue_access_token(row["id"], row["email"])

    r = await _put_user(client, access, {"password": NEW})
    assert r.status_code == 200

    r = await client.post(
        "/auth/v1/token", json={"email": "pwless@example.com", "password": NEW}
    )
    assert r.status_code == 200


async def test_requires_bearer(client):
    r = await client.put("/auth/v1/user", json={"password": NEW})
    assert r.status_code == 401


async def test_audit_row_written(client, pool):
    tokens = await _signup(client)
    await _put_user(
        client, tokens["access_token"], {"password": NEW, "current_password": OLD}
    )
    async with pool.acquire() as conn:
        payload = await conn.fetchval(
            "select payload from auth.audit_log where event = 'password_change'"
        )
    assert payload is not None
    assert "user_update" in str(payload)
