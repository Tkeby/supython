"""Scoped signout: /auth/v1/logout with scope local / global / others."""

import httpx


async def _signup(client: httpx.AsyncClient, email: str) -> dict:
    r = await client.post(
        "/auth/v1/signup", json={"email": email, "password": "password123"}
    )
    assert r.status_code == 201
    return r.json()


async def _login(client: httpx.AsyncClient, email: str) -> dict:
    r = await client.post(
        "/auth/v1/token", json={"email": email, "password": "password123"}
    )
    assert r.status_code == 200
    return r.json()


async def _refresh(client: httpx.AsyncClient, token: str) -> httpx.Response:
    return await client.post("/auth/v1/refresh", json={"refresh_token": token})


async def test_local_logout_revokes_token(client):
    tokens = await _signup(client, "so-local@example.com")
    r = await client.post(
        "/auth/v1/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert r.status_code == 204
    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


async def test_local_logout_with_stale_token_kills_descendants(client):
    """Logging out with an already-rotated token must kill its successor too."""
    tokens = await _signup(client, "so-chain@example.com")
    rt0 = tokens["refresh_token"]
    rt1 = (await _refresh(client, rt0)).json()["refresh_token"]

    r = await client.post("/auth/v1/logout", json={"refresh_token": rt0})
    assert r.status_code == 204
    assert (await _refresh(client, rt1)).status_code == 401


async def test_global_logout_via_bearer_revokes_all_sessions(client):
    s1 = await _signup(client, "so-global@example.com")
    s2 = await _login(client, "so-global@example.com")

    r = await client.post(
        "/auth/v1/logout",
        json={"scope": "global"},
        headers={"Authorization": f"Bearer {s1['access_token']}"},
    )
    assert r.status_code == 204
    assert (await _refresh(client, s1["refresh_token"])).status_code == 401
    assert (await _refresh(client, s2["refresh_token"])).status_code == 401


async def test_others_logout_keeps_presented_session(client):
    s1 = await _signup(client, "so-others@example.com")
    s2 = await _login(client, "so-others@example.com")

    r = await client.post(
        "/auth/v1/logout",
        json={"refresh_token": s1["refresh_token"], "scope": "others"},
    )
    assert r.status_code == 204
    assert (await _refresh(client, s2["refresh_token"])).status_code == 401
    assert (await _refresh(client, s1["refresh_token"])).status_code == 200


async def test_logout_unknown_token_is_silent_204(client):
    r = await client.post(
        "/auth/v1/logout", json={"refresh_token": "no-such-token"}
    )
    assert r.status_code == 204


async def test_local_logout_without_token_is_400(client):
    r = await client.post("/auth/v1/logout", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_request"


async def test_global_logout_without_any_credential_is_401(client):
    r = await client.post("/auth/v1/logout", json={"scope": "global"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "missing_credentials"


async def test_global_logout_writes_audit_row(client, pool):
    s1 = await _signup(client, "so-audit@example.com")
    await client.post(
        "/auth/v1/logout",
        json={"scope": "global"},
        headers={"Authorization": f"Bearer {s1['access_token']}"},
    )
    async with pool.acquire() as conn:
        payload = await conn.fetchval(
            "select payload from auth.audit_log where event = 'sign_out'"
        )
    assert payload is not None
    assert "global" in str(payload)
