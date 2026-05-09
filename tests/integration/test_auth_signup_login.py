"""End-to-end tests for signup, password login, refresh, logout, and /user."""

import httpx


async def _signup(client: httpx.AsyncClient, email: str, password: str) -> dict:
    r = await client.post(
        "/auth/v1/signup",
        json={"email": email, "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _login(client: httpx.AsyncClient, email: str, password: str) -> dict:
    r = await client.post(
        "/auth/v1/token",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_signup_returns_token_pair(client):
    body = await _signup(client, "alice@example.com", "password123")

    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "alice@example.com"


async def test_login_after_signup(client):
    await _signup(client, "bob@example.com", "s3cr3tPass")
    body = await _login(client, "bob@example.com", "s3cr3tPass")

    assert body["access_token"]
    assert body["user"]["email"] == "bob@example.com"


async def test_me_returns_user(client):
    tokens = await _signup(client, "carol@example.com", "password123")
    r = await client.get(
        "/auth/v1/user",
        headers={"authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "carol@example.com"


async def test_me_requires_bearer_token(client):
    r = await client.get("/auth/v1/user")
    assert r.status_code == 401


async def test_me_rejects_invalid_token(client):
    r = await client.get(
        "/auth/v1/user",
        headers={"authorization": "Bearer not.a.real.token"},
    )
    assert r.status_code == 401


async def test_duplicate_email_returns_409(client):
    await _signup(client, "dave@example.com", "password123")
    r = await client.post(
        "/auth/v1/signup",
        json={"email": "dave@example.com", "password": "password123"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "email_taken"


async def test_wrong_password_returns_401(client):
    await _signup(client, "eve@example.com", "correcthorse")
    r = await client.post(
        "/auth/v1/token",
        json={"email": "eve@example.com", "password": "wrongpassword"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invalid_credentials"


async def test_refresh_returns_new_token_pair(client):
    tokens = await _signup(client, "frank@example.com", "password123")
    r = await client.post(
        "/auth/v1/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] != tokens["access_token"]
    assert body["refresh_token"] != tokens["refresh_token"]


async def test_logout_invalidates_refresh_token(client):
    tokens = await _signup(client, "grace@example.com", "password123")
    r = await client.post(
        "/auth/v1/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert r.status_code == 204

    # Using the revoked token should now fail
    r2 = await client.post(
        "/auth/v1/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert r2.status_code == 401
