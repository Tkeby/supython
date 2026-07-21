from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

# Per-field input caps. The body-size middleware already rejects absurdly
# large payloads, but per-field caps give the user a precise 422 instead
# of a generic 413 and stop unbounded values from reaching argon2 / the
# DB. RFC 5321 caps email at 254; argon2id is happy with arbitrary
# password lengths but slow on huge ones, so we mirror what the underlying
# password column / hash assumes.
MAX_EMAIL_LEN = 254
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128
# Refresh tokens / one-time tokens are short opaque strings (under 100
# chars in practice). 4096 keeps a generous head-room for any future
# encoding while still rejecting "1 MB token" abuse.
MAX_TOKEN_LEN = 4096
# Redirect URLs are ordinary web URLs; 2048 is the de-facto browser cap.
MAX_REDIRECT_URL_LEN = 2048

EmailField = Annotated[EmailStr, Field(max_length=MAX_EMAIL_LEN)]
PasswordField = Annotated[
    str, Field(min_length=MIN_PASSWORD_LEN, max_length=MAX_PASSWORD_LEN)
]
TokenField = Annotated[str, Field(min_length=1, max_length=MAX_TOKEN_LEN)]


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    created_at: datetime


class SignUpRequest(BaseModel):
    email: EmailField
    password: PasswordField
    # Only meaningful when AUTH_REQUIRE_EMAIL_CONFIRMATION is on: where
    # /auth/v1/confirm/verify should 302 the browser after confirming, tokens
    # in the fragment (same contract as the magic-link redirect_url, validated
    # against the same MAGIC_LINK_REDIRECT_ALLOWLIST). Omit for the JSON flow.
    redirect_url: Annotated[
        str | None, Field(default=None, max_length=MAX_REDIRECT_URL_LEN)
    ] = None


class SignUpPendingResponse(BaseModel):
    """202 body when signup requires email confirmation: no tokens yet."""

    user: UserResponse
    confirmation_sent_at: datetime


class TokenRequest(BaseModel):
    email: EmailField
    # Login deliberately does not enforce ``min_length``: an old account
    # may predate the current minimum. The max cap still applies so we
    # don't argon2-hash megabyte payloads.
    password: Annotated[str, Field(max_length=MAX_PASSWORD_LEN)]


class RefreshRequest(BaseModel):
    refresh_token: TokenField


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
    user: UserResponse


class RecoverRequest(BaseModel):
    email: EmailField


class RecoverVerifyRequest(BaseModel):
    email: EmailField
    token: TokenField
    password: PasswordField


class MagicLinkRequest(BaseModel):
    email: EmailField
    # Where /auth/v1/magiclink/verify should send the browser after issuing
    # tokens: a 302 to this URL with the token pair in the fragment (as OAuth
    # does), instead of a JSON response. Must match MAGIC_LINK_REDIRECT_
    # ALLOWLIST or the request is rejected 400. Omit for the JSON flow.
    redirect_url: Annotated[
        str | None, Field(default=None, max_length=MAX_REDIRECT_URL_LEN)
    ] = None
    # Per-request token lifetime in seconds, clamped to [60, MAGIC_LINK_MAX_TTL].
    # Omit to use MAGIC_LINK_TOKEN_TTL. Lets a caller mint a longer-lived link
    # (e.g. an operator invite) without changing the global default.
    ttl: Annotated[int | None, Field(default=None, ge=1)] = None


class ConfirmResendRequest(BaseModel):
    email: EmailField
    redirect_url: Annotated[
        str | None, Field(default=None, max_length=MAX_REDIRECT_URL_LEN)
    ] = None


class OtpRequest(BaseModel):
    email: EmailField


class OtpVerifyRequest(BaseModel):
    email: EmailField
    token: TokenField
