"""Token issuance & verification contract tests.

Phase 2+: multi-key, kid-routed verification with algorithm pinning.
Tests run under RS256 and ES256.
"""

import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import jwt.algorithms
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from supython import jwks
from supython.settings import get_settings
from supython.tokens import decode_access_token, issue_access_token
from tests._keys import (
    make_alg_confusion_token,
    make_expired_token,
    make_token,
    make_token_with_alg,
    make_wrong_key_token,
)


class TestRoundTrip:

    def test_round_trip_preserves_claims(self):
        uid = uuid.uuid4()
        tok, ttl = issue_access_token(uid, "alice@test.com")
        claims = decode_access_token(tok)
        assert claims["sub"] == str(uid)
        assert claims["email"] == "alice@test.com"
        assert claims["role"] == "authenticated"
        assert claims["aud"] == get_settings().jwt_aud
        assert "jti" in claims
        assert claims["jti"]

    def test_ttl_returned(self):
        _, ttl = issue_access_token(uuid.uuid4(), "x@test.com")
        assert ttl > 0

    def test_exp_is_in_the_future(self):
        tok, _ = issue_access_token(uuid.uuid4(), "x@test.com")
        claims = decode_access_token(tok)
        assert claims["exp"] > time.time()

    def test_extra_claims_round_trip(self):
        uid = uuid.uuid4()
        tok, _ = issue_access_token(uid, "x@test.com", extra_claims={"kid": "key-1"})
        claims = decode_access_token(tok)
        assert claims["kid"] == "key-1"


class TestAlgorithmAllowList:

    def test_decode_rejects_unsupported_alg_hs512(self):
        # Sign under the real signer kid so the kid lookup succeeds and
        # the decoder actually reaches PyJWT's algorithms=[...] check —
        # otherwise we'd be testing the kid path, not the alg allow-list.
        signer = jwks.load_signing_key()
        tok = make_token_with_alg("HS512", kid=signer.kid)
        with pytest.raises(jwt.InvalidAlgorithmError):
            decode_access_token(tok)

    def test_decode_rejects_none_alg(self):
        signer = jwks.load_signing_key()
        tok = make_token_with_alg("none", kid=signer.kid)
        with pytest.raises(jwt.InvalidAlgorithmError):
            decode_access_token(tok)

    def test_decode_rejects_wrong_key(self):
        tok = make_wrong_key_token()
        with pytest.raises(jwt.InvalidKeyError):
            decode_access_token(tok)


@pytest.mark.parametrize("with_alg", ["RS256", "ES256"], indirect=True)
class TestRoundTripPerAlg:

    def test_round_trip(self, with_alg):
        uid = uuid.uuid4()
        tok, _ = issue_access_token(uid, f"alice-{with_alg}@test.com")
        claims = decode_access_token(tok)
        assert claims["sub"] == str(uid)
        assert claims["email"] == f"alice-{with_alg}@test.com"
        assert claims["role"] == "authenticated"

    def test_issued_token_has_kid_and_typ_headers(self, with_alg):
        tok, _ = issue_access_token(uuid.uuid4(), "x@test.com")
        header = jwt.get_unverified_header(tok)
        assert header["kid"]
        assert header["typ"] == "JWT"
        assert header["alg"] == with_alg


