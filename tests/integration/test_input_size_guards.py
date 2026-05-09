"""Integration smoke tests for input size guards.

These exercise the real ASGI app: the body-size middleware runs ahead of
the auth router, and the per-field caps trip on real request payloads
through the live signup pipeline. Pure middleware / pydantic unit tests
live in `tests/unit/test_input_size_guards.py`.
"""

import json

import pytest

from supython.auth.schemas import MAX_EMAIL_LEN, MAX_PASSWORD_LEN
from supython.body_size import ERR_BODY_TOO_LARGE


@pytest.mark.asyncio
async def test_signup_returns_413_for_oversized_body(client):
    big_password_payload = json.dumps(
        {"email": "x@example.com", "password": "p" * 2_000_000}
    )
    response = await client.post(
        "/auth/v1/signup",
        content=big_password_payload,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    body = response.json()
    assert body["detail"]["code"] == ERR_BODY_TOO_LARGE
    assert response.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.asyncio
async def test_signup_returns_422_for_oversized_password_field(client):
    response = await client.post(
        "/auth/v1/signup",
        json={
            "email": "alice@example.com",
            "password": "x" * (MAX_PASSWORD_LEN + 1),
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_signup_returns_422_for_oversized_email_field(client):
    response = await client.post(
        "/auth/v1/signup",
        json={
            "email": "a" * (MAX_EMAIL_LEN + 1) + "@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 422
