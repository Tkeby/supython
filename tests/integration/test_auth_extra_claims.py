"""Integration tests for the claims-provider extension point.

Verifies that a provider registered via ``claims.register`` (the same
callable that ``app.claims_provider`` exposes) injects custom claims
into the access tokens minted by ``/auth/v1/signup``,
``/auth/v1/token``, and ``/auth/v1/refresh``.
"""

import pytest

from supython.auth import claims
from supython.tokens import decode_access_token


@pytest.fixture(autouse=True)
def _clean_registry():
    claims.reset()
    yield
    claims.reset()


async def test_signup_token_carries_provider_claims(client):
    @claims.register
    async def add_org(user, conn):
        return {"org_id": "org-42", "tier": "pro"}

    resp = await client.post(
        "/auth/v1/signup",
        json={"email": "alice@test.com", "password": "correct horse"},
    )
    assert resp.status_code == 201, resp.text

    decoded = decode_access_token(resp.json()["access_token"])
    assert decoded["org_id"] == "org-42"
    assert decoded["tier"] == "pro"
    assert decoded["sub"]
    assert decoded["role"] == "authenticated"


async def test_password_grant_carries_provider_claims(client):
    signup = await client.post(
        "/auth/v1/signup",
        json={"email": "bob@test.com", "password": "correct horse"},
    )
    assert signup.status_code == 201

    @claims.register
    async def add_scope(user, conn):
        return {"scope": "read write"}

    resp = await client.post(
        "/auth/v1/token",
        json={"email": "bob@test.com", "password": "correct horse"},
    )
    assert resp.status_code == 200, resp.text
    decoded = decode_access_token(resp.json()["access_token"])
    assert decoded["scope"] == "read write"


async def test_refresh_re_collects_claims(client):
    """A token re-issued via /refresh must reflect the *current* output of
    the provider, not the claims that happened to be on the original
    access token."""
    counter = {"calls": 0}

    @claims.register
    async def add_call_count(user, conn):
        counter["calls"] += 1
        return {"call_count": counter["calls"]}

    signup = await client.post(
        "/auth/v1/signup",
        json={"email": "carol@test.com", "password": "correct horse"},
    )
    assert signup.status_code == 201
    body = signup.json()
    first = decode_access_token(body["access_token"])
    assert first["call_count"] == 1

    refresh = await client.post(
        "/auth/v1/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert refresh.status_code == 200, refresh.text
    second = decode_access_token(refresh.json()["access_token"])
    assert second["call_count"] == 2


async def test_provider_cannot_overwrite_reserved_claim(client):
    @claims.register
    async def evil(user, conn):
        return {"role": "service_role", "org_id": "ok"}

    resp = await client.post(
        "/auth/v1/signup",
        json={"email": "dave@test.com", "password": "correct horse"},
    )
    assert resp.status_code == 201
    decoded = decode_access_token(resp.json()["access_token"])
    assert decoded["role"] == "authenticated"
    assert decoded["org_id"] == "ok"


async def test_provider_exception_fails_signup(client):
    """A provider that raises must abort issuance — issuing a token without
    the claim the app relies on for authz is the worst failure mode."""

    @claims.register
    async def boom(user, conn):
        raise RuntimeError("db is on fire")

    with pytest.raises(RuntimeError, match="db is on fire"):
        await client.post(
            "/auth/v1/signup",
            json={"email": "erin@test.com", "password": "correct horse"},
        )


async def test_no_providers_token_unchanged(client):
    """Sanity check: with no providers registered, the access token shape
    is exactly the standard claim set."""
    resp = await client.post(
        "/auth/v1/signup",
        json={"email": "frank@test.com", "password": "correct horse"},
    )
    assert resp.status_code == 201
    decoded = decode_access_token(resp.json()["access_token"])
    assert set(decoded.keys()) == {"sub", "email", "role", "aud", "iat", "exp", "jti"}
