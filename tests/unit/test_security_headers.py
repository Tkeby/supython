import pytest

from supython.security_headers import SecurityHeadersMiddleware
from supython.settings import Settings


def _make_http_scope(
    method: str = "GET",
    path: str = "/test",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
    }


async def _run_asgi(
    middleware_cls,
    inner_app,
    scope,
    settings: Settings | None = None,
):
    mw = middleware_cls(inner_app, settings=settings)

    messages: list[dict] = []

    async def _send(msg):
        messages.append(msg)

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await mw(scope, _receive, _send)
    return messages


def _header_value(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    for n, v in headers:
        if n.lower() == name.lower():
            return v
    return None


@pytest.mark.asyncio
async def test_applies_default_headers_to_200():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    settings = Settings(site_url="http://localhost:8000")
    messages = await _run_asgi(
        SecurityHeadersMiddleware, app, _make_http_scope(), settings=settings
    )

    start_msg = messages[0]
    assert _header_value(start_msg["headers"], b"x-content-type-options") == b"nosniff"
    assert _header_value(start_msg["headers"], b"x-frame-options") == b"DENY"
    assert (
        _header_value(start_msg["headers"], b"referrer-policy")
        == b"strict-origin-when-cross-origin"
    )
    assert _header_value(start_msg["headers"], b"content-security-policy") is not None


@pytest.mark.asyncio
async def test_hsts_off_for_http_site_url():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    settings = Settings(site_url="http://localhost:8000")
    messages = await _run_asgi(
        SecurityHeadersMiddleware, app, _make_http_scope(), settings=settings
    )

    assert _header_value(messages[0]["headers"], b"strict-transport-security") is None


@pytest.mark.asyncio
async def test_hsts_auto_on_for_https_site_url():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    settings = Settings(site_url="https://api.example.com")
    messages = await _run_asgi(
        SecurityHeadersMiddleware, app, _make_http_scope(), settings=settings
    )

    hsts = _header_value(messages[0]["headers"], b"strict-transport-security")
    assert hsts is not None
    assert b"max-age=31536000" in hsts
    assert b"includeSubDomains" in hsts


@pytest.mark.asyncio
async def test_hsts_explicit_false_wins_over_https():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    settings = Settings(site_url="https://api.example.com", security_hsts_enabled=False)
    messages = await _run_asgi(
        SecurityHeadersMiddleware, app, _make_http_scope(), settings=settings
    )

    assert _header_value(messages[0]["headers"], b"strict-transport-security") is None


@pytest.mark.asyncio
async def test_hsts_explicit_true_wins_over_http():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    settings = Settings(site_url="http://localhost:8000", security_hsts_enabled=True)
    messages = await _run_asgi(
        SecurityHeadersMiddleware, app, _make_http_scope(), settings=settings
    )

    assert _header_value(messages[0]["headers"], b"strict-transport-security") is not None


@pytest.mark.asyncio
async def test_hsts_with_preload():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    settings = Settings(
        site_url="https://api.example.com",
        security_hsts_enabled=True,
        security_hsts_preload=True,
    )
    messages = await _run_asgi(
        SecurityHeadersMiddleware, app, _make_http_scope(), settings=settings
    )

    hsts = _header_value(messages[0]["headers"], b"strict-transport-security")
    assert hsts is not None
    assert b"preload" in hsts


@pytest.mark.asyncio
async def test_csp_applied_to_api_path():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    settings = Settings(site_url="http://localhost:8000")
    messages = await _run_asgi(
        SecurityHeadersMiddleware,
        app,
        _make_http_scope(path="/auth/v1/signup"),
        settings=settings,
    )

    assert _header_value(messages[0]["headers"], b"content-security-policy") is not None


@pytest.mark.asyncio
async def test_csp_skipped_for_docs_path():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    settings = Settings(site_url="http://localhost:8000")

    for path in [
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json",
        "/admin",
        "/admin/dashboard",
        "/admin/assets/index-CXk11u8r.js",
    ]:
        messages = await _run_asgi(
            SecurityHeadersMiddleware,
            app,
            _make_http_scope(path=path),
            settings=settings,
        )
        assert _header_value(messages[0]["headers"], b"content-security-policy") is None, path
        assert _header_value(messages[0]["headers"], b"x-content-type-options") == b"nosniff", path
        assert _header_value(messages[0]["headers"], b"x-frame-options") == b"DENY", path
        assert (
            _header_value(messages[0]["headers"], b"referrer-policy")
            == b"strict-origin-when-cross-origin"
        ), path


@pytest.mark.asyncio
async def test_does_not_override_existing_csp():
    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-security-policy", b"default-src 'self'")
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    settings = Settings(site_url="http://localhost:8000")
    messages = await _run_asgi(
        SecurityHeadersMiddleware, app, _make_http_scope(), settings=settings
    )

    csp = _header_value(messages[0]["headers"], b"content-security-policy")
    assert csp == b"default-src 'self'"


@pytest.mark.asyncio
async def test_passes_through_websocket():
    called = False

    async def inner_app(scope, receive, send):
        nonlocal called
        called = True

    mw = SecurityHeadersMiddleware(inner_app, settings=Settings())
    scope = {"type": "websocket", "path": "/ws", "headers": []}
    await mw(scope, lambda: {"type": "websocket.connect"}, lambda msg: None)
    assert called


@pytest.mark.asyncio
async def test_disabled_via_setting():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    settings = Settings(security_headers_enabled=False)
    messages = await _run_asgi(
        SecurityHeadersMiddleware, app, _make_http_scope(), settings=settings
    )

    assert _header_value(messages[0]["headers"], b"x-content-type-options") is None
    assert _header_value(messages[0]["headers"], b"x-frame-options") is None
    assert _header_value(messages[0]["headers"], b"referrer-policy") is None
    assert _header_value(messages[0]["headers"], b"content-security-policy") is None


@pytest.mark.asyncio
async def test_cors_preflight_gets_security_headers():
    from httpx import ASGITransport, AsyncClient

    from supython.app import create_app
    from supython.settings import Settings, get_settings

    get_settings.cache_clear()
    settings = Settings(cors_origins="http://test")
    app = create_app()
    # FastAPI re-reads settings at construction time; we need an app built
    # with the CORS-enabled settings. create_app() calls get_settings() which
    # is cached, so monkeypatch the cache to our CORS-enabled settings.
    get_settings.cache_clear()
    original_get_settings = get_settings

    def _patched():
        return settings

    import supython.app
    import supython.security_headers

    supython.app.get_settings = _patched
    supython.security_headers.get_settings = _patched
    app = create_app()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.options(
                "/auth/v1/login",
                headers={
                    "Origin": "http://test",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert response.status_code == 200
            assert "access-control-allow-origin" in response.headers
            assert response.headers.get("x-content-type-options") == "nosniff"
            assert response.headers.get("x-frame-options") == "DENY"
            assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
            assert "content-security-policy" in response.headers
    finally:
        supython.app.get_settings = original_get_settings
        supython.security_headers.get_settings = original_get_settings
        get_settings.cache_clear()
