from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from urllib.parse import quote

from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import db, netutil, tokens
from ..settings import get_settings
from . import ratelimit, service
from .schemas import (
    ConfirmResendRequest,
    LogoutRequest,
    MagicLinkRequest,
    OtpRequest,
    OtpVerifyRequest,
    RecoverRequest,
    RecoverVerifyRequest,
    RefreshRequest,
    SignUpPendingResponse,
    SignUpRequest,
    TokenRequest,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
    UserUpdateResponse,
)

router = APIRouter(prefix="/auth/v1", tags=["auth"])


def _to_token_response(
    user: UserResponse, access: str, refresh: str, ttl: int
) -> TokenResponse:
    return TokenResponse(
        access_token=access,
        expires_in=ttl,
        refresh_token=refresh,
        user=user,
    )


def _auth_error(exc: service.AuthError) -> HTTPException:
    return HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": exc.message},
    )


async def _current_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        claims = tokens.decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}"
        ) from exc
    try:
        return UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token missing valid sub claim"
        ) from exc


def _client_ip(request: Request) -> str:
    return _client_ip_or_none(request) or "unknown"


def _client_ip_or_none(request: Request) -> str | None:
    """Return the client IP for rate limiting / audit logging, or None.

    Proxy-aware: when the TCP peer is listed in TRUSTED_PROXIES, the address
    is taken from X-Forwarded-For (rightmost untrusted hop — see
    supython.netutil.resolve_client_ip). Returns None (not "unknown") so
    callers can pass the result straight to a Postgres inet column.
    """
    peer = request.client.host if request.client else None
    return netutil.resolve_client_ip(
        peer,
        request.headers.get("x-forwarded-for"),
        get_settings().trusted_proxies,
    )


# Scoped CSP for the emailed-link interstitial pages. Unlike the global
# form-action 'none' policy, this permits the self-POST that consumes the token
# and the static inline <style>, while still forbidding all scripts.
_INTERSTITIAL_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)


# All styling is inline in a single <style> block — the scoped CSP allows
# 'unsafe-inline' for style but forbids scripts and every external resource
# (no web fonts, no images), so the page must be self-contained: system fonts,
# inline SVG icons, and prefers-color-scheme for dark mode.
_PAGE_STYLE = """
*{box-sizing:border-box}
:root{
  --bg1:#eef2ff;--bg2:#faf5ff;--card:#ffffff;--fg:#0f172a;--muted:#64748b;
  --border:#e2e8f0;--accent:#4f46e5;--accent-hover:#4338ca;--icon-bg:#eef2ff;
  --icon-fg:#4f46e5;--ring:rgba(79,70,229,.35)
}
@media (prefers-color-scheme:dark){
  :root{
    --bg1:#0b1120;--bg2:#0f172a;--card:#111827;--fg:#f1f5f9;--muted:#94a3b8;
    --border:#1f2937;--accent:#6366f1;--accent-hover:#818cf8;--icon-bg:#1e253b;
    --icon-fg:#a5b4fc;--ring:rgba(129,140,248,.4)
  }
}
html,body{height:100%}
body{
  margin:0;min-height:100%;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color:var(--fg);
  background:radial-gradient(1200px 600px at 50% -10%,var(--bg2),var(--bg1));
  display:flex;align-items:center;justify-content:center;padding:24px
}
.card{
  width:100%;max-width:420px;background:var(--card);
  border:1px solid var(--border);border-radius:16px;
  padding:40px 32px;text-align:center;
  box-shadow:0 10px 30px -12px rgba(2,6,23,.25),0 4px 8px -4px rgba(2,6,23,.1)
}
.icon{
  width:64px;height:64px;margin:0 auto 24px;border-radius:50%;
  background:var(--icon-bg);color:var(--icon-fg);
  display:flex;align-items:center;justify-content:center
}
.icon svg{width:32px;height:32px}
h1{font-size:1.4rem;line-height:1.3;margin:0 0 8px;font-weight:650}
p{margin:0 auto;max-width:32ch;color:var(--muted);font-size:.95rem;line-height:1.5}
form{margin:28px 0 0}
button{
  -webkit-appearance:none;appearance:none;cursor:pointer;
  width:100%;font-size:1rem;font-weight:600;
  padding:.8rem 1.4rem;border:0;border-radius:10px;
  color:#fff;background:var(--accent);transition:background .15s ease
}
button:hover{background:var(--accent-hover)}
button:focus-visible{outline:none;box-shadow:0 0 0 4px var(--ring)}
button:active{transform:translateY(1px)}
.footnote{margin-top:20px;font-size:.8rem;color:var(--muted)}
"""

