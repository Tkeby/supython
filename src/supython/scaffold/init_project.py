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
    ("package_jobs_init.py.tmpl", "{name}/jobs/__init__.py"),
    ("apps_jobs_example.py.tmpl", "{name}/jobs/example.py"),
    ("package_hooks_init.py.tmpl", "{name}/hooks/__init__.py"),
    ("apps_hooks_welcome.py.tmpl", "{name}/hooks/welcome.py"),
    ("pyproject.toml.tmpl", "pyproject.toml"),
]

# Verbatim copies — NOT run through ``str.format``. Use for example files that
# contain literal ``{`` / ``}`` (e.g. f-strings in function code) and need no
# template substitution. Sources live under ``templates/static/``.
_STATIC_MAP: list[tuple[str, str]] = [
    ("static/functions_hello.py", "functions/hello.py"),
    ("static/0001_create_todos.sql", "migrations/0001_create_todos.sql"),
]


def scaffold(
    name: str,
    target: Path,
    *,
    force: bool = False,
    allow_existing: bool = False,
) -> list[Path]:
    """Write a minimal supython project into *target*.

    Returns the list of paths written, in order. Existing files are skipped
    (never overwritten) unless *force* is set, so a re-run only tops up what is
    missing.

    Raises ``FileExistsError`` if *target* is non-empty and neither *force* nor
    *allow_existing* is set. Pass ``allow_existing=True`` when the caller has
    explicitly chosen an existing directory (e.g. ``supython init myapp .``):
    the scaffold then writes alongside whatever is already there.
    """
    if target.exists() and any(target.iterdir()) and not force and not allow_existing:
        raise FileExistsError(f"{target} is not empty. Use --force to overwrite.")

    target.mkdir(parents=True, exist_ok=True)
    (target / "migrations").mkdir(exist_ok=True)
    (target / "functions").mkdir(exist_ok=True)

    vars: dict[str, str] = {
        "name": name,
        "supython_req": _supython_requirement(),
    }

    written: list[Path] = []

    for tmpl_name, dest_rel in _TEMPLATE_MAP:
        content = (_TEMPLATES_DIR / tmpl_name).read_text().format(**vars)
        _emit(target, dest_rel.format(**vars), content, force=force, written=written)

    for src_name, dest_rel in _STATIC_MAP:
        content = (_TEMPLATES_DIR / src_name).read_text()
        _emit(target, dest_rel, content, force=force, written=written)

    # manage.py should be executable.
    manage_py = target / "manage.py"
    if manage_py.exists() and os.name == "posix":
        manage_py.chmod(manage_py.stat().st_mode | 0o111)

    # Write-once artifacts: a runnable .env plus the JWT keypair and signing
    # secrets. These are NEVER overwritten — not even under --force — because
    # rotating them silently would invalidate live sessions and signed URLs.
    # Rotation has dedicated homes: `supython keygen` / `supython secret`.
    written.extend(_write_dotenv(target, vars))
    written.extend(_write_scaffold_keypair(target))
    written.extend(_write_scaffold_secrets(target))
    return written


def _emit(
    target: Path,
    dest_rel: str,
    content: str,
    *,
    force: bool,
    written: list[Path],
) -> None:
    """Write *content* to ``target/dest_rel``, skipping an existing file unless force."""
    dest = target / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        return
    dest.write_text(content)
    written.append(dest)


def _supython_requirement() -> str:
    """PEP 508 requirement string pinning the installed supython version."""
    from supython import __version__

    if __version__.startswith("0.0.0"):
        return "supython"  # version unknown (uninstalled / editable w/o metadata)
    return f"supython>={__version__}"


def _write_dotenv(target: Path, vars: dict[str, str]) -> list[Path]:
    """Write a ready-to-run, gitignored .env from the example template, once.

    Never overwrites an existing .env (it may hold edited dev config). The
    committed reference stays in .env.example.
    """
    dest = target / ".env"
    if dest.exists():
        return []
    content = (_TEMPLATES_DIR / "env.example.tmpl").read_text().format(**vars)
    content = content.replace(
        "# Copy to .env and adjust as needed.",
        "# Generated by `supython init`: working dev defaults. "
        "Edit freely — this file is gitignored.",
        1,
    )
    dest.write_text(content)
    return [dest]


def _write_scaffold_keypair(target: Path) -> list[Path]:
    key_dir = target / _JWT_KEYS_DIRNAME
    key_dir.mkdir(parents=True, exist_ok=True)
    pem_path = key_dir / _PRIVATE_KEY_FILENAME
    jwks_path = key_dir / _JWKS_FILENAME

    # Never re-mint an existing keypair — not even under --force — to avoid
    # silently rotating keys and invalidating live tokens. `supython keygen`
    # owns rotation.
    if pem_path.exists() and jwks_path.exists():
        return []

    key = _jwks.generate_private_key("RS256")
    signer = _jwks.signing_key_from_private_key(key, "RS256")
    _jwks.write_private_key_pem(pem_path, _jwks.private_key_to_pem(key), force=True)
    _jwks.write_jwks_file(jwks_path, _jwks.jwks_for_signing_key(signer))
    return [pem_path, jwks_path]


def _write_scaffold_secrets(target: Path) -> list[Path]:
    secrets_dir = target / ".supython" / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target / ".supython" / "secrets.json"

    # Never regenerate existing secrets — not even under --force. Rotation is
    # `supython secret rotate`.
    if manifest_path.exists():
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
