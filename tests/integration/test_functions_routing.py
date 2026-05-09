"""HTTP dispatch integration tests for /functions/{name:path}.

The global FunctionRegistry is replaced per-test with one pointing at the
fixture functions directory so no real ``functions/`` directory is required.
"""

from pathlib import Path

import httpx
import pytest

import supython.functions.router as fn_router
from supython.functions.loader import FunctionRegistry, reset_registry, set_registry
from supython.functions.schemas import (
    ERR_BODY_TOO_LARGE,
    ERR_FUNCTION_ERROR,
    ERR_FUNCTION_TIMEOUT,
    ERR_INVALID_TOKEN,
    ERR_METHOD_NOT_ALLOWED,
    ERR_NOT_FOUND,
)
from supython.settings import Settings

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "functions"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def functions_registry():
    """Replace the global dispatcher registry with the test fixtures."""
    reg = FunctionRegistry(FIXTURES, hot_reload=True)
    reg.discover()
    set_registry(reg)
    yield reg
    reset_registry()


async def _signup(client: httpx.AsyncClient, email: str = "user@example.com") -> dict:
    r = await client.post(
        "/auth/v1/signup", json={"email": email, "password": "password123"}
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Basic routing
# ---------------------------------------------------------------------------


async def test_get_hello_returns_200(client: httpx.AsyncClient):
    r = await client.get("/functions/hello")
    assert r.status_code == 200
    assert r.json() == {"msg": "hello, world"}


async def test_post_hello_also_returns_200(client: httpx.AsyncClient):
    r = await client.post("/functions/hello")
    assert r.status_code == 200
    assert "msg" in r.json()


async def test_put_hello_returns_405(client: httpx.AsyncClient):
    r = await client.put("/functions/hello")
    assert r.status_code == 405
    assert r.json()["detail"]["code"] == ERR_METHOD_NOT_ALLOWED


async def test_unknown_function_returns_404(client: httpx.AsyncClient):
    r = await client.get("/functions/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == ERR_NOT_FOUND


async def test_nested_route_reachable(client: httpx.AsyncClient):
    r = await client.get("/functions/nested/inner")
    assert r.status_code == 200
    assert r.json() == {"route": "nested/inner"}


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


async def test_authenticated_function_no_bearer_returns_401(client: httpx.AsyncClient):
    r = await client.post("/functions/me")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == ERR_INVALID_TOKEN


async def test_authenticated_function_tampered_bearer_returns_401(
    client: httpx.AsyncClient,
):
    r = await client.post(
        "/functions/me",
        headers={"authorization": "Bearer not.a.real.jwt"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == ERR_INVALID_TOKEN


async def test_authenticated_function_valid_bearer_returns_200(
    client: httpx.AsyncClient,
):
    data = await _signup(client)
    token = data["access_token"]

    r = await client.post(
        "/functions/me",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "user@example.com"
    assert body["role"] == "authenticated"
    assert body["id"] is not None


async def test_anon_function_accepts_no_bearer(client: httpx.AsyncClient):
    r = await client.get("/functions/hello")
    assert r.status_code == 200
    assert r.json()["msg"] == "hello, world"


# ---------------------------------------------------------------------------
# Body size limit
# ---------------------------------------------------------------------------


async def test_body_over_limit_returns_413(
    client: httpx.AsyncClient, monkeypatch
):
    """Content-Length header exceeding functions_max_body_bytes → 413."""
    tiny = Settings(functions_max_body_bytes=10)
    monkeypatch.setattr(fn_router, "get_settings", lambda: tiny)

    r = await client.post("/functions/hello", content=b"x" * 50)
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == ERR_BODY_TOO_LARGE


# ---------------------------------------------------------------------------
# Handler timeout (functions_max_handler_seconds)
# ---------------------------------------------------------------------------


async def test_slow_handler_returns_504(
    client: httpx.AsyncClient, monkeypatch
):
    """An async handler that exceeds the configured timeout returns 504."""
    fast = Settings(functions_max_handler_seconds=0.05)
    monkeypatch.setattr(fn_router, "get_settings", lambda: fast)

    r = await client.get("/functions/slow_async")
    assert r.status_code == 504
    assert r.json()["detail"]["code"] == ERR_FUNCTION_TIMEOUT


# ---------------------------------------------------------------------------
# Cleanup: failing aclose() must not mask the original handler error
# ---------------------------------------------------------------------------


async def test_aclose_failure_does_not_mask_handler_error(
    client: httpx.AsyncClient, monkeypatch, caplog
):
    """If postgrest.aclose() raises, the handler's real error still surfaces."""
    from supython.functions import context as fn_context

    async def boom(self):  # noqa: ARG001
        raise RuntimeError("aclose exploded")

    monkeypatch.setattr(fn_context.PostgrestClient, "aclose", boom)

    # boom raises a deliberate RuntimeError; the response should be the
    # standard 500/function_error mapped from THAT, not from aclose.
    with caplog.at_level("WARNING", logger="supython.functions.router"):
        r = await client.post("/functions/boom")

    assert r.status_code == 500
    assert r.json()["detail"]["code"] == ERR_FUNCTION_ERROR
    # The aclose failure should be logged separately, but the handler error
    # is what mapped to the response.
    assert any("postgrest close failed" in rec.message for rec in caplog.records)
