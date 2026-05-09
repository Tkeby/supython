"""Tests for JWT key material loading and JWKS derivation."""

import hashlib
import json
from base64 import urlsafe_b64encode

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.utils import to_base64url_uint

from supython import settings
from supython.jwks import (
    _MIN_RSA_BITS,
    clear_cache,
    dump_jwks,
    generate_private_key,
    jwks_for_signing_key,
    load_signing_key,
    load_verification_keyset,
    private_key_to_pem,
    signing_key_from_private_key,
    write_current_jwks,
    write_jwks_file,
)


def _rsa_pem(bits: int = 2048) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _ec_pem(curve: ec.EllipticCurve | None = None) -> bytes:
    key = ec.generate_private_key(curve or ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _thumbprint_rsa(key) -> str:
    numbers = key.public_key().public_numbers()
    members = {
        "e": to_base64url_uint(numbers.e).decode(),
        "kty": "RSA",
        "n": to_base64url_uint(numbers.n).decode(),
    }
    canonical = json.dumps(members, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode()


def _thumbprint_ec(key) -> str:
    numbers = key.public_key().public_numbers()
    members = {
        "crv": "P-256",
        "kty": "EC",
        "x": to_base64url_uint(numbers.x).decode(),
        "y": to_base64url_uint(numbers.y).decode(),
    }
    canonical = json.dumps(members, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode()


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_KEYSET_MANIFEST_PATH", str(tmp_path / "keyset.json"))
    monkeypatch.setenv("JWT_KEYS_DIR", str(tmp_path / "keys"))
    settings.get_settings.cache_clear()
    clear_cache()
    yield
    settings.get_settings.cache_clear()
    clear_cache()


class TestLoadSigningKey:

    def test_loads_rsa_pem_from_inline_env(self, monkeypatch):
        pem = _rsa_pem()
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())
        sk = load_signing_key()
        assert sk.alg == "RS256"
        assert isinstance(sk.key, rsa.RSAPrivateKey)
        assert sk.key.key_size >= _MIN_RSA_BITS
        assert len(sk.kid) == 43  # base64url(SHA-256) = 43 chars

    def test_loads_rsa_pem_from_file_path(self, monkeypatch, tmp_path):
        pem = _rsa_pem()
        key_file = tmp_path / "jwt_private.pem"
        key_file.write_bytes(pem)
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(key_file))
        sk = load_signing_key()
        assert sk.alg == "RS256"
        assert isinstance(sk.key, rsa.RSAPrivateKey)
        assert len(sk.kid) == 43

    def test_loads_ec_p256_for_es256(self, monkeypatch):
        pem = _ec_pem()
        monkeypatch.setenv("JWT_ALG", "ES256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())
        sk = load_signing_key()
        assert sk.alg == "ES256"
        assert isinstance(sk.key, ec.EllipticCurvePrivateKey)
        assert isinstance(sk.key.curve, ec.SECP256R1)
        assert len(sk.kid) == 43

    def test_rejects_rsa_key_when_alg_is_es256(self, monkeypatch):
        pem = _rsa_pem()
        monkeypatch.setenv("JWT_ALG", "ES256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())
        with pytest.raises(ValueError, match="ES256 requires"):
            load_signing_key()

    def test_rejects_ec_key_when_alg_is_rs256(self, monkeypatch):
        pem = _ec_pem()
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())
        with pytest.raises(ValueError, match="RS256 requires"):
            load_signing_key()

    def test_rejects_short_rsa_key(self, monkeypatch):
        pem = _rsa_pem(bits=1024)
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())
        with pytest.raises(ValueError, match="2048"):
            load_signing_key()

    def test_explicit_kid_overrides_thumbprint(self, monkeypatch):
        pem = _rsa_pem()
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())
        monkeypatch.setenv("JWT_KID", "mykey-1")
        sk = load_signing_key()
        assert sk.kid == "mykey-1"

    def test_missing_key_material_raises(self, monkeypatch):
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", "")
        monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")
        with pytest.raises(RuntimeError, match="requires JWT_PRIVATE_KEY"):
            load_signing_key()

class TestKeyGeneration:

    @pytest.mark.parametrize(
        ("alg", "key_type"),
        [("RS256", rsa.RSAPrivateKey), ("ES256", ec.EllipticCurvePrivateKey)],
    )
    def test_generate_private_key_shape(self, alg, key_type):
        key = generate_private_key(alg)
        assert isinstance(key, key_type)
        pem = private_key_to_pem(key)
        assert pem.startswith(b"-----BEGIN PRIVATE KEY-----")

    def test_jwks_for_signing_key(self):
        key = generate_private_key("RS256")
        signer = signing_key_from_private_key(key, "RS256")
        doc = jwks_for_signing_key(signer)
        assert len(doc["keys"]) == 1
        jwk = doc["keys"][0]
        assert jwk["alg"] == "RS256"
        assert jwk["kid"] == signer.kid
        assert jwk["kty"] == "RSA"
        assert "d" not in jwk


