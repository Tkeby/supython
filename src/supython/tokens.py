"""JWT issuance & verification.

PostgREST verifies tokens using the same public JWKS this module emits
(see supython.jwks). All tokens are RS256 or ES256; the symmetric
fallback was removed in v0.6.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from . import jwks
from .settings import get_settings

logger = logging.getLogger(__name__)

_LEEWAY_SECONDS = 30
_REQUIRED_CLAIMS = ["exp", "iat", "aud", "role"]


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def issue_access_token(
    user_id: uuid.UUID,
    email: str,
    role: str = "authenticated",
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, int]:
    s = get_settings()
    iat = _now()
    exp = iat + timedelta(seconds=s.access_token_ttl)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "aud": s.jwt_aud,
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra_claims:
        payload.update(extra_claims)

    signer = jwks.load_signing_key()
    # Use signer.alg (the algorithm of the actual signing key) rather than
    # s.jwt_alg (the env preference). During rotation or when a keyset
    # manifest pins a different alg than the env, these can disagree and
    # the resulting token would have an `alg` header that contradicts the
    # key it was signed with — making it unverifiable under its own kid.
    headers = {"kid": signer.kid, "alg": signer.alg, "typ": "JWT"}
    token = jwt.encode(payload, signer.key, algorithm=signer.alg, headers=headers)
    return token, s.access_token_ttl


def issue_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def decode_access_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        unverified = jwt.get_unverified_header(token)
    except jwt.DecodeError as exc:
        raise jwt.InvalidTokenError(f"malformed token header: {exc}") from exc

    kid = unverified.get("kid")
    keyset = jwks.load_verification_keyset()
    if kid is None or kid not in keyset:
        raise jwt.InvalidKeyError(f"unknown kid: {kid!r}")

    pyjwk = keyset[kid]
    return jwt.decode(
        token,
        pyjwk.key,
        algorithms=[pyjwk.algorithm_name],
        audience=s.jwt_aud,
        leeway=_LEEWAY_SECONDS,
        options={"require": _REQUIRED_CLAIMS},
    )
