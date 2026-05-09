"""Symmetric secret rotation manifest.

Multi-secret lifecycle for symmetric secrets (storage signed URLs, OAuth state).
Mirrors the JWT keyset pattern: ``secrets.json`` manifest + ``secrets/*.secret``
files. The manifest tracks metadata (kid, status, created_at, retired_at);
secret values live in individual files with ``0o600`` permissions.
"""

import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from .settings import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_SECRETS_DIR = Path("./.supython/secrets")

SecretName = Literal["storage_signed_url", "oauth_state"]
SecretStatus = Literal["active", "verifying", "retired"]


@dataclass(frozen=True)
class SecretEntry:
    kid: str
    name: SecretName
    secret_path: Path
    created_at: datetime
    retired_at: datetime | None
    status: SecretStatus


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def secrets_dir() -> Path:
    s = get_settings()
    return s.secrets_dir if s.secrets_dir is not None else _DEFAULT_SECRETS_DIR


def manifest_path() -> Path:
    return get_settings().secrets_manifest_path


def has_manifest() -> bool:
    return manifest_path().exists()


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _from_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _entry_to_dict(entry: SecretEntry) -> dict[str, Any]:
    return {
        "kid": entry.kid,
        "status": entry.status,
        "created_at": _to_iso(entry.created_at),
        "retired_at": _to_iso(entry.retired_at) if entry.retired_at else None,
    }


