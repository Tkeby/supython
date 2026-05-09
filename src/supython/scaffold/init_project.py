"""Scaffold a new supython project directory."""

import json
import os
import secrets
from pathlib import Path

from supython import jwks as _jwks

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_JWT_KEYS_DIRNAME = ".supython"
_PRIVATE_KEY_FILENAME = "jwt_private.pem"
_JWKS_FILENAME = "jwks.json"

_TEMPLATE_MAP: list[tuple[str, str]] = [
    ("docker-compose.yml.tmpl", "docker-compose.yml"),
    ("docker-compose.prod.yml.tmpl", "docker-compose.prod.yml"),
    ("env.example.tmpl", ".env.example"),
    ("gitignore.tmpl", ".gitignore"),
    ("README.md.tmpl", "README.md"),
    ("functions_README.md.tmpl", "functions/README.md"),
    ("Caddyfile.tmpl", "Caddyfile"),
    ("docker_postgres_Dockerfile.tmpl", "docker/postgres/Dockerfile"),
    ("docker_postgres_postgresql.conf.tmpl", "docker/postgres/postgresql.conf"),
    ("settings.py.tmpl", "{name}/settings.py"),
    ("asgi.py.tmpl", "{name}/asgi.py"),
    ("manage.py.tmpl", "manage.py"),
    ("package_init.py.tmpl", "{name}/__init__.py"),
    ("apps_jobs.py.tmpl", "{name}/jobs.py"),
    ("apps_hooks.py.tmpl", "{name}/hooks.py"),
]


def scaffold(name: str, target: Path, *, force: bool = False) -> list[Path]:
    """Write a minimal supython project into *target*.

    Returns the list of paths written, in order.
    Raises ``FileExistsError`` if *target* is non-empty and *force`` is False.
    """
    if target.exists() and any(target.iterdir()) and not force:
        raise FileExistsError(f"{target} is not empty. Use --force to overwrite.")

    target.mkdir(parents=True, exist_ok=True)
    (target / "migrations").mkdir(exist_ok=True)
    (target / "functions").mkdir(exist_ok=True)

    vars: dict[str, str] = {
        "name": name,
    }

    written: list[Path] = []

    for tmpl_name, dest_rel in _TEMPLATE_MAP:
        tmpl_path = _TEMPLATES_DIR / tmpl_name
        content = tmpl_path.read_text().format(**vars)
        dest = target / dest_rel.format(**vars)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not force:
            continue
        dest.write_text(content)
        written.append(dest)

    # manage.py should be executable.
    manage_py = target / "manage.py"
    if manage_py.exists() and os.name == "posix":
        manage_py.chmod(manage_py.stat().st_mode | 0o111)

    gitkeep = target / "migrations" / ".gitkeep"
    if not gitkeep.exists() or force:
        gitkeep.write_text("")
        written.append(gitkeep)

    written.extend(_write_scaffold_keypair(target, force=force))
    written.extend(_write_scaffold_secrets(target, force=force))
    return written


def _write_scaffold_keypair(target: Path, *, force: bool) -> list[Path]:
    key_dir = target / _JWT_KEYS_DIRNAME
    key_dir.mkdir(parents=True, exist_ok=True)
    pem_path = key_dir / _PRIVATE_KEY_FILENAME
    jwks_path = key_dir / _JWKS_FILENAME

    if not force and pem_path.exists() and jwks_path.exists():
        return []

    key = _jwks.generate_private_key("RS256")
    signer = _jwks.signing_key_from_private_key(key, "RS256")
    _jwks.write_private_key_pem(pem_path, _jwks.private_key_to_pem(key), force=force)
    _jwks.write_jwks_file(jwks_path, _jwks.jwks_for_signing_key(signer))
    return [pem_path, jwks_path]


def _write_scaffold_secrets(target: Path, *, force: bool) -> list[Path]:
    secrets_dir = target / ".supython" / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target / ".supython" / "secrets.json"

    if not force and manifest_path.exists():
        return []

    oauth_secret = secrets.token_urlsafe(48)
    storage_secret = secrets.token_urlsafe(48)

    oauth_kid = "v1"
    storage_kid = "v1"

    (secrets_dir / f"oauth_state.{oauth_kid}.secret").write_text(oauth_secret)
    (secrets_dir / f"storage_signed_url.{storage_kid}.secret").write_text(storage_secret)
    if os.name == "posix":
        (secrets_dir / f"oauth_state.{oauth_kid}.secret").chmod(0o600)
        (secrets_dir / f"storage_signed_url.{storage_kid}.secret").chmod(0o600)

    now_iso = "2026-01-01T00:00:00Z"  # static; tests read back the actual values
    manifest = {
        "oauth_state": {
            "active": oauth_kid,
            "keys": [
                {
                    "kid": oauth_kid,
                    "status": "active",
                    "created_at": now_iso,
                    "retired_at": None,
                }
            ],
        },
        "storage_signed_url": {
            "active": storage_kid,
            "keys": [
                {
                    "kid": storage_kid,
                    "status": "active",
                    "created_at": now_iso,
                    "retired_at": None,
                }
            ],
        },
    }
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return [
        secrets_dir / f"oauth_state.{oauth_kid}.secret",
        secrets_dir / f"storage_signed_url.{storage_kid}.secret",
        manifest_path,
    ]
