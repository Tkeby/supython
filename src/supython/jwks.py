"""JWT key material loader. No I/O happens until a loader is called."""

import functools
import hashlib
import json
import logging
import os
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt import PyJWK
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from jwt.utils import to_base64url_uint

from .settings import get_settings

logger = logging.getLogger(__name__)

_MIN_RSA_BITS = 2048

_PRIVATE_JWK_MEMBERS = frozenset({"d", "p", "q", "dp", "dq", "qi"})


@dataclass(frozen=True)
class SigningKey:
    alg: str
    kid: str
    key: Any


def _mtime(path: Path | None) -> float:
    return path.stat().st_mtime if path and path.exists() else 0.0


def _dir_signature(path: Path | None) -> tuple:
    if path is None or not path.exists() or not path.is_dir():
        return ()
    entries = sorted(p.name for p in path.iterdir() if p.suffix == ".pem")
    return tuple((name, (path / name).stat().st_mtime) for name in entries)


def _cache_key() -> tuple:
    s = get_settings()
    from . import keyset

    return (
        s.jwt_alg,
        s.jwt_kid,
        s.jwt_private_key,
        _mtime(s.jwt_private_key_path),
        _mtime(s.jwt_keyset_manifest_path),
        _dir_signature(keyset.keys_dir()),
    )