_CHECK_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4 12 14.01l-3-3"/></svg>'
)
_WARN_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86'
    'a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/>'
    '<line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
)


def _shell(title: str, icon: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{title}</title>
<style>{_PAGE_STYLE}</style>
</head><body><main class="card">
<div class="icon">{icon}</div>
{body}
</main></body></html>"""


def _token_page(
    action_path: str,
    token: str,
    heading: str,
    button: str,
    subtitle: str,
) -> HTMLResponse:
    """Interstitial for emailed verify links.

    The emailed GET must stay side-effect-free — mail scanners prefetch GETs
    and would burn the token (or, in redirect mode, receive the session).
    Consumption happens on the form POST below, which scanners don't submit.
    The token rides in the form action's query string so no body parsing
    (python-multipart) is needed.

    The global CSP (form-action 'none') would block the self-POST that consumes
    the token, so this response carries its own scoped CSP (_INTERSTITIAL_CSP):
    still no scripts, but the form may post to itself and the inline styles
    apply. The markup has no user-injected content (heading/button/subtitle are
    static; token is quote()-encoded into the action), so 'unsafe-inline' for
    style is safe. The middleware yields to any pre-set CSP header.
    """
    action = f"{action_path}?token={quote(token, safe='')}"
    body = (
        f"<h1>{heading}</h1><p>{subtitle}</p>"
        f'<form method="post" action="{action}">'
        f'<button type="submit">{button}</button></form>'
        '<div class="footnote">This link can only be used once.</div>'
    )
    html = _shell(heading, _CHECK_ICON, body)
    return HTMLResponse(html, headers={"content-security-policy": _INTERSTITIAL_CSP})


def _invalid_link_page() -> HTMLResponse:
    body = (
        "<h1>Link invalid or expired</h1>"
        "<p>This link may have already been used or timed out. "
        "Request a new one and try again.</p>"
    )
    html = _shell("Link invalid or expired", _WARN_ICON, body)
    return HTMLResponse(
        html,
        status_code=400,
        headers={"content-security-policy": _INTERSTITIAL_CSP},
    )


def _rate_limit_dep(prefix: str, rule_attr: str):
    async def dep(request: Request) -> None:
        settings = get_settings()
        if not settings.auth_rate_limit_enabled:
            return
        rule = ratelimit.RateLimit(
            limit=getattr(settings, rule_attr),
            window_seconds=settings.auth_rate_limit_window_seconds,
        )
        bucket = f"{prefix}:{_client_ip(request)}"
        async with db.as_service_role() as conn:
            blocked, _ = await ratelimit.hit(conn, bucket=bucket, rule=rule)
        if blocked:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "rate_limited", "message": "Too many requests"},
                headers={"Retry-After": str(rule.window_seconds)},
            )

    return dep


_rl_token = _rate_limit_dep("auth.token", "auth_rate_limit_token_per_window")
_rl_signup = _rate_limit_dep("auth.signup", "auth_rate_limit_signup_per_window")
_rl_recover = _rate_limit_dep("auth.recover", "auth_rate_limit_recover_per_window")
_rl_otp = _rate_limit_dep("auth.otp", "auth_rate_limit_otp_per_window")
_rl_magiclink = _rate_limit_dep(
    "auth.magiclink", "auth_rate_limit_magiclink_per_window"
)
_rl_confirm = _rate_limit_dep("auth.confirm", "auth_rate_limit_confirm_per_window")


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[Depends(_rl_signup)],
    responses={
        202: {
            "model": SignUpPendingResponse,
            "description": "AUTH_REQUIRE_EMAIL_CONFIRMATION is on: the account "
            "was created and a confirmation email sent; no session is issued "
            "until /auth/v1/confirm/verify.",
        }
    },
)
async def signup(payload: SignUpRequest) -> Response:
    try:
        async with db.acquire() as conn:
            user, pair = await service.signup(
                conn,
                payload.email,
                payload.password,
                data=payload.data,
                redirect_url=payload.redirect_url,
            )
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    if pair is None:
        pending = SignUpPendingResponse(
            user=user, confirmation_sent_at=datetime.now(UTC)
        )
        return JSONResponse(jsonable_encoder(pending), status_code=202)
    return JSONResponse(
        jsonable_encoder(_to_token_response(user, *pair)), status_code=201
    )


@router.post("/token", response_model=TokenResponse, dependencies=[Depends(_rl_token)])
async def token(payload: TokenRequest) -> TokenResponse:
    try:
        async with db.acquire() as conn:
            result = await service.password_grant(
                conn, payload.email, payload.password
            )
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    return _to_token_response(*result)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request) -> TokenResponse:
    try:
        async with db.acquire() as conn:
            result = await service.refresh_grant(
                conn,
                payload.refresh_token,
                ip=_client_ip_or_none(request),
                ua=request.headers.get("user-agent"),
            )
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    return _to_token_response(*result)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    payload: LogoutRequest | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Sign out. ``scope``: local (default) / global / others.

    The bearer token, when present and valid, identifies the user for
    ``scope=global`` without needing a refresh token. An invalid bearer is
    ignored rather than rejected — revocation is a safe operation and the
    refresh token in the body is an independent credential.
    """
    user_id: UUID | None = None
    if authorization and authorization.lower().startswith("bearer "):
        try:
            claims = tokens.decode_access_token(authorization.split(" ", 1)[1])
            user_id = UUID(claims["sub"])
        except (jwt.PyJWTError, KeyError, ValueError):
            user_id = None
    body = payload or LogoutRequest()
    try:
        async with db.acquire() as conn:
            await service.logout(
                conn,
                body.refresh_token,
                scope=body.scope,
                user_id=user_id,
                ip=_client_ip_or_none(request),
                ua=request.headers.get("user-agent"),
            )
    except service.AuthError as exc:
        raise _auth_error(exc) from exc


@router.put(
    "/user",
    response_model=TokenResponse,
    dependencies=[Depends(_rl_token)],
    responses={
        200: {
            "description": "TokenResponse for a password change; "
            "UserUpdateResponse for email/data updates.",
        }
    },
)
async def update_user(
    payload: UserUpdateRequest,
    user_id: Annotated[UUID, Depends(_current_user_id)],
    request: Request,
) -> Response:
    """Update the caller's account. One mode per request:

    - ``password`` (+ ``current_password`` when one is set): revokes every
      refresh token, returns a fresh ``TokenResponse``. Exclusive.
    - ``email``: starts a dual-confirmation email change (both inboxes get a
      link); ``data``: shallow-merges into user_metadata. These two may be
      combined and return a ``UserUpdateResponse``.
    """
    ip = _client_ip_or_none(request)
    ua = request.headers.get("user-agent")
    invalid = _auth_error(
        service.AuthError(
            "invalid_request",
            "Provide password (exclusively), or email and/or data",
            400,
        )
    )
    try:
        async with db.acquire() as conn:
            if payload.password is not None:
                if payload.email is not None or payload.data is not None:
                    raise invalid
                result = await service.update_password(
                    conn,
                    user_id,
                    payload.password,
                    payload.current_password,
                    ip=ip,
                    ua=ua,
                )
                return JSONResponse(jsonable_encoder(_to_token_response(*result)))

            if payload.email is None and payload.data is None:
                raise invalid
            email_change_sent_at = None
            if payload.data is not None:
                await service.update_user_metadata(conn, user_id, payload.data)
            if payload.email is not None:
                await service.request_email_change(
                    conn, user_id, payload.email, ip=ip, ua=ua
                )
                email_change_sent_at = datetime.now(UTC)
            user = await service.get_user(conn, user_id)
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    if user is None:
        raise HTTPException(404, "User not found")
    return JSONResponse(
        jsonable_encoder(
            UserUpdateResponse(user=user, email_change_sent_at=email_change_sent_at)
        )
    )


@router.get("/user", response_model=UserResponse)
async def me(
    user_id: Annotated[UUID, Depends(_current_user_id)],
) -> UserResponse:
    async with db.acquire() as conn:
        user = await service.get_user(conn, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.post("/recover", status_code=202, dependencies=[Depends(_rl_recover)])
async def request_recover(payload: RecoverRequest) -> None:
    async with db.acquire() as conn:
        await service.request_recover(conn, payload.email)


@router.post(
    "/recover/verify",
    response_model=TokenResponse,
    dependencies=[Depends(_rl_recover)],
)
async def verify_recover(payload: RecoverVerifyRequest, request: Request) -> TokenResponse:
    try:
        async with db.acquire() as conn:
            result = await service.verify_recover(
                conn,
                payload.email,
                payload.token,
                payload.password,
                ip=_client_ip_or_none(request),
                ua=request.headers.get("user-agent"),
            )
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    return _to_token_response(*result)


@router.post("/magiclink", status_code=202, dependencies=[Depends(_rl_magiclink)])
async def request_magic_link(payload: MagicLinkRequest) -> None:
    try:
        async with db.acquire() as conn:
            await service.request_magic_link(
                conn,
                payload.email,
                redirect_url=payload.redirect_url,
                ttl=payload.ttl,
            )
    except service.AuthError as exc:
        # Currently only invalid_redirect (400) — a bad email is filtered by
        # EmailStr at the schema layer before this handler ever runs.
        raise _auth_error(exc) from exc


@router.get(
    "/magiclink/verify",
    dependencies=[Depends(_rl_magiclink)],
    response_class=HTMLResponse,
)
async def magic_link_page(
    token: Annotated[str, Query(description="Raw magic-link token from the email")],
) -> Response:
    """Side-effect-free landing page for the emailed link.

    Renders a confirm button whose POST consumes the token; a scanner
    prefetching this GET burns nothing. Invalid/expired tokens get a 400
    page without revealing anything else.
    """
    async with db.acquire() as conn:
        alive = await service.peek_one_time_token(conn, token, ["magic_link"])
    if not alive:
        return _invalid_link_page()
    return _token_page(
        "/auth/v1/magiclink/verify",
        token,
        "Sign in",
        "Continue",
        "Click below to finish signing in to your account.",
    )


@router.post(
    "/magiclink/verify",
    dependencies=[Depends(_rl_magiclink)],
)
async def verify_magic_link(
    token: Annotated[str, Query(description="Raw magic-link token from the email")],
) -> Response:
    """Consume a magic-link token (token in the query string, no body).

    JSON callers (no ``redirect_url`` at request time) get a ``TokenResponse``.
    A caller that requested a redirect gets a 302 to that URL with the token
    pair in the fragment — the same shape as the OAuth callback — so a browser
    arriving via the interstitial ends up on the SPA's page with a session.
    """
    try:
        async with db.acquire() as conn:
            user, access, refresh, ttl, redirect_url = await service.verify_magic_link(
                conn, token
            )
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    if redirect_url:
        fragment = (
            f"access_token={access}"
            f"&refresh_token={refresh}"
            f"&expires_in={ttl}"
            f"&token_type=bearer"
        )
        return RedirectResponse(f"{redirect_url}#{fragment}", status_code=302)
    return JSONResponse(
        jsonable_encoder(_to_token_response(user, access, refresh, ttl))
    )


@router.get(
    "/confirm/verify",
    dependencies=[Depends(_rl_confirm)],
    response_class=HTMLResponse,
)
async def signup_confirm_page(
    token: Annotated[str, Query(description="Raw confirmation token from the email")],
) -> Response:
    """Side-effect-free landing page for the emailed confirmation link."""
    async with db.acquire() as conn:
        alive = await service.peek_one_time_token(conn, token, ["signup_confirm"])
    if not alive:
        return _invalid_link_page()
    return _token_page(
        "/auth/v1/confirm/verify",
        token,
        "Confirm your email",
        "Confirm",
        "Confirm your email address to activate your account.",
    )


@router.post(
    "/confirm/verify",
    dependencies=[Depends(_rl_confirm)],
)
async def verify_signup_confirm(
    token: Annotated[str, Query(description="Raw confirmation token from the email")],
    request: Request,
) -> Response:
    """Consume a signup-confirmation token and issue the first session.

    Same response contract as ``POST /magiclink/verify``: JSON
    ``TokenResponse`` by default, or a 302 to the ``redirect_url`` given at
    signup/resend time with the token pair in the fragment.
    """
    try:
        async with db.acquire() as conn:
            user, access, refresh, ttl, redirect_url = (
                await service.verify_signup_confirm(
                    conn,
                    token,
                    ip=_client_ip_or_none(request),
                    ua=request.headers.get("user-agent"),
                )
            )
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    if redirect_url:
        fragment = (
            f"access_token={access}"
            f"&refresh_token={refresh}"
            f"&expires_in={ttl}"
            f"&token_type=bearer"
        )
        return RedirectResponse(f"{redirect_url}#{fragment}", status_code=302)
    return JSONResponse(
        jsonable_encoder(_to_token_response(user, access, refresh, ttl))
    )


@router.post("/confirm/resend", status_code=202, dependencies=[Depends(_rl_confirm)])
async def resend_signup_confirm(payload: ConfirmResendRequest) -> None:
    try:
        async with db.acquire() as conn:
            await service.resend_signup_confirm(
                conn, payload.email, redirect_url=payload.redirect_url
            )
    except service.AuthError as exc:
        # Only invalid_redirect (400) surfaces; unknown/confirmed emails stay
        # a silent 202 so the endpoint can't be used for enumeration.
        raise _auth_error(exc) from exc


@router.get(
    "/email_change/verify",
    dependencies=[Depends(_rl_confirm)],
    response_class=HTMLResponse,
)
async def email_change_page(
    token: Annotated[str, Query(description="Raw email-change token from the email")],
) -> Response:
    """Side-effect-free landing page for either side's email-change link."""
    async with db.acquire() as conn:
        alive = await service.peek_one_time_token(
            conn, token, ["email_change_current", "email_change_new"]
        )
    if not alive:
        return _invalid_link_page()
    return _token_page(
        "/auth/v1/email_change/verify",
        token,
        "Confirm email change",
        "Confirm",
        "Confirm this address to complete your email change.",
    )


@router.post(
    "/email_change/verify",
    dependencies=[Depends(_rl_confirm)],
    responses={
        202: {"description": "This side is confirmed; the other inbox's link is still pending."}
    },
)
async def verify_email_change(
    token: Annotated[str, Query(description="Raw email-change token from the email")],
    request: Request,
) -> Response:
    """Consume one side of a dual-confirmation email change.

    202 while the other inbox has not confirmed yet; once both sides have,
    the change applies and a ``TokenResponse`` for the updated account is
    returned.
    """
    try:
        async with db.acquire() as conn:
            result = await service.verify_email_change(
                conn,
                token,
                ip=_client_ip_or_none(request),
                ua=request.headers.get("user-agent"),
            )
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    if result is None:
        return JSONResponse(
            {"status": "pending_other_confirmation"}, status_code=202
        )
    return JSONResponse(jsonable_encoder(_to_token_response(*result)))


@router.post("/otp", status_code=202, dependencies=[Depends(_rl_otp)])
async def request_otp(payload: OtpRequest) -> None:
    async with db.acquire() as conn:
        await service.request_otp(conn, payload.email)


@router.post("/otp/verify", response_model=TokenResponse, dependencies=[Depends(_rl_otp)])
async def verify_otp(payload: OtpVerifyRequest) -> TokenResponse:
    try:
        async with db.acquire() as conn:
            result = await service.verify_otp(conn, payload.email, payload.token)
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    return _to_token_response(*result)


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------


@router.get("/authorize/{provider}", status_code=302)
async def oauth_authorize(
    provider: str,
    redirect_uri: Annotated[str, Query(description="URL to redirect back to after login")],
) -> RedirectResponse:
    """Initiate an OAuth2 Authorization Code flow for the given provider."""
    try:
        url = await service.oauth_start(provider, redirect_uri)
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    return RedirectResponse(url, status_code=302)


@router.get("/callback/{provider}", status_code=302)
async def oauth_callback(
    provider: str,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    request: Request,
) -> RedirectResponse:
    """Handle the provider callback, exchange the code, and redirect with tokens."""
    try:
        async with db.acquire() as conn:
            result = await service.oauth_finish(
                conn,
                provider,
                code,
                state,
                ip=_client_ip_or_none(request),
                ua=request.headers.get("user-agent"),
            )
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    _user, access, refresh, ttl, redirect_uri = result
    fragment = (
        f"access_token={access}"
        f"&refresh_token={refresh}"
        f"&expires_in={ttl}"
        f"&token_type=bearer"
    )
    return RedirectResponse(f"{redirect_uri}#{fragment}", status_code=302)
