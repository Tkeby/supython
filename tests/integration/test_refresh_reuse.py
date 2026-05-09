"""Refresh-token reuse detection: revoked token re-use invalidates the full chain."""

import httpx


async def _signup(client: httpx.AsyncClient) -> dict:
    r = await client.post(
        "/auth/v1/signup",
        json={"email": "reuse@example.com", "password": "password123"},
    )
    assert r.status_code == 201
    return r.json()


async def _refresh(client: httpx.AsyncClient, token: str) -> httpx.Response:
    return await client.post("/auth/v1/refresh", json={"refresh_token": token})


async def test_happy_refresh_rotation(client):
    tokens = await _signup(client)
    original_rt = tokens["refresh_token"]

    r = await _refresh(client, original_rt)
    assert r.status_code == 200

    body = r.json()
    # New tokens must differ from the originals
    assert body["refresh_token"] != original_rt
    assert body["access_token"] != tokens["access_token"]

    # Original token is now revoked
    r2 = await _refresh(client, original_rt)
    assert r2.status_code == 401


async def test_reuse_of_revoked_token_revokes_descendants(client, pool):
    tokens = await _signup(client)
    rt0 = tokens["refresh_token"]

    # Rotate once: rt0 → rt1
    r1 = await _refresh(client, rt0)
    assert r1.status_code == 200
    rt1 = r1.json()["refresh_token"]

    # Rotate again: rt1 → rt2
    r2 = await _refresh(client, rt1)
    assert r2.status_code == 200
    rt2 = r2.json()["refresh_token"]

    # Re-use rt0 (already revoked) — this is a reuse attack
    r_attack = await _refresh(client, rt0)
    assert r_attack.status_code == 401
    assert r_attack.json()["detail"]["code"] == "token_reuse_detected"

    # rt1 and rt2 (descendants) must now be revoked too
    r_rt1 = await _refresh(client, rt1)
    assert r_rt1.status_code == 401

    r_rt2 = await _refresh(client, rt2)
    assert r_rt2.status_code == 401


async def test_reuse_writes_audit_log(client, pool):
    tokens = await _signup(client)
    rt0 = tokens["refresh_token"]

    # Rotate once so rt0 becomes revoked, then re-use it
    r1 = await _refresh(client, rt0)
    assert r1.status_code == 200

    await _refresh(client, rt0)  # the reuse

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select event from auth.audit_log where event = 'refresh_token_reuse'"
        )

    assert row is not None, "Expected an audit_log entry for token reuse"
    assert row["event"] == "refresh_token_reuse"
