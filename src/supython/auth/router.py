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
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse

from .. import db, tokens
from ..settings import get_settings
from . import ratelimit, service
from .schemas import (
    MagicLinkRequest,
    OtpRequest,
    OtpVerifyRequest,
    RecoverRequest,
    RecoverVerifyRequest,
    RefreshRequest,
    SignUpRequest,
    TokenRequest,
    TokenResponse,
    UserResponse,
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
    if request.client is None:
        return "unknown"
    return request.client.host


def _client_ip_or_none(request: Request) -> str | None:
    """Return the client IP for audit logging, or None when unavailable.

    Unlike _client_ip, returns None instead of "unknown" so callers can safely
    pass the result to a Postgres inet column without a cast error.
    """
    if request.client is None:
        return None
    return request.client.host


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


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[Depends(_rl_signup)],
)
async def signup(payload: SignUpRequest) -> TokenResponse:
    try:
        async with db.acquire() as conn:
            result = await service.signup(conn, payload.email, payload.password)
    except service.AuthError as exc:
        raise _auth_error(exc) from exc
    return _to_token_response(*result)


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
async def logout(payload: RefreshRequest) -> None:
    async with db.acquire() as conn:
        await service.logout(conn, payload.refresh_token)


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
)
async def verify_magic_link(
    token: Annotated[str, Query(description="Raw magic-link token from the email")],
) -> Response:
    """Verify a magic-link token.

    Legacy/JSON callers (no ``redirect_url`` at request time) get the same
    ``TokenResponse`` body as always. A caller that requested a redirect gets a
    302 to that URL with the token pair in the fragment — the same shape as the
    OAuth callback (`oauth_callback` below) — so a browser landing here from an
    emailed link ends up on the SPA's own page with a session, not looking at
    raw JSON.
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
