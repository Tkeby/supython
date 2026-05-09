"""HMAC sign/verify for storage signed URLs.

Signed URLs are minted by supython itself (not S3 presigned URLs). This keeps
the URL shape identical for the local and S3 backends and lets RLS gate the
*sign* step — the bytes step is then a stateless signature check.

The signing secret (``storage_signed_url_secret``) is intentionally distinct
from the JWT private key: rotating one must not invalidate the other.
"""

from datetime import UTC, datetime, timedelta
from functools import lru_cache

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from ..settings import get_settings


class SignatureError(Exception):
    """Base class for signed-URL verification failures."""

    code: str = "invalid_signature"


class InvalidSignature(SignatureError):
    code = "invalid_signature"


class ExpiredSignature(SignatureError):
    code = "signature_expired"


_SALT = "supython.storage.signed-url"


def _signer_for(secret_value: str) -> TimestampSigner:
    return TimestampSigner(secret_value, salt=_SALT)


def _active_signer() -> TimestampSigner:
    from ..secretset import load_signing_secret

    manifest_secret = load_signing_secret("storage_signed_url")
    if manifest_secret is not None:
        return _signer_for(manifest_secret)
    legacy = get_settings().storage_signed_url_secret
    if legacy is None:
        raise RuntimeError(
            "no storage signed-url secret configured; run "
            "`supython secret rotate storage` or set STORAGE_SIGNED_URL_SECRET"
        )
    return _signer_for(legacy)


def _payload(bucket: str, path: str, ttl: int) -> str:
    return f"{bucket}/{path}|{ttl}"


def sign(bucket: str, path: str, ttl: int) -> tuple[str, datetime]:
    """Return ``(token, expires_at)`` for a (bucket, path) and TTL in seconds."""
    if ttl <= 0:
        raise InvalidSignature("ttl must be positive")
    token = _active_signer().sign(_payload(bucket, path, ttl)).decode("utf-8")
    expires_at = datetime.now(tz=UTC) + timedelta(seconds=ttl)
    return token, expires_at


def verify(token: str, bucket: str, path: str) -> None:
    """Raise ``SignatureError`` when ``token`` is bad, tampered, or expired.

    The TTL is read out of the signed payload itself, so the signer is the
    source of truth for how long a URL is valid for.
    """
    from ..secretset import load_verification_secrets

    secrets_list = load_verification_secrets("storage_signed_url")
    if not secrets_list:
        legacy = get_settings().storage_signed_url_secret
        if legacy is None:
            raise RuntimeError(
                "no storage signed-url secret configured; run "
                "`supython secret rotate storage` or set STORAGE_SIGNED_URL_SECRET"
            )
        secrets_list = [(legacy, None)]

    last_error: Exception | None = None
    for value, _kid in secrets_list:
        signer = _signer_for(value)
        try:
            raw = signer.unsign(token).decode("utf-8")

            expected_prefix = f"{bucket}/{path}|"
            if not raw.startswith(expected_prefix):
                raise InvalidSignature("signed payload does not match (bucket, path)")
            try:
                ttl = int(raw[len(expected_prefix) :])
            except ValueError as exc:
                raise InvalidSignature("signed payload is malformed") from exc
            if ttl <= 0:
                raise InvalidSignature("signed payload has non-positive ttl")

            try:
                signer.unsign(token, max_age=ttl)
            except SignatureExpired as exc:
                raise ExpiredSignature(str(exc)) from exc
            except BadSignature as exc:
                raise InvalidSignature(str(exc)) from exc
            return  # success
        except (BadSignature, SignatureExpired) as exc:
            last_error = exc
            continue
    raise InvalidSignature(str(last_error)) from last_error


def reset_signer_cache() -> None:
    """Clear the cached signer; tests use this after overriding the secret."""
    from ..secretset import clear_cache

    clear_cache()
