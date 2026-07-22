"""GET verify pages are side-effect-free interstitials; POST consumes.

Mail scanners prefetch GET links — the page must not burn the token or mint
a session. Consumption only happens on the form POST.
"""

import json

import asyncpg
import httpx

EMAIL = "interstitial@example.com"


async def _signup(client: httpx.AsyncClient, email: str = EMAIL) -> dict:
    r = await client.post(
        "/auth/v1/signup", json={"email": email, "password": "password123"}
    )
    assert r.status_code == 201
    return r.json()


async def _latest_token(pool: asyncpg.Pool) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select payload from jobs.jobs where name = 'send_auth_email' "
            "order by created_at desc limit 1"
        )
    p = row["payload"]
    payload = p if isinstance(p, dict) else json.loads(p)
    return payload["text"].split("?token=")[-1].strip()


async def test_magic_link_get_is_html_and_does_not_consume(client, pool):
    await _signup(client)
    await client.post("/auth/v1/magiclink", json={"email": EMAIL})
    token = await _latest_token(pool)

    # Simulate a scanner prefetching the link — twice.
    for _ in range(2):
        r = await client.get(f"/auth/v1/magiclink/verify?token={token}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "<form" in r.text and 'method="post"' in r.text

    # The token still works: the user's actual click (form POST) signs in.
    r = await client.post(f"/auth/v1/magiclink/verify?token={token}")
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_magic_link_get_invalid_token_is_400_html(client):
    r = await client.get("/auth/v1/magiclink/verify?token=bogus")
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("text/html")
    assert "invalid or expired" in r.text.lower()
    # The interstitial CSP must survive on the invalid-link page too.
    assert "form-action 'self'" in r.headers["content-security-policy"]


async def test_interstitial_has_scoped_csp_that_allows_self_post(client, pool):
    """The global form-action 'none' CSP would block the token-consuming POST.

    The interstitial must ship its own scoped CSP so the self-POST and the
    inline <style> work while scripts stay forbidden (see issue #13).
    """
    await _signup(client)
    await client.post("/auth/v1/magiclink", json={"email": EMAIL})
    token = await _latest_token(pool)

    r = await client.get(f"/auth/v1/magiclink/verify?token={token}")
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "form-action 'self'" in csp
    assert "style-src 'unsafe-inline'" in csp
    assert "form-action 'none'" not in csp
    assert "script-src" not in csp


async def test_confirm_get_is_html_and_does_not_consume(client, pool):
    # Signup no longer stamps email_confirmed_at, so resend works even in
    # default (confirmation-off) mode and gives us a live confirm token.
    await _signup(client)
    r = await client.post("/auth/v1/confirm/resend", json={"email": EMAIL})
    assert r.status_code == 202
    token = await _latest_token(pool)

    r = await client.get(f"/auth/v1/confirm/verify?token={token}")
    assert r.status_code == 200
    assert "<form" in r.text

    r = await client.post(f"/auth/v1/confirm/verify?token={token}")
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_email_change_get_is_html_and_does_not_consume(client, pool):
    tokens = await _signup(client)
    r = await client.put(
        "/auth/v1/user",
        json={"email": "changed@example.com"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 200
    token = await _latest_token(pool)

    r = await client.get(f"/auth/v1/email_change/verify?token={token}")
    assert r.status_code == 200
    assert "<form" in r.text

    r = await client.post(f"/auth/v1/email_change/verify?token={token}")
    assert r.status_code in (200, 202)