def _thumbprint_kid(members: dict[str, str]) -> str:
    canonical = json.dumps(members, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode()


def _derive_kid(key: Any, alg: str) -> str:
    if alg == "RS256":
        pub = key.public_key()
        numbers = pub.public_numbers()
        members = {
            "e": to_base64url_uint(numbers.e).decode(),
            "kty": "RSA",
            "n": to_base64url_uint(numbers.n).decode(),
        }
        return _thumbprint_kid(members)
    if alg == "ES256":
        pub = key.public_key()
        numbers = pub.public_numbers()
        members = {
            "crv": "P-256",
            "kty": "EC",
            "x": to_base64url_uint(numbers.x).decode(),
            "y": to_base64url_uint(numbers.y).decode(),
        }
        return _thumbprint_kid(members)
    raise ValueError(f"Unsupported algorithm for thumbprint: {alg}")


def _load_pem_bytes(s: Any) -> bytes:
    if s.jwt_private_key:
        return s.jwt_private_key.encode()
    if s.jwt_private_key_path and s.jwt_private_key_path.name:
        return s.jwt_private_key_path.read_bytes()
    raise RuntimeError(
        f"{s.jwt_alg} requires JWT_PRIVATE_KEY or JWT_PRIVATE_KEY_PATH to be set"
    )


def generate_private_key(alg: Literal["RS256", "ES256"]) -> Any:
    if alg == "RS256":
        return rsa.generate_private_key(public_exponent=65537, key_size=_MIN_RSA_BITS)
    if alg == "ES256":
        return ec.generate_private_key(ec.SECP256R1())
    raise ValueError(f"unsupported JWT algorithm for key generation: {alg}")


def private_key_to_pem(key: Any) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def signing_key_from_private_key(
    key: Any,
    alg: Literal["RS256", "ES256"],
    kid: str | None = None,
) -> SigningKey:
    if alg == "RS256":
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError(f"RS256 requires an RSA private key, got {type(key).__name__}")
        if key.key_size < _MIN_RSA_BITS:
            raise ValueError(
                f"RS256 requires RSA key size >= {_MIN_RSA_BITS} bits, got {key.key_size}"
            )
    elif alg == "ES256":
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError(f"ES256 requires an EC private key, got {type(key).__name__}")
        if not isinstance(key.curve, ec.SECP256R1):
            raise ValueError(f"ES256 requires SECP256R1 curve, got {key.curve.name}")
    else:
        raise ValueError(f"unsupported JWT algorithm for signing key: {alg}")

    return SigningKey(alg, kid if kid is not None else _derive_kid(key, alg), key)


def _load_signer_from_keyset_entry(entry: Any) -> SigningKey:
    pem = entry.pem_path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    return signing_key_from_private_key(key, entry.alg, entry.kid)


@functools.lru_cache(maxsize=1)
def load_signing_key() -> SigningKey:
    s = get_settings()
    from . import keyset

    if keyset.has_manifest():
        kid = keyset.active_kid()
        if kid is None:
            raise RuntimeError(
                f"keyset manifest at {keyset.manifest_path()} has no active kid; "
                "run `supython keygen activate <kid>`"
            )
        entry = keyset.get_entry(kid)
        if entry is None:
            raise RuntimeError(
                f"active kid {kid!r} not present in keyset manifest "
                f"{keyset.manifest_path()}"
            )
        return _load_signer_from_keyset_entry(entry)

    pem = _load_pem_bytes(s)
    key = serialization.load_pem_private_key(pem, password=None)
    return signing_key_from_private_key(key, s.jwt_alg, s.jwt_kid)


def derive_public_jwk(signing_key: SigningKey) -> dict[str, Any]:
    if signing_key.alg == "RS256":
        jwk_str = RSAAlgorithm.to_jwk(signing_key.key.public_key())
    elif signing_key.alg == "ES256":
        jwk_str = ECAlgorithm.to_jwk(signing_key.key.public_key())
    else:
        raise ValueError(
            f"derive_public_jwk does not apply to {signing_key.alg}"
        )
    jwk = json.loads(jwk_str) if isinstance(jwk_str, str) else jwk_str
    jwk = {k: v for k, v in jwk.items() if k not in _PRIVATE_JWK_MEMBERS}
    jwk.update({"use": "sig", "alg": signing_key.alg, "kid": signing_key.kid})
    return jwk


def jwks_for_signing_key(signing_key: SigningKey) -> dict[str, list[dict[str, Any]]]:
    return {"keys": [derive_public_jwk(signing_key)]}


def write_private_key_pem(path: Path, pem: bytes, *, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_TRUNC if force else os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
            fd = -1
    finally:
        if fd >= 0:
            os.close(fd)
    if os.name == "posix":
        path.chmod(0o600)


@functools.lru_cache(maxsize=1)
def load_verification_keyset() -> dict[str, PyJWK]:
    from . import keyset as keyset_mod

    out: dict[str, PyJWK] = {}
    if keyset_mod.has_manifest():
        for entry in keyset_mod.list_keys():
            sk = _load_signer_from_keyset_entry(entry)
            jwk = derive_public_jwk(sk)
            out[sk.kid] = PyJWK(jwk, algorithm=sk.alg)
        if out:
            return out

    sk = load_signing_key()
    jwk = derive_public_jwk(sk)
    out[sk.kid] = PyJWK(jwk, algorithm=sk.alg)
    return out


def dump_jwks(keyset: dict[str, PyJWK]) -> dict[str, list[dict[str, Any]]]:
    keys: list[dict[str, Any]] = []
    for kid, pyjwk in keyset.items():
        if pyjwk.algorithm_name == "RS256":
            jwk_str = RSAAlgorithm.to_jwk(pyjwk.key)
        elif pyjwk.algorithm_name == "ES256":
            jwk_str = ECAlgorithm.to_jwk(pyjwk.key)
        else:
            continue
        jwk = json.loads(jwk_str) if isinstance(jwk_str, str) else jwk_str
        jwk = {k: v for k, v in jwk.items() if k not in _PRIVATE_JWK_MEMBERS}
        jwk.update({"use": "sig", "alg": pyjwk.algorithm_name, "kid": kid})
        keys.append(jwk)
    return {"keys": keys}


def write_jwks_file(path: Path, jwks_doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(jwks_doc, sort_keys=True) + "\n")
    os.replace(tmp_path, path)


def write_current_jwks(path: Path | None = None) -> dict[str, Any]:
    s = get_settings()
    target = path if path is not None else s.jwt_jwks_path
    jwks_doc = dump_jwks(load_verification_keyset())
    write_jwks_file(target, jwks_doc)
    return jwks_doc


def clear_cache() -> None:
    load_signing_key.cache_clear()
    load_verification_keyset.cache_clear()
