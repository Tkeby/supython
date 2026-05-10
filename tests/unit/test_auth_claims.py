"""Tests for the claims-provider registry — pure Python, no DB."""

import uuid
from datetime import UTC, datetime

import pytest

from supython.auth import claims
from supython.auth.schemas import UserResponse


@pytest.fixture(autouse=True)
def _clean_registry():
    claims.reset()
    yield
    claims.reset()


def _user() -> UserResponse:
    return UserResponse(
        id=uuid.uuid4(),
        email="alice@test.com",
        created_at=datetime.now(UTC),
    )


async def test_collect_with_no_providers_returns_empty():
    assert await claims.collect(_user(), conn=None) == {}


async def test_register_returns_function_unchanged():
    async def provider(user, conn):
        return {"x": 1}

    assert claims.register(provider) is provider


async def test_collect_invokes_each_provider_in_order():
    seen: list[str] = []

    @claims.register
    async def first(user, conn):
        seen.append("first")
        return {"a": 1}

    @claims.register
    async def second(user, conn):
        seen.append("second")
        return {"b": 2}

    out = await claims.collect(_user(), conn=None)
    assert out == {"a": 1, "b": 2}
    assert seen == ["first", "second"]


async def test_later_provider_wins_on_key_collision():
    @claims.register
    async def first(user, conn):
        return {"role_internal": "viewer"}

    @claims.register
    async def second(user, conn):
        return {"role_internal": "admin"}

    out = await claims.collect(_user(), conn=None)
    assert out == {"role_internal": "admin"}


@pytest.mark.parametrize("reserved", ["sub", "email", "role", "aud", "iat", "exp", "jti"])
async def test_reserved_claims_are_filtered(reserved):
    @claims.register
    async def provider(user, conn):
        return {reserved: "evil", "org_id": "ok"}

    out = await claims.collect(_user(), conn=None)
    assert reserved not in out
    assert out == {"org_id": "ok"}


async def test_provider_returning_empty_dict_is_safe():
    @claims.register
    async def provider(user, conn):
        return {}

    assert await claims.collect(_user(), conn=None) == {}


async def test_provider_exception_propagates():
    """A broken provider must fail loudly rather than silently issue a
    token missing the claim the app relies on for authz."""

    class Boom(RuntimeError):
        pass

    @claims.register
    async def provider(user, conn):
        raise Boom("db query failed")

    with pytest.raises(Boom):
        await claims.collect(_user(), conn=None)


async def test_reset_clears_providers():
    @claims.register
    async def provider(user, conn):
        return {"x": 1}

    assert await claims.collect(_user(), conn=None) == {"x": 1}
    claims.reset()
    assert await claims.collect(_user(), conn=None) == {}
