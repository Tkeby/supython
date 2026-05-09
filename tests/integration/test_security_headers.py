"""Integration smoke tests for the security headers middleware.

These exercise the real ASGI app through the test ``client`` fixture so
the full middleware stack (CORS, RequestId, RequestLogging, BodySize,
SecurityHeaders) participates. Pure middleware unit tests live in
`tests/unit/test_security_headers.py`.
"""

import pytest


@pytest.mark.asyncio
async def test_integration_smoke_livez_headers(client):
    response = await client.get("/livez")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "content-security-policy" in response.headers


@pytest.mark.asyncio
async def test_swagger_ui_loads(client):
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower() or "swagger" in response.text.lower()