def _entry_from_dict(data: dict[str, Any], name: SecretName, sdir: Path) -> SecretEntry:
    return SecretEntry(
        kid=data["kid"],
        name=name,
        secret_path=sdir / f"{name}.{data['kid']}.secret",
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


def list_secrets(name: SecretName) -> list[SecretEntry]:
    manifest = load_manifest()
    if manifest is None:
        return []
    section = manifest.get(name)
    if section is None:
        return []
    sdir = secrets_dir()
    return [_entry_from_dict(d, name, sdir) for d in section.get("keys", [])]


def active_secret(name: SecretName) -> SecretEntry | None:
    manifest = load_manifest()
    if manifest is None:
        return None
    section = manifest.get(name)
    if section is None:
        return None
    active_kid = section.get("active")
    if active_kid is None:
        return None
    for entry in list_secrets(name):
        if entry.kid == active_kid:
            return entry
    return None


def get_entry(name: SecretName, kid: str) -> SecretEntry | None:
    for entry in list_secrets(name):
        if entry.kid == kid:
            return entry
    return None


def import_legacy_single_secret(name: SecretName) -> SecretEntry | None:
    """Seed the manifest from a legacy env var when the manifest is absent.

    Returns ``None`` if the manifest already exists or if the legacy env var
    is empty / shorter than 32 characters.
    """
    if has_manifest():
        return None
    s = get_settings()
    if name == "storage_signed_url":
        legacy = s.storage_signed_url_secret
    elif name == "oauth_state":
        legacy = s.oauth_state_secret
    else:
        return None
    if not legacy or len(legacy) < 32:
        return None

    sdir = secrets_dir()
    sdir.mkdir(parents=True, exist_ok=True)
    kid = "v1"
    secret_path = sdir / f"{name}.{kid}.secret"
    secret_path.write_text(legacy)
    if os.name == "posix":
        secret_path.chmod(0o600)

    entry = SecretEntry(
        kid=kid,
        name=name,
        secret_path=secret_path,
        created_at=_now(),
        retired_at=None,
        status="active",
    )
    manifest = load_manifest() or {}
    manifest[name] = {
        "active": kid,
        "keys": [_entry_to_dict(entry)],
    }
    write_manifest(manifest)
    return entry


def rotate(name: SecretName) -> SecretEntry:
    """Generate a new secret, write file, append to manifest as ``verifying``.

    On first call (no manifest), imports the legacy single secret before
    appending the new one.
    """
    if not has_manifest():
        import_legacy_single_secret(name)

    sdir = secrets_dir()
    sdir.mkdir(parents=True, exist_ok=True)

    kid = secrets.token_urlsafe(8)
    secret_path = sdir / f"{name}.{kid}.secret"
    secret_value = secrets.token_urlsafe(48)
    secret_path.write_text(secret_value)
    if os.name == "posix":
        secret_path.chmod(0o600)

    entry = SecretEntry(
        kid=kid,
        name=name,
        secret_path=secret_path,
        created_at=_now(),
        retired_at=None,
        status="verifying",
    )

    manifest = load_manifest() or {}
    section = manifest.get(name)
    if section is None:
        section = {"active": None, "keys": []}
        manifest[name] = section

    if not any(k["kid"] == kid for k in section["keys"]):
        section["keys"].append(_entry_to_dict(entry))

    if section.get("active") is None:
        section["active"] = kid
        for k in section["keys"]:
            if k["kid"] == kid:
                k["status"] = "active"
                k["retired_at"] = None

    write_manifest(manifest)
    return entry


def activate(name: SecretName, kid: str) -> None:
    """Promote ``kid`` to ``active``; previous active becomes ``retired``."""
    manifest = load_manifest()
    if manifest is None:
        raise FileNotFoundError(f"secret manifest not found: {manifest_path()}")
    section = manifest.get(name)
    if section is None:
        raise KeyError(f"secret name not in manifest: {name!r}")
    target = next((k for k in section["keys"] if k["kid"] == kid), None)
    if target is None:
        raise KeyError(f"kid not in {name} secret set: {kid!r}")
    previous = section.get("active")
    now_iso = _to_iso(_now())
    for k in section["keys"]:
        if k["kid"] == previous and previous != kid:
            k["status"] = "retired"
            k["retired_at"] = now_iso
    target["status"] = "active"
    target["retired_at"] = None
    section["active"] = kid
    write_manifest(manifest)


def prune(name: SecretName, *, force_all: bool = False) -> list[str]:
    """Drop retired secrets past grace; delete ``.secret`` files; return removed kids."""
    manifest = load_manifest()
    if manifest is None:
        return []
    section = manifest.get(name)
    if section is None:
        return []
    grace = get_settings().secret_rotation_grace_seconds
    now = _now()
    sdir = secrets_dir()
    removed: list[str] = []
    surviving: list[dict[str, Any]] = []
    for k in section["keys"]:
        if k.get("status") != "retired":
            surviving.append(k)
            continue
        retired_at = _from_iso(k.get("retired_at"))
        elapsed = (now - retired_at).total_seconds() if retired_at else 0.0
        if force_all or (retired_at is not None and elapsed >= grace):
            secret_path = sdir / f"{name}.{k['kid']}.secret"
            try:
                secret_path.unlink()
            except FileNotFoundError:
                pass
            removed.append(k["kid"])
        else:
            surviving.append(k)
    section["keys"] = surviving
    if section.get("active") in removed:
        section["active"] = None
    write_manifest(manifest)
    return removed


def read_secret_value(entry: SecretEntry) -> str:
    return entry.secret_path.read_text().strip()


@lru_cache(maxsize=None)
def load_signing_secret(name: SecretName) -> str | None:
    """Return the active secret value, or ``None`` when callers should fall back.

    Returns ``None`` when the manifest is absent **or** has no section for
    ``name`` so callers can use the legacy env-var path per-``SecretName``.
    This lets one secret family migrate to the manifest while another keeps
    running on its env var (the §18 "each secret family still rotates
    independently" decision).

    Raises ``RuntimeError`` only when the section exists but its ``active``
    pointer is absent or dangles to a kid that is not in the section's
    ``keys`` list — that state is operator error, surfaced by ``supython
    doctor``.
    """
    manifest = load_manifest()
    if manifest is None:
        return None
    section = manifest.get(name)
    if section is None:
        return None
    active_kid = section.get("active")
    if active_kid is None:
        raise RuntimeError(f"no active secret for {name!r}")
    entry = get_entry(name, active_kid)
    if entry is None:
        raise RuntimeError(
            f"active kid {active_kid!r} for {name!r} not present in manifest"
        )
    return read_secret_value(entry)


@lru_cache(maxsize=None)
def load_verification_secrets(name: SecretName) -> list[tuple[str, str | None]]:
    """Return ``(secret_value, kid)`` for active + retired-within-grace.

    Returns ``[]`` when the manifest is absent.
    """
    manifest = load_manifest()
    if manifest is None:
        return []
    grace = get_settings().secret_rotation_grace_seconds
    now = _now()
    result: list[tuple[str, str | None]] = []
    for entry in list_secrets(name):
        if entry.status == "active":
            result.append((read_secret_value(entry), entry.kid))
        elif entry.status == "retired":
            retired_at = entry.retired_at
            elapsed = (now - retired_at).total_seconds() if retired_at else 0.0
            if retired_at is not None and elapsed < grace:
                result.append((read_secret_value(entry), entry.kid))
    return result


def clear_cache() -> None:
    """Clear cached loaders; call after manifest mutations."""
    load_signing_secret.cache_clear()
    load_verification_secrets.cache_clear()
