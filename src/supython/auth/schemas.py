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


class OtpRequest(BaseModel):
    email: EmailField


class OtpVerifyRequest(BaseModel):
    email: EmailField
    token: TokenField
