"""Tests for hooks — registration, bare decorator, called decorator, error isolation."""

import pytest

from supython.hooks import fire, on, reset


@pytest.fixture(autouse=True)
def _clean_hooks():
    reset()
    yield
    reset()


@pytest.mark.asyncio
async def test_on_bare_decorator():
    called = []

    @on("signup")
    async def handler(user, ctx):
        called.append(user)

    await fire("signup", "alice", None)
    assert called == ["alice"]


@pytest.mark.asyncio
async def test_on_called_decorator():
    called = []

    @on("signup")
    async def handler(user, ctx):
        called.append(user)

    await fire("signup", "bob", None)
    assert called == ["bob"]


@pytest.mark.asyncio
async def test_on_imperative():
    called = []

    async def handler(user, ctx):
        called.append(user)

    on("signup", handler)
    await fire("signup", "carol", None)
    assert called == ["carol"]


@pytest.mark.asyncio
async def test_fire_in_order():
    order = []

    @on("evt")
    async def first(*args):
        order.append(1)

    @on("evt")
    async def second(*args):
        order.append(2)

    await fire("evt")
    assert order == [1, 2]


@pytest.mark.asyncio
async def test_error_does_not_break_subsequent():
    order = []

    @on("evt")
    async def bad(*args):
        order.append("bad")
        raise RuntimeError("boom")

    @on("evt")
    async def good(*args):
        order.append("good")

    await fire("evt")
    assert order == ["bad", "good"]


@pytest.mark.asyncio
async def test_fire_unknown_event_is_noop():
    await fire("nonexistent")
