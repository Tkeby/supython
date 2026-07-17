"""Auth business logic: signup, password grant, refresh rotation, logout."""

import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import asyncpg
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .. import mail, passwords, tokens
from ..mailer import EmailMessage
from ..settings import get_settings
from . import claims
from .schemas import UserResponse

logger = logging.getLogger(__name__)


class AuthError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _row_to_user(row: asyncpg.Record) -> UserResponse:
    return UserResponse(
        id=row["id"],
        email=row["email"],
        created_at=row["created_at"],
    )

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def _audit_log(
    conn: asyncpg.Connection,
    user_id: UUID,
    event: str,
    *,
    ip: str | None = None,
    ua: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    await conn.execute(
        """
        insert into auth.audit_log (user_id, event, ip, ua, payload)
        values ($1, $2, $3::inet, $4, $5::jsonb)
        """,
        user_id,
        event,
        ip,
        ua,
        json.dumps(payload or {}),
    )


async def _assert_can_authenticate(
    conn: asyncpg.Connection, user_id: UUID
) -> None:
    """Refuse session issuance for an account that is not eligible to sign in.

    Enforced at the issuance funnel so every grant type — password, refresh,
    magic-link, OTP, recover, OAuth — is gated by the same rules:

    - ``banned_until`` in the future ⇒ ``account_disabled`` (403), deliberately
      distinct from ``invalid_credentials`` (401) so a caller can tell "wrong
      password" apart from "correct credentials, but locked out".
    - ``activated_at is null`` ⇒ ``account_inactive`` (403). A consumer can
      pre-create an ``auth.users`` row (e.g. an invite flow that provisions the
      user plus a role/membership up front) that must not authenticate until an
      explicit ``activate_user`` call; signup and OAuth sign-in activate inline.

    Gating at issuance (rather than only at password verification) means the
    check also lands on the passwordless verifies and on ``refresh_grant``, so
    an in-flight session dies at its next refresh — near-immediate revocation
    with no token blocklist.
    """
    row = await conn.fetchrow(
        "select banned_until, activated_at from auth.users where id = $1",
        user_id,
    )
    if row is None:
        # The row vanished between the caller's lookup and issuance (e.g. a
        # concurrent delete). Fail closed rather than mint an orphan session.
        raise AuthError("account_disabled", "Account is not eligible to sign in", 403)
    banned_until = row["banned_until"]
    if banned_until is not None and banned_until > datetime.now(UTC):
        raise AuthError("account_disabled", "Account is disabled", 403)
    if row["activated_at"] is None:
        raise AuthError("account_inactive", "Account is not activated", 403)


async def _issue_pair(
    conn: asyncpg.Connection, user: UserResponse
) -> tuple[str, str, int]:
    await _assert_can_authenticate(conn, user.id)
    extra = await claims.collect(user, conn)
    access, ttl = tokens.issue_access_token(
        user.id, user.email, extra_claims=extra or None
    )
    refresh = tokens.issue_refresh_token()
    await conn.execute(
        "insert into auth.refresh_tokens (user_id, token) values ($1, $2)",
        user.id,
        refresh,
    )
    return access, refresh, ttl


async def _store_one_time_token(
    conn: asyncpg.Connection,
    user_id: UUID,
    token_type: str,
    ttl_seconds: int,
    *,
    redirect_url: str | None = None,
) -> str:
    """Generate, sha256-hash, and store a one-time token. Returns the raw token.

    ``redirect_url`` is stored only for magic-link tokens (recover/otp pass
    None ⇒ NULL); verify reads it back to decide between a 302 and JSON.
    """
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    await conn.execute(
        """
        insert into auth.one_time_tokens (user_id, type, token_hash, expires_at, redirect_url)
        values ($1, $2, $3, $4, $5)
        """,
        user_id,
        token_type,
        _sha256(raw),
        expires_at,
        redirect_url,
    )
    return raw


async def _verify_one_time_token(
    conn: asyncpg.Connection,
    token: str,
    token_type: str,
    email: str | None = None,
) -> asyncpg.Record:
    """Return a valid, unexpired, unused token row. Raises AuthError if not found."""
    token_hash = _sha256(token)
    if email is not None:
        row = await conn.fetchrow(
            """
            select ott.id as ott_id, ott.redirect_url, u.id, u.email, u.created_at
            from auth.one_time_tokens ott
            join auth.users u on u.id = ott.user_id
            where ott.token_hash = $1
              and ott.type = $2
              and ott.used_at is null
              and ott.expires_at > now()
              and u.email = $3
            """,
            token_hash,
            token_type,
            email,
        )
    else:
        row = await conn.fetchrow(
            """
            select ott.id as ott_id, ott.redirect_url, u.id, u.email, u.created_at
            from auth.one_time_tokens ott
            join auth.users u on u.id = ott.user_id
            where ott.token_hash = $1
              and ott.type = $2
              and ott.used_at is null
              and ott.expires_at > now()
            """,
            token_hash,
            token_type,
        )
    if not row:
        logger.warning("auth.verify_one_time_token: invalid or expired %s token", token_type)
        raise AuthError("invalid_token", "Token is invalid or expired", 400)
    return row


async def signup(
    conn: asyncpg.Connection, email: str, password: str
) -> tuple[UserResponse, str, str, int]:
    existing = await conn.fetchval(
        "select 1 from auth.users where email = $1", email
    )
    if existing:
        raise AuthError("email_taken", "Email already registered", 409)

    pw_hash = passwords.hash_password(password)
    row = await conn.fetchrow(
        """
        insert into auth.users (email, encrypted_password, email_confirmed_at, activated_at)
        values ($1, $2, now(), now())
        returning id, email, created_at
        """,
        email,
        pw_hash,
    )
    user = _row_to_user(row)
    access, refresh, ttl = await _issue_pair(conn, user)

    try:
        from .. import db as _db
        from ..hooks import build_hook_ctx, fire

        synth_claims = {"sub": str(user.id), "email": user.email, "role": "authenticated"}
        async with _db.as_role("authenticated", synth_claims) as role_conn:
            ctx = build_hook_ctx(conn=role_conn)
            await fire("signup", user, ctx)
    except Exception:
        logger.warning("hooks: signup hook failed", exc_info=True)

    return user, access, refresh, ttl


async def password_grant(
    conn: asyncpg.Connection, email: str, password: str
) -> tuple[UserResponse, str, str, int]:
    row = await conn.fetchrow(
        """
        select id, email, encrypted_password, created_at
        from auth.users
        where email = $1
        """,
        email,
    )
    if not row or not row["encrypted_password"]:
        logger.warning("auth.password_grant: unknown email %s", email)
        raise AuthError("invalid_credentials", "Invalid email or password", 401)
    if not passwords.verify_password(row["encrypted_password"], password):
        logger.warning("auth.password_grant: bad password for %s", email)
        raise AuthError("invalid_credentials", "Invalid email or password", 401)

    user = _row_to_user(row)
    # Issue first: _issue_pair raises account_disabled (403) for a banned user,
    # so we don't stamp last_sign_in_at for a sign-in that was refused.
    access, refresh, ttl = await _issue_pair(conn, user)
    await conn.execute(
        "update auth.users set last_sign_in_at = now() where id = $1",
        row["id"],
    )
    return user, access, refresh, ttl


async def refresh_grant(
    conn: asyncpg.Connection,
    refresh_token: str,
    *,
    ip: str | None = None,
    ua: str | None = None,
) -> tuple[UserResponse, str, str, int]:
    row = await conn.fetchrow(
        """
        select rt.id          as rt_id,
               rt.revoked     as rt_revoked,
               u.id           as id,
               u.email        as email,
               u.created_at   as created_at
        from auth.refresh_tokens rt
        join auth.users u on u.id = rt.user_id
        where rt.token = $1
        """,
        refresh_token,
    )
    if not row:
        logger.warning("auth.refresh_grant: unknown refresh token")
        raise AuthError("invalid_refresh_token", "Refresh token is invalid", 401)

    if row["rt_revoked"]:
        # A revoked token was presented — this is a reuse attack.
        # Walk the full descendant chain and revoke every live child token,
        # then record the incident before refusing the request.
        async with conn.transaction():
            await conn.execute(
                """
                with recursive descendants as (
                    select id, token
                    from auth.refresh_tokens
                    where parent = $1
                    union all
                    select rt.id, rt.token
                    from auth.refresh_tokens rt
                    join descendants d on rt.parent = d.token
                )
                update auth.refresh_tokens
                set revoked = true
                where id in (select id from descendants)
                """,
                refresh_token,
            )
            await _audit_log(
                conn, row["id"], "refresh_token_reuse",
                ip=ip, ua=ua,
                payload={"token_id": str(row["rt_id"])},
            )
        raise AuthError(
            "token_reuse_detected",
            "Token reuse detected — all sessions have been invalidated",
            401,
        )

    user = _row_to_user(row)
    # refresh_grant mints its own pair rather than routing through _issue_pair,
    # so the eligibility gate has to be applied here too. Check before rotating:
    # a banned user is refused without burning their current refresh token.
    await _assert_can_authenticate(conn, user.id)
    new_refresh = tokens.issue_refresh_token()
    async with conn.transaction():
        await conn.execute(
            "update auth.refresh_tokens set revoked = true where id = $1",
            row["rt_id"],
        )
        await conn.execute(
            "insert into auth.refresh_tokens (user_id, token, parent) "
            "values ($1, $2, $3)",
            user.id,
            new_refresh,
            refresh_token,
        )
    extra = await claims.collect(user, conn)
    access, ttl = tokens.issue_access_token(
        user.id, user.email, extra_claims=extra or None
    )
    return user, access, new_refresh, ttl


async def logout(conn: asyncpg.Connection, refresh_token: str) -> None:
    await conn.execute(
        "update auth.refresh_tokens set revoked = true where token = $1",
        refresh_token,
    )


async def get_user(
    conn: asyncpg.Connection, user_id: UUID
) -> UserResponse | None:
    row = await conn.fetchrow(
        "select id, email, created_at from auth.users where id = $1",
        user_id,
    )
    return _row_to_user(row) if row else None


async def activate_user(conn: asyncpg.Connection, user_id: UUID) -> None:
    """Mark a pre-created account eligible to authenticate.

    A consumer that provisions an ``auth.users`` row up front (e.g. an invite
    flow that creates the user plus a role/membership before the person has set
    up credentials) calls this at its intended activation step. Until then the
    row's ``activated_at`` is null and every session-issuing path refuses it with
    ``account_inactive`` (403). Self-serve signup and OAuth sign-in activate
    inline, so this is only needed for externally pre-created rows.

    Idempotent: activating an already-active user is a no-op and does not move
    the existing ``activated_at``. Raises ``AuthError('user_not_found', 404)``
    when no such user exists, so a mistyped id surfaces instead of silently
    doing nothing.
    """
    exists = await conn.fetchval(
        "select 1 from auth.users where id = $1", user_id
    )
    if not exists:
        raise AuthError("user_not_found", "User not found", 404)
    await conn.execute(
        """
        update auth.users
        set activated_at = now()
        where id = $1 and activated_at is null
        """,
        user_id,
    )


async def request_recover(
    conn: asyncpg.Connection, email: str
) -> None:
    row = await conn.fetchrow(
        "select id from auth.users where email = $1", email
    )
    if not row:
        return
    s = get_settings()
    async with conn.transaction():
        raw = await _store_one_time_token(conn, row["id"], "recover", s.recover_token_ttl)
        await mail.dispatch(
            conn,
            EmailMessage(
                to=[email],
                subject="Reset your password",
                text=f"Use this token to reset your password: {raw}",
            ),
            job_name="send_auth_email",
        )


async def verify_recover(
    conn: asyncpg.Connection,
    email: str,
    token: str,
    new_password: str,
    *,
    ip: str | None = None,
    ua: str | None = None,
) -> tuple[UserResponse, str, str, int]:
    row = await _verify_one_time_token(conn, token, "recover", email)
    pw_hash = passwords.hash_password(new_password)
    user = _row_to_user(row)
    async with conn.transaction():
        await conn.execute(
            "update auth.one_time_tokens set used_at = now() where id = $1",
            row["ott_id"],
        )
        await conn.execute(
            "update auth.users set encrypted_password = $1 where id = $2",
            pw_hash,
            row["id"],
        )
        await _audit_log(
            conn, user.id, "password_change",
            ip=ip, ua=ua,
            payload={"via": "recover"},
        )
        access, refresh, ttl = await _issue_pair(conn, user)
    return user, access, refresh, ttl


def _url_origin(url: str) -> str | None:
    """Return the ``scheme://host[:port]`` origin of an absolute http(s) URL.

    Returns None for anything that isn't a well-formed absolute http(s) URL, or
    that carries embedded credentials (``user:pass@host``) — those have no place
    in a redirect target and are a classic obfuscation vector. Origins are
    lower-cased so comparison is case-insensitive on scheme/host.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc or "@" in parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def validate_magic_link_redirect(redirect_url: str, allowlist_csv: str) -> str:
    """Return ``redirect_url`` when its origin is allowlisted, else raise.

    ``allowlist_csv`` is the comma-separated ``MAGIC_LINK_REDIRECT_ALLOWLIST``
    setting. An empty allowlist rejects every redirect (the feature is off and
    fails closed). Matching is by origin only, so any path/query/fragment under
    an allowlisted origin is accepted. Raises ``AuthError('invalid_redirect')``
    (400) on any miss — the caller turns that into an HTTP 400.
    """
    origin = _url_origin(redirect_url)
    if origin is None:
        raise AuthError(
            "invalid_redirect", "redirect_url must be an absolute http(s) URL", 400
        )
    allowed = {
        o for entry in allowlist_csv.split(",") if (o := _url_origin(entry.strip()))
    }
    if origin not in allowed:
        raise AuthError(
            "invalid_redirect", "redirect_url origin is not allowlisted", 400
        )
    return redirect_url


def _clamp_magic_link_ttl(ttl: int | None, settings: Any) -> int:
    """Resolve the effective magic-link TTL in seconds.

    ``None`` ⇒ the ``magic_link_token_ttl`` default. A supplied value is clamped
    to ``[60, magic_link_max_ttl]`` so a caller can neither mint a link that
    expires too fast to click nor one that outlives the configured ceiling.
    """
    if ttl is None:
        return settings.magic_link_token_ttl
    return max(60, min(ttl, settings.magic_link_max_ttl))


async def request_magic_link(
    conn: asyncpg.Connection,
    email: str,
    *,
    redirect_url: str | None = None,
    ttl: int | None = None,
) -> None:
    s = get_settings()
    # Validate the redirect before the user lookup: a bad redirect is a client
    # error regardless of whether the email exists, and checking it here keeps
    # the email-enumeration silence below intact (unknown emails still 202).
    if redirect_url is not None:
        validate_magic_link_redirect(redirect_url, s.magic_link_redirect_allowlist)
    row = await conn.fetchrow(
        "select id from auth.users where email = $1", email
    )
    if not row:
        return
    async with conn.transaction():
        raw = await _store_one_time_token(
            conn,
            row["id"],
            "magic_link",
            _clamp_magic_link_ttl(ttl, s),
            redirect_url=redirect_url,
        )
        verify_url = f"{s.site_url}/auth/v1/magiclink/verify?token={raw}"
        await mail.dispatch(
            conn,
            EmailMessage(
                to=[email],
                subject="Sign in to your account",
                text=f"Click the link to sign in: {verify_url}",
            ),
            job_name="send_auth_email",
        )


async def verify_magic_link(
    conn: asyncpg.Connection, token: str
) -> tuple[UserResponse, str, str, int, str | None]:
    row = await _verify_one_time_token(conn, token, "magic_link")
    user = _row_to_user(row)
    async with conn.transaction():
        await conn.execute(
            "update auth.one_time_tokens set used_at = now() where id = $1",
            row["ott_id"],
        )
        access, refresh, ttl = await _issue_pair(conn, user)
    # redirect_url is None for legacy/JSON callers; the router 302-redirects
    # (OAuth-style, tokens in the fragment) only when it is set.
    return user, access, refresh, ttl, row["redirect_url"]


async def request_otp(
    conn: asyncpg.Connection, email: str
) -> None:
    row = await conn.fetchrow(
        "select id from auth.users where email = $1", email
    )
    if not row:
        return
    s = get_settings()
    async with conn.transaction():
        raw = await _store_one_time_token(conn, row["id"], "otp", s.otp_token_ttl)
        await mail.dispatch(
            conn,
            EmailMessage(
                to=[email],
                subject="Your one-time password",
                text=f"Your OTP is: {raw}",
            ),
            job_name="send_auth_email",
        )


async def verify_otp(
    conn: asyncpg.Connection, email: str, token: str
) -> tuple[UserResponse, str, str, int]:
    row = await _verify_one_time_token(conn, token, "otp", email)
    user = _row_to_user(row)
    async with conn.transaction():
        await conn.execute(
            "update auth.one_time_tokens set used_at = now() where id = $1",
            row["ott_id"],
        )
        access, refresh, ttl = await _issue_pair(conn, user)
    return user, access, refresh, ttl


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------
s = get_settings()

_OAUTH_STATE_MAX_AGE = s.oauth_state_max_age  # seconds — state cookie lifetime


def _state_signer() -> URLSafeTimedSerializer:
    from ..secretset import load_signing_secret

    manifest_secret = load_signing_secret("oauth_state")
    if manifest_secret is not None:
        return URLSafeTimedSerializer(manifest_secret)
    legacy = get_settings().oauth_state_secret
    if legacy is None:
        raise RuntimeError(
            "no OAuth state secret configured; run "
            "`supython secret rotate oauth` or set OAUTH_STATE_SECRET"
        )
    return URLSafeTimedSerializer(legacy)


async def oauth_start(provider_name: str, redirect_uri: str) -> str:
    """Return the provider's authorization URL with a signed, time-limited state."""
    from .providers.registry import get_provider

    try:
        provider = get_provider(provider_name)
    except KeyError as exc:
        raise AuthError("unknown_provider", str(exc), 400) from exc

    code_verifier = secrets.token_urlsafe(32)
    state = _state_signer().dumps(
        {"redirect_uri": redirect_uri, "p": provider_name, "v": code_verifier}
    )
    return await provider.authorize_url(state, redirect_uri, code_verifier)


async def oauth_finish(
    conn: asyncpg.Connection,
    provider_name: str,
    code: str,
    state: str,
    *,
    ip: str | None = None,
    ua: str | None = None,
) -> tuple[UserResponse, str, str, int, str]:
    """Exchange an OAuth code for our own token pair.

    Returns (user, access_token, refresh_token, ttl, redirect_uri) where
    redirect_uri was embedded in the signed state at authorize time.
    """
    from ..secretset import load_verification_secrets
    from .providers.registry import get_provider

    secrets_list = load_verification_secrets("oauth_state")
    if not secrets_list:
        legacy = get_settings().oauth_state_secret
        if legacy is None:
            raise RuntimeError(
                "no OAuth state secret configured; run "
                "`supython secret rotate oauth` or set OAUTH_STATE_SECRET"
            )
        secrets_list = [(legacy, None)]

    state_data: dict | None = None
    last_error: Exception | None = None
    for value, _kid in secrets_list:
        signer = URLSafeTimedSerializer(value)
        try:
            state_data = signer.loads(state, max_age=_OAUTH_STATE_MAX_AGE)
            break
        except BadSignature as exc:
            last_error = exc
            continue
    if state_data is None:
        raise AuthError(
            "invalid_state", "OAuth state is invalid or expired", 400
        ) from last_error

    redirect_uri: str = state_data.get("redirect_uri", "")
    code_verifier: str | None = state_data.get("v")

    try:
        provider = get_provider(provider_name)
    except KeyError as exc:
        raise AuthError("unknown_provider", str(exc), 400) from exc

    try:
        profile = await provider.exchange(code, redirect_uri, code_verifier)
    except Exception as exc:
        logger.warning("OAuth exchange failed for %s: %s", provider_name, exc)
        raise AuthError("oauth_exchange_failed", "Provider exchange failed", 400) from exc

    if not profile.email:
        raise AuthError(
            "no_email",
            "The OAuth provider did not return an email address. "
            "Make sure your account has a public primary email set.",
            400,
        )

    identity_row = await conn.fetchrow(
        """
        select i.user_id, u.email, u.created_at
        from auth.identities i
        join auth.users u on u.id = i.user_id
        where i.provider = $1 and i.provider_user_id = $2
        """,
        provider_name,
        profile.provider_user_id,
    )

    if identity_row:
        user = UserResponse(
            id=identity_row["user_id"],
            email=identity_row["email"],
            created_at=identity_row["created_at"],
        )
        await conn.execute(
            "update auth.users set last_sign_in_at = now() where id = $1",
            user.id,
        )
    else:
        async with conn.transaction():
            user_row = await conn.fetchrow(
                "select id, email, created_at from auth.users where email = $1",
                profile.email,
            )
            if not user_row:
                user_row = await conn.fetchrow(
                    """
                    insert into auth.users (email, email_confirmed_at)
                    values ($1, now())
                    returning id, email, created_at
                    """,
                    profile.email,
                )
            user = _row_to_user(user_row)
            identity_id = await conn.fetchval(
                """
                insert into auth.identities
                    (user_id, provider, provider_user_id, identity_data)
                values ($1, $2, $3, $4::jsonb)
                on conflict (provider, provider_user_id) do nothing
                returning id
                """,
                user.id,
                provider_name,
                profile.provider_user_id,
                json.dumps(profile.raw),
            )
            if identity_id is not None:
                await _audit_log(
                    conn, user.id, "oauth_identity_linked",
                    ip=ip, ua=ua,
                    payload={
                        "provider": provider_name,
                        "provider_user_id": profile.provider_user_id,
                    },
                )

    # A successful OAuth exchange proves control of the external account, so it
    # activates the user inline (no-op if already active). This also lets a
    # consumer's pre-created invite row, matched here by email, come online via
    # its first OAuth sign-in.
    await conn.execute(
        "update auth.users set activated_at = now() where id = $1 and activated_at is null",
        user.id,
    )
    access, refresh, ttl = await _issue_pair(conn, user)
    return user, access, refresh, ttl, redirect_uri