class TestThumbprintDeterminism:

    def test_kid_is_deterministic_thumbprint(self, monkeypatch):
        pem = _rsa_pem()
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())

        sk1 = load_signing_key()
        clear_cache()
        sk2 = load_signing_key()
        assert sk1.kid == sk2.kid

        # Different PEM should yield different kid
        pem2 = _rsa_pem()
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem2.decode())
        settings.get_settings.cache_clear()
        clear_cache()
        sk3 = load_signing_key()
        assert sk3.kid != sk1.kid

        # Verify kid matches inline recomputation
        key = serialization.load_pem_private_key(pem, password=None)
        expected = _thumbprint_rsa(key)
        assert sk1.kid == expected

    def test_ec_kid_is_deterministic_thumbprint(self, monkeypatch):
        pem = _ec_pem()
        monkeypatch.setenv("JWT_ALG", "ES256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())

        sk1 = load_signing_key()
        clear_cache()
        sk2 = load_signing_key()
        assert sk1.kid == sk2.kid

        key = serialization.load_pem_private_key(pem, password=None)
        expected = _thumbprint_ec(key)
        assert sk1.kid == expected


class TestVerificationKeyset:

    def test_contains_rs256_kid_only(self, monkeypatch):
        pem = _rsa_pem()
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())
        keyset = load_verification_keyset()
        sk = load_signing_key()
        assert sk.kid in keyset
        assert keyset[sk.kid].algorithm_name == "RS256"
        assert len(keyset) == 1

    def test_keyset_dir_yields_all_kids(self, monkeypatch, tmp_path):
        from supython import keyset as keyset_mod

        keys_dir = tmp_path / "keys"
        manifest = tmp_path / "keyset.json"
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_KEYS_DIR", str(keys_dir))
        monkeypatch.setenv("JWT_KEYSET_MANIFEST_PATH", str(manifest))
        monkeypatch.setenv("JWT_KID", "")
        monkeypatch.setenv("JWT_PRIVATE_KEY", "")
        monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")
        settings.get_settings.cache_clear()
        clear_cache()

        first = keyset_mod.add_key("RS256")
        second = keyset_mod.add_key("RS256")

        clear_cache()
        keyset = load_verification_keyset()

        assert {first.kid, second.kid} <= set(keyset)
        assert keyset[first.kid].algorithm_name == "RS256"
        assert keyset[second.kid].algorithm_name == "RS256"


class TestDumpJwks:

    def test_dump_jwks_omits_private_components(self, monkeypatch):
        pem = _rsa_pem()
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())
        keyset = load_verification_keyset()
        jwks_doc = dump_jwks(keyset)
        for key in jwks_doc["keys"]:
            for private_member in {"d", "p", "q", "dp", "dq", "qi"}:
                assert private_member not in key

    def test_write_current_jwks(self, monkeypatch, tmp_path):
        pem = _rsa_pem()
        out = tmp_path / "nested" / "jwks.json"
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())

        jwks_doc = write_current_jwks(out)

        assert json.loads(out.read_text()) == jwks_doc
        assert len(jwks_doc["keys"]) == 1
        assert not (tmp_path / "nested" / "jwks.json.tmp").exists()

    def test_write_jwks_file_overwrites_atomically(self, tmp_path):
        out = tmp_path / "jwks.json"
        write_jwks_file(out, {"keys": []})
        write_jwks_file(out, {"keys": [{"kid": "new"}]})
        assert json.loads(out.read_text()) == {"keys": [{"kid": "new"}]}

    def test_dump_jwks_rs256_shape(self, monkeypatch):
        pem = _rsa_pem()
        monkeypatch.setenv("JWT_ALG", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())
        sk = load_signing_key()
        keyset = load_verification_keyset()
        jwks_doc = dump_jwks(keyset)
        assert len(jwks_doc["keys"]) == 1
        key = jwks_doc["keys"][0]
        assert key["kty"] == "RSA"
        assert key["alg"] == "RS256"
        assert key["kid"] == sk.kid
        assert key["use"] == "sig"
        assert "n" in key
        assert "e" in key

    def test_dump_jwks_es256_shape(self, monkeypatch):
        pem = _ec_pem()
        monkeypatch.setenv("JWT_ALG", "ES256")
        monkeypatch.setenv("JWT_PRIVATE_KEY", pem.decode())
        sk = load_signing_key()
        keyset = load_verification_keyset()
        jwks_doc = dump_jwks(keyset)
        assert len(jwks_doc["keys"]) == 1
        key = jwks_doc["keys"][0]
        assert key["kty"] == "EC"
        assert key["alg"] == "ES256"
        assert key["kid"] == sk.kid
        assert key["use"] == "sig"
        assert "x" in key
        assert "y" in key
        assert key["crv"] == "P-256"
