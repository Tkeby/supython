"""Shared fixtures for the supython test suite.

The suite is split in two:

- `tests/unit/`        — pure-Python tests; no Docker, no Postgres.
- `tests/integration/` — exercise the full stack against the dedicated
                         test database (`supython test up`).

Anything DB-bound lives in `tests/integration/conftest.py` so unit tests
never depend on a running Postgres. Helpers below are usable by both
trees: cryptographic key fixtures (used by JWT round-trip tests in
either tree) and the in-memory mailer (used by integration auth tests).
"""

import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa


# ---------------------------------------------------------------------------
# Default JWT signing key for the test session.
#
# Set at conftest import time (before any fixture or test) so that any
# code that constructs ``Settings()`` early — e.g. integration session
# fixtures that build the FastAPI app — sees a usable JWT_PRIVATE_KEY.
# We don't depend on the dogfooded ``dev-app/.supython/jwt_private.pem``
# because tests must be hermetic; if a real key is already configured
# in the environment, we leave it alone.
# ---------------------------------------------------------------------------
if not os.environ.get("JWT_PRIVATE_KEY") and not os.environ.get("JWT_PRIVATE_KEY_PATH"):
    _bootstrap_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    os.environ["JWT_PRIVATE_KEY"] = _bootstrap_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    del _bootstrap_key


from supython.mailer import EmailMessage  # noqa: E402


class CapturingBackend:
    """In-memory email backend that stores sent messages for test assertions."""

    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def send(self, msg: EmailMessage) -> None:
        self.messages.append(msg)


@pytest.fixture
def capturing_mailer() -> CapturingBackend:
    """Email backend that captures messages in memory for inspection."""
    return CapturingBackend()


# ---------------------------------------------------------------------------
# JWT algorithm test fixtures (Phase 2)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_key_pem_session() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.fixture(scope="session")
def ec_p256_pem_session() -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.fixture
def with_alg(request, monkeypatch, tmp_path, rsa_key_pem_session, ec_p256_pem_session):
    from supython import jwks, settings

    alg = request.param
    monkeypatch.setenv("JWT_ALG", alg)
    if alg == "RS256":
        monkeypatch.setenv("JWT_PRIVATE_KEY", rsa_key_pem_session.decode())
    elif alg == "ES256":
        monkeypatch.setenv("JWT_PRIVATE_KEY", ec_p256_pem_session.decode())
    else:
        raise ValueError(f"with_alg only supports RS256/ES256, got {alg!r}")
    # Shut out any on-disk keyset manifest / dev keys so the JWT_PRIVATE_KEY
    # we just installed is what jwks.load_signing_key() actually consumes.
    # Without this, ./.supython/keyset.json (left by `supython keygen`) takes
    # precedence and the test silently signs with the wrong key/alg.
    monkeypatch.setenv("JWT_KEYSET_MANIFEST_PATH", str(tmp_path / "no-manifest.json"))
    monkeypatch.setenv("JWT_KEYS_DIR", str(tmp_path / "no-keys"))
    monkeypatch.setenv("JWT_KID", "")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")
    settings.get_settings.cache_clear()
    jwks.clear_cache()
    yield alg
    settings.get_settings.cache_clear()
    jwks.clear_cache()