class TestKidRouting:

    def test_decode_rejects_token_with_unknown_kid(self):
        s = get_settings()
        signer = jwks.load_signing_key()
        payload = {
            "sub": str(uuid.uuid4()),
            "role": "authenticated",
            "aud": s.jwt_aud,
            "iat": 1,
            "exp": 9_999_999_999,
        }
        tok = jwt.encode(
            payload, signer.key, algorithm=s.jwt_alg,
            headers={"kid": "does-not-exist", "alg": s.jwt_alg, "typ": "JWT"},
        )
        with pytest.raises(jwt.InvalidKeyError):
            decode_access_token(tok)

    def test_decode_rejects_token_without_kid(self):
        s = get_settings()
        signer = jwks.load_signing_key()
        payload = {
            "sub": str(uuid.uuid4()),
            "role": "authenticated",
            "aud": s.jwt_aud,
            "iat": 1,
            "exp": 9_999_999_999,
        }
        tok = jwt.encode(
            payload, signer.key, algorithm=s.jwt_alg,
            headers={"typ": "JWT"},  # no kid
        )
        with pytest.raises(jwt.InvalidKeyError):
            decode_access_token(tok)

    def test_decode_accepts_token_signed_under_old_kid_during_rotation(self, monkeypatch):
        from unittest.mock import patch

        from jwt import PyJWK

        s = get_settings()
        signer = jwks.load_signing_key()

        alt_key_pem = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        alt_kid = "old-kid-a"
        alt_jwk_str = jwt.algorithms.RSAAlgorithm.to_jwk(alt_key_pem.public_key())
        import json
        alt_jwk = json.loads(alt_jwk_str) if isinstance(alt_jwk_str, str) else alt_jwk_str
        alt_jwk.update({"use": "sig", "alg": "RS256", "kid": alt_kid})
        alt_pyjwk = PyJWK(alt_jwk, algorithm="RS256")

        fake_keyset = {**jwks.load_verification_keyset(), alt_kid: alt_pyjwk}

        payload = {
            "sub": str(uuid.uuid4()),
            "role": "authenticated",
            "aud": s.jwt_aud,
            "iat": 1,
            "exp": 9_999_999_999,
        }
        tok = jwt.encode(
            payload, alt_key_pem, algorithm="RS256",
            headers={"kid": alt_kid, "alg": "RS256", "typ": "JWT"},
        )

        with patch("supython.jwks.load_verification_keyset", return_value=fake_keyset):
            claims = decode_access_token(tok)
        assert claims["role"] == "authenticated"


