"""raw_user_meta_data / raw_app_meta_data wire-up."""

import httpx

EMAIL = "meta@example.com"


async def _signup(
    client: httpx.AsyncClient, email: str = EMAIL, data: dict | None = None
) -> dict:
    body: dict = {"email": email, "password": "password123"}
    if data is not None:
        body["data"] = data
    r = await client.post("/auth/v1/signup", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_signup_stores_user_metadata_and_provider(client, pool):
    tokens = await _signup(client, data={"display_name": "Meta Person"})
    assert tokens["user"]["user_metadata"] == {"display_name": "Meta Person"}
    assert tokens["user"]["app_metadata"]["provider"] == "email"

    r = await client.get(
        "/auth/v1/user",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_metadata"] == {"display_name": "Meta Person"}
    assert body["app_metadata"] == {"provider": "email", "providers": ["email"]}


async def test_put_user_merges_metadata(client):
    tokens = await _signup(client, data={"a": 1, "b": "keep"})
    r = await client.put(
        "/auth/v1/user",
        json={"data": {"a": 2, "c": True}},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 200
    meta = r.json()["user"]["user_metadata"]
    assert meta == {"a": 2, "b": "keep", "c": True}


async def test_oversized_metadata_is_422(client):
    r = await client.post(
        "/auth/v1/signup",
        json={
            "email": "big@example.com",
            "password": "password123",
            "data": {"blob": "x" * 9000},
        },
    )
    assert r.status_code == 422


async def test_put_user_password_mode_is_exclusive(client):
    tokens = await _signup(client)
    r = await client.put(
        "/auth/v1/user",
        json={
            "password": "newpassword456",
            "current_password": "password123",
            "data": {"x": 1},
        },
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_request"


async def test_put_user_empty_body_is_400(client):
    tokens = await _signup(client)
    r = await client.put(
        "/auth/v1/user",
        json={},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_request"
