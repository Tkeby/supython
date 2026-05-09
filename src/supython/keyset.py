"""JWT key rotation manifest.

Multi-kid keyset lifecycle: tracks per-kid PEM files in a directory
(``settings.jwt_keys_dir``, default ``./.supython/keys/``) governed by a
JSON manifest (``settings.jwt_keyset_manifest_path``, default
``./.supython/keyset.json``). The manifest is the source of truth for
the active signing kid; ``settings.jwt_kid`` (the ``JWT_KID`` env var)
remains as an explicit override for read-only-FS deployments.

When the manifest is absent, ``jwks.load_signing_key`` /
``load_verification_keyset`` continue to behave as in Phase 5 (single
key from ``JWT_PRIVATE_KEY_PATH`` / ``JWT_PRIVATE_KEY``). The first
``supython keygen rotate`` invocation calls
``import_legacy_single_key`` to seed the manifest from the legacy
single-key environment.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cryptography.hazmat.primitives import serialization

from . import jwks
from .settings import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_KEYS_DIR = Path("./.supython/keys")

KeyStatus = Literal["active", "verifying", "retired"]


@dataclass(frozen=True)
class KeyEntry:
    kid: str
    alg: str
    pem_path: Path
    created_at: datetime
    retired_at: datetime | None
    status: KeyStatus


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def keys_dir() -> Path:
    s = get_settings()
    return s.jwt_keys_dir if s.jwt_keys_dir is not None else _DEFAULT_KEYS_DIR


def manifest_path() -> Path:
    return get_settings().jwt_keyset_manifest_path


def has_manifest() -> bool:
    return manifest_path().exists()


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _from_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _entry_to_dict(entry: KeyEntry) -> dict[str, Any]:
    return {
        "kid": entry.kid,
        "alg": entry.alg,
        "created_at": _to_iso(entry.created_at),
        "retired_at": _to_iso(entry.retired_at) if entry.retired_at else None,
        "status": entry.status,
    }


def _entry_from_dict(data: dict[str, Any], kdir: Path) -> KeyEntry:
    return KeyEntry(
        kid=data["kid"],
        alg=data["alg"],
        pem_path=kdir / f"{data['kid']}.pem",
        created_at=_from_iso(data["created_at"]) or _now(),
        retired_at=_from_iso(data.get("retired_at")),
        status=data.get("status", "verifying"),
    )


def load_manifest() -> dict[str, Any] | None:
    path = manifest_path()
    if not path.exists():
        return None
    with path.open("r") as f:
        return json.load(f)


def write_manifest(manifest: dict[str, Any]) -> None:
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    os.replace(tmp_path, path)


def list_keys() -> list[KeyEntry]:
    manifest = load_manifest()
    if manifest is None:
        return []
    kdir = keys_dir()
    return [_entry_from_dict(d, kdir) for d in manifest.get("keys", [])]


def get_entry(kid: str) -> KeyEntry | None:
    for entry in list_keys():
        if entry.kid == kid:
            return entry
    return None


def active_kid() -> str | None:
    """Return the kid the auth process should sign with.

    ``JWT_KID`` env var wins over the manifest so a deployment with a
    read-only filesystem can pin a kid without touching the manifest.
    """
    s = get_settings()
    if s.jwt_kid is not None:
        return s.jwt_kid
    manifest = load_manifest()
    if manifest is None:
        return None
    return manifest.get("active")


def add_key(
    alg: Literal["RS256", "ES256"] = "RS256",
    *,
    status: KeyStatus = "verifying",
    activate_immediately: bool = False,
) -> KeyEntry:
    """Generate a new keypair, persist its PEM, and append it to the manifest.

    When the manifest has no active kid yet, the new key is promoted to
    ``active`` regardless of ``status`` so the keyset is always usable.
    """
    kdir = keys_dir()
    kdir.mkdir(parents=True, exist_ok=True)

    key = jwks.generate_private_key(alg)
    signer = jwks.signing_key_from_private_key(key, alg)
    pem_path = kdir / f"{signer.kid}.pem"
    if not pem_path.exists():
        jwks.write_private_key_pem(pem_path, jwks.private_key_to_pem(key), force=False)

    manifest = load_manifest() or {"active": None, "keys": []}

    if not any(e["kid"] == signer.kid for e in manifest["keys"]):
        entry = KeyEntry(
            kid=signer.kid,
            alg=alg,
            pem_path=pem_path,
            created_at=_now(),
            retired_at=None,
            status=status,
        )
        manifest["keys"].append(_entry_to_dict(entry))

    if activate_immediately or manifest.get("active") is None:
        manifest["active"] = signer.kid
        for e in manifest["keys"]:
            if e["kid"] == signer.kid:
                e["status"] = "active"
                e["retired_at"] = None

    write_manifest(manifest)
    record = next(e for e in manifest["keys"] if e["kid"] == signer.kid)
    return _entry_from_dict(record, kdir)


def activate(kid: str) -> None:
    """Flip the active signing kid; previously-active kid becomes ``retired``."""
    manifest = load_manifest()
    if manifest is None:
        raise FileNotFoundError(f"keyset manifest not found: {manifest_path()}")
    target = next((e for e in manifest["keys"] if e["kid"] == kid), None)
    if target is None:
        raise KeyError(f"kid not in keyset: {kid!r}")
    previous = manifest.get("active")
    now_iso = _to_iso(_now())
    for e in manifest["keys"]:
        if e["kid"] == previous and previous != kid:
            e["status"] = "retired"
            e["retired_at"] = now_iso
    target["status"] = "active"
    target["retired_at"] = None
    manifest["active"] = kid
    write_manifest(manifest)


def prune(*, force_all: bool = False) -> list[str]:
    """Drop retired kids whose grace window has elapsed; return removed kids."""
    manifest = load_manifest()
    if manifest is None:
        return []
    grace = get_settings().jwt_rotation_grace_seconds
    now = _now()
    kdir = keys_dir()
    removed: list[str] = []
    surviving: list[dict[str, Any]] = []
    for e in manifest["keys"]:
        if e.get("status") != "retired":
            surviving.append(e)
            continue
        retired_at = _from_iso(e.get("retired_at"))
        elapsed = (now - retired_at).total_seconds() if retired_at else 0.0
        if force_all or (retired_at is not None and elapsed >= grace):
            pem_path = kdir / f"{e['kid']}.pem"
            try:
                pem_path.unlink()
            except FileNotFoundError:
                pass
            removed.append(e["kid"])
        else:
            surviving.append(e)
    manifest["keys"] = surviving
    if manifest.get("active") in removed:
        manifest["active"] = None
    write_manifest(manifest)
    return removed


def import_legacy_single_key() -> KeyEntry | None:
    """Seed the manifest from ``JWT_PRIVATE_KEY_PATH`` / ``JWT_PRIVATE_KEY``.

    Returns ``None`` if the manifest already exists or if the legacy
    single-key environment is empty. Idempotent: re-running on a
    non-empty manifest is a no-op.
    """
    if has_manifest():
        return None
    s = get_settings()
    if s.jwt_private_key is None and s.jwt_private_key_path is None:
        return None
    if s.jwt_private_key is not None:
        pem_bytes = s.jwt_private_key.encode()
    elif s.jwt_private_key_path is not None and s.jwt_private_key_path.exists():
        pem_bytes = s.jwt_private_key_path.read_bytes()
    else:
        return None

    key = serialization.load_pem_private_key(pem_bytes, password=None)
    signer = jwks.signing_key_from_private_key(key, s.jwt_alg, s.jwt_kid)

    kdir = keys_dir()
    kdir.mkdir(parents=True, exist_ok=True)
    pem_path = kdir / f"{signer.kid}.pem"
    if not pem_path.exists():
        jwks.write_private_key_pem(pem_path, jwks.private_key_to_pem(key), force=False)

    entry = KeyEntry(
        kid=signer.kid,
        alg=s.jwt_alg,
        pem_path=pem_path,
        created_at=_now(),
        retired_at=None,
        status="active",
    )
    write_manifest({
        "active": signer.kid,
        "keys": [_entry_to_dict(entry)],
    })
    return entry