class TestSecurityInvariants:

    def test_decode_rejects_alg_confusion_attack(self, rsa_key_pem_session, monkeypatch):
        from supython import settings
        from cryptography.hazmat.primitives import serialization

        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", rsa_key_pem_session.decode())
        settings.get_settings.cache_clear()
        jwks.clear_cache()
        try:
            signer = jwks.load_signing_key()
            public_pem = signer.key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            forged = make_alg_confusion_token(public_pem)
            with pytest.raises(jwt.InvalidAlgorithmError):
                decode_access_token(forged)
        finally:
            monkeypatch.delenv("JWT_ALG", raising=False)
            monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)
            settings.get_settings.cache_clear()
            jwks.clear_cache()

    def test_decode_rejects_alg_none(self):
        tok = make_token_with_alg("none")
        with pytest.raises(jwt.InvalidAlgorithmError):
            decode_access_token(tok)

    @pytest.mark.parametrize("missing_claim", ["exp", "iat", "aud", "role"])
    def test_decode_rejects_missing_required_claim(self, missing_claim):
        s = get_settings()
        signer = jwks.load_signing_key()
        payload = {
            "sub": str(uuid.uuid4()),
            "email": "missing@test.com",
            "role": "authenticated",
            "aud": s.jwt_aud,
            "iat": 1,
            "exp": 9_999_999_999,
        }
        del payload[missing_claim]
        tok = jwt.encode(
            payload, signer.key, algorithm=s.jwt_alg,
            headers={"kid": signer.kid, "alg": s.jwt_alg, "typ": "JWT"},
        )
        with pytest.raises(jwt.MissingRequiredClaimError):
            decode_access_token(tok)

    def test_decode_tolerates_small_clock_skew(self):
        import time as _time
        s = get_settings()
        signer = jwks.load_signing_key()
        now = int(_time.time())
        payload = {
            "sub": str(uuid.uuid4()),
            "email": "skew@test.com",
            "role": "authenticated",
            "aud": s.jwt_aud,
            "iat": now - 15,
            "exp": now - 10,
        }
        tok = jwt.encode(
            payload, signer.key, algorithm=s.jwt_alg,
            headers={"kid": signer.kid, "alg": s.jwt_alg, "typ": "JWT"},
        )
        claims = decode_access_token(tok)
        assert claims["sub"]

    def test_decode_rejects_large_clock_skew(self):
        import time as _time
        s = get_settings()
        signer = jwks.load_signing_key()
        now = int(_time.time())
        payload = {
            "sub": str(uuid.uuid4()),
            "email": "skew-big@test.com",
            "role": "authenticated",
            "aud": s.jwt_aud,
            "iat": now - 120,
            "exp": now - 60,
        }
        tok = jwt.encode(
            payload, signer.key, algorithm=s.jwt_alg,
            headers={"kid": signer.kid, "alg": s.jwt_alg, "typ": "JWT"},
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(tok)


class TestSecurityInvariants:

    def test_decode_rejects_any_hs256_token(self):
        signer = jwks.load_signing_key()
        # Even pretending to be the legacy kid from v0.5 must fail now.
        for kid in ("hs256-legacy", signer.kid, "whatever"):
            forged = make_token_with_alg("HS256", kid=kid)
            with pytest.raises((jwt.InvalidKeyError, jwt.InvalidAlgorithmError)):
                decode_access_token(forged)


class TestRotation:
    """Phase 6: zero-downtime key rotation across multiple kids."""

    @pytest.fixture
    def rotation_env(self, monkeypatch, tmp_path):
        from supython import keyset, settings

        keys_dir = tmp_path / "keys"
        manifest = tmp_path / "keyset.json"
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_KEYS_DIR", str(keys_dir))
        monkeypatch.setenv("JWT_KEYSET_MANIFEST_PATH", str(manifest))
        monkeypatch.setenv("JWT_KID", "")
        monkeypatch.setenv("JWT_PRIVATE_KEY", "")
        monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")
        settings.get_settings.cache_clear()
        jwks.clear_cache()
        yield keyset
        settings.get_settings.cache_clear()
        jwks.clear_cache()

    @staticmethod
    def _sign_under_kid(entry, alg: str = "RS256") -> str:
        s = get_settings()
        key = serialization.load_pem_private_key(
            entry.pem_path.read_bytes(), password=None
        )
        payload = {
            "sub": str(uuid.uuid4()),
            "email": "rotate@test.com",
            "role": "authenticated",
            "aud": s.jwt_aud,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        }
        return jwt.encode(
            payload,
            key,
            algorithm=alg,
            headers={"kid": entry.kid, "alg": alg, "typ": "JWT"},
        )

    def test_rotation_two_active_kids_both_verify(self, rotation_env):
        keyset = rotation_env

        kid_a = keyset.add_key("RS256")
        kid_b = keyset.add_key("RS256", status="verifying")

        jwks.clear_cache()
        verification = jwks.load_verification_keyset()
        assert {kid_a.kid, kid_b.kid} <= set(verification)

        tok_a = self._sign_under_kid(kid_a)
        tok_b = self._sign_under_kid(kid_b)

        claims_a = decode_access_token(tok_a)
        claims_b = decode_access_token(tok_b)
        assert claims_a["role"] == "authenticated"
        assert claims_b["role"] == "authenticated"

    def test_rotation_old_kid_removed_after_grace_window(
        self, rotation_env, monkeypatch
    ):
        keyset = rotation_env
        from supython import settings

        monkeypatch.setenv("JWT_ROTATION_GRACE_SECONDS", "100")
        settings.get_settings.cache_clear()

        fake_now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        monkeypatch.setattr("supython.keyset._now", lambda: fake_now[0])

        kid_a = keyset.add_key("RS256")
        kid_b = keyset.add_key("RS256", status="verifying")

        fake_now[0] = fake_now[0] + timedelta(seconds=30)
        keyset.activate(kid_b.kid)

        jwks.clear_cache()
        mid = jwks.load_verification_keyset()
        assert {kid_a.kid, kid_b.kid} <= set(mid)

        fake_now[0] = fake_now[0] + timedelta(seconds=200)
        removed = keyset.prune()
        assert removed == [kid_a.kid]

        jwks.clear_cache()
        post = jwks.load_verification_keyset()
        assert kid_a.kid not in post
        assert kid_b.kid in post
