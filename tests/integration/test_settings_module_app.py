"""Integration tests for ``SUPYTHON_SETTINGS_MODULE`` wiring."""

import os

import asyncpg
import httpx
import pytest
from httpx import ASGITransport


@pytest.mark.asyncio
async def test_settings_module_mounts_extra_router(pool: asyncpg.Pool):
    """The app with SUPYTHON_SETTINGS_MODULE mounts the extra router."""
    os.environ["SUPYTHON_SETTINGS_MODULE"] = "tests.fixtures.settings_modules.with_router"

    # Invalidate the lru_cache on get_settings so it picks up the env var.
    from supython.settings import get_settings

    get_settings.cache_clear()

    try:
        from supython.app import create_app

        app = create_app()

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://test",
        ) as client:
            resp = await client.get("/fixture-test")
            assert resp.status_code == 200
            assert resp.json() == {"ok": "true"}
    finally:
        del os.environ["SUPYTHON_SETTINGS_MODULE"]
        get_settings.cache_clear()
