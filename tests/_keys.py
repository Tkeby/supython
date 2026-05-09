"""Centralised JWT helpers for tests.

All test-side token forging goes through this module so that
jwt.encode calls are not scattered across the suite.
"""

import uuid
from functools import lru_cache

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from supython import jwks
from supython.settings import get_settings
from supython.tokens import issue_access_token

_TEST_HS256_SECRET = b"phase5-forgery-secret-at-least-32-bytes!!"
_FORGED_HS256_KID = "forged-hs256"


def make_token(
    *,
    role: str = "authenticated",
    user_id: uuid.UUID | None = None,
    email: str | None = None,
    extra_claims: dict | None = None,
) -> str:
    uid = user_id or uuid.uuid4()
    tok, _ = issue_access_token(uid, email or f"user-{uid}@test.com", role, extra_claims=extra_claims)
    return tok


def make_expired_token() -> str:
    s = get_settings()
    signer = jwks.load_signing_key()
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "expired@test.com",
        "role": "authenticated",
        "aud": s.jwt_aud,
        "iat": 1,
        "exp": 1,
        "jti": uuid.uuid4().hex,
    }
    headers = {"kid": signer.kid, "alg": s.jwt_alg, "typ": "JWT"}
    return jwt.encode(payload, signer.key, algorithm=s.jwt_alg, headers=headers)


@lru_cache(maxsize=1)
def _alternate_rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_wrong_key_token() -> str:
    key = _alternate_rsa_key()
    payload = {
        "sub": str(uuid.uuid4()),
        "role": "authenticated",
        "aud": "authenticated",
        "iat": 1,
        "exp": 9_999_999_999,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(
        payload, key, algorithm="RS256",
        headers={"kid": "alien-key", "alg": "RS256", "typ": "JWT"},
    )


def make_token_with_alg(
    alg: str,
    secret_or_key: bytes | str | None = ...,
    *,
    kid: str | None = None,
) -> str:
    s = get_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "forged@test.com",
        "role": "authenticated",
        "aud": s.jwt_aud,
        "iat": 1,
        "exp": 9_999_999_999,
    }
    if secret_or_key is ...:
        key = None if alg == "none" else _TEST_HS256_SECRET
    else:
        key = secret_or_key
    hdr_kid = kid if kid is not None else _FORGED_HS256_KID
    return jwt.encode(
        payload, key, algorithm=alg,
        headers={"kid": hdr_kid, "alg": alg, "typ": "JWT"},
    )


def make_alg_confusion_token(public_key_pem: bytes) -> str:
    s = get_settings()
    signer = jwks.load_signing_key()
    public_key = serialization.load_pem_public_key(public_key_pem)
    public_key_der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "confused@test.com",
        "role": "authenticated",
        "aud": s.jwt_aud,
        "iat": 1,
        "exp": 9_999_999_999,
    }
    return jwt.encode(
        payload, public_key_der, algorithm="HS256",
        headers={"kid": signer.kid, "alg": "HS256", "typ": "JWT"},
    )
