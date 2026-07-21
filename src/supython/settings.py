from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "postgresql://supython:supython@localhost:54322/supython"
    db_statement_timeout_ms: int = 30000
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_allowed_roles: Annotated[frozenset[str], NoDecode] = frozenset[str](
        {"anon", "authenticated"}
    )
    jwt_alg: Literal["RS256", "ES256"] = "RS256"
    jwt_aud: str = "authenticated"

    jwt_private_key: str | None = None
    jwt_private_key_path: Path | None = None
    jwt_kid: str | None = None
    jwt_jwks_path: Path = Path("./.supython/jwks.json")
    jwt_keys_dir: Path | None = None
    jwt_keyset_manifest_path: Path = Path("./.supython/keyset.json")
    jwt_rotation_grace_seconds: int = 3600

    secrets_dir: Path | None = None
    secrets_manifest_path: Path = Path("./.supython/secrets.json")
    secret_rotation_grace_seconds: int = 3600

    @field_validator(
        "jwt_private_key",
        "jwt_kid",
        "secrets_dir",
        "storage_signed_url_secret",
        "oauth_state_secret",
        "storage_s3_endpoint",
        "settings_module",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("db_allowed_roles", mode="before")
    @classmethod
    def _split_db_allowed_roles(cls, v: object) -> object:
        if isinstance(v, str):
            return frozenset(part.strip() for part in v.split(",") if part.strip())
        return v

    @field_validator("security_hsts_enabled", mode="before")
    @classmethod
    def _empty_bool_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator(
        "jwt_private_key_path", "jwt_keys_dir", "backup_docker_container", mode="before"
    )
    @classmethod
    def _empty_path_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    access_token_ttl: int = 3600
    refresh_token_ttl: int = 60 * 60 * 24 * 30

    recover_token_ttl: int = 3600
    magic_link_token_ttl: int = 15 * 60
    otp_token_ttl: int = 10 * 60
    signup_confirm_token_ttl: int = 60 * 60 * 24

    # When true, password signup returns 202 (no tokens) and sends a
    # confirmation email; sign-in is refused with `email_not_confirmed` (403)
    # until the address is proven. Off by default so upgrades and mailer-less
    # dev setups keep the immediate-token signup flow.
    auth_require_email_confirmation: bool = False

    # Ceiling for a per-request magic-link lifetime. A POST /auth/v1/magiclink
    # may pass its own `ttl` (e.g. a multi-day operator invite) without moving
    # the magic_link_token_ttl default that ordinary sign-in links use; the
    # requested value is clamped to [60, magic_link_max_ttl].
    magic_link_max_ttl: int = 60 * 60 * 24 * 7  # 7 days

    # Comma-separated origins (scheme://host[:port]) a magic-link `redirect_url`
    # may target. Empty ⇒ redirects are disabled and verify keeps returning
    # JSON. A redirect_url whose origin is not listed is rejected 400 at request
    # time, so an attacker can't aim a victim's emailed link at a token-stealing
    # site. Example: MAGIC_LINK_REDIRECT_ALLOWLIST=https://app.example.com,http://localhost:5173
    magic_link_redirect_allowlist: str = ""
    auth_rate_limit_enabled: bool = True
    auth_rate_limit_window_seconds: int = 60
    auth_rate_limit_token_per_window: int = 10
    auth_rate_limit_signup_per_window: int = 5
    auth_rate_limit_recover_per_window: int = 3
    auth_rate_limit_otp_per_window: int = 5
    auth_rate_limit_magiclink_per_window: int = 5
    auth_rate_limit_confirm_per_window: int = 5

    authenticator_password: str = "authenticator"

    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "supython@localhost"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    oauth_state_secret: str | None = Field(default=None, min_length=32)
    oauth_state_max_age: int = 600
    # Comma-separated origins (scheme://host[:port]) an OAuth `redirect_uri`
    # may target — the callback 302s there with the token pair in the URL
    # fragment, so an unvalidated value is a token-stealing open redirect.
    # Empty ⇒ every redirect is refused (OAuth sign-in is effectively off
    # until configured). Same origin-matching rules as
    # MAGIC_LINK_REDIRECT_ALLOWLIST.
    # Example: OAUTH_REDIRECT_ALLOWLIST=https://app.example.com,http://localhost:5173
    oauth_redirect_allowlist: str = ""

    # PostgREST
    postgrest_url: str = "http://localhost:54321"
    site_url: str = "http://localhost:8000"

    # CORS: comma-separated allowed browser origins. Empty = no wildcard.
    # Example: CORS_ORIGINS=https://app.example.com,http://localhost:5173
    cors_origins: str = ""

    # Storage (v0.3)
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: str = "./storage"

    storage_s3_endpoint: str | None = None
    storage_s3_region: str = "us-east-1"
    storage_s3_bucket: str = ""
    storage_s3_access_key_id: str = ""
    storage_s3_secret_access_key: str = ""

    storage_signed_url_secret: str | None = Field(default=None, min_length=32)
    storage_signed_url_default_ttl: int = 3600
    storage_max_upload_bytes: int = 50 * 1024 * 1024

    # Security headers
    security_headers_enabled: bool = True

    # HSTS: None = auto (on iff site_url starts with https://). True/False
    # explicitly forces. Dev defaults are safe because site_url defaults to
    # http://localhost:8000, so HSTS is off out of the box.
    security_hsts_enabled: bool | None = None
    security_hsts_max_age: int = 31536000
    security_hsts_include_subdomains: bool = True
    security_hsts_preload: bool = False

    security_frame_options: str = "DENY"
    security_referrer_policy: str = "strict-origin-when-cross-origin"
    security_csp: str = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )
    # Comma-separated path prefixes that skip CSP. Default exempts FastAPI's
    # auto docs (inline scripts + jsdelivr CDN bundle) and the bundled admin
    # SPA (Vue + Naive UI inject inline styles, Monaco uses blob: workers) —
    # both would be broken by the strict `default-src 'none'` policy.
    security_csp_exempt_paths: str = "/docs,/redoc,/openapi.json,/admin"

    # Input size guards (v0.7 — Security round 2)
    # Global cap on request body size for non-streaming write routes. Sized
    # generously for JSON/form payloads so it never trips legitimate auth or
    # control-plane traffic, while still rejecting "1 GB password" abuse
    # before it reaches argon2.
    security_max_body_bytes: int = 1 * 1024 * 1024
    # Path prefixes whose bodies are governed by their own per-feature caps
    # (storage_max_upload_bytes, functions_max_body_bytes) rather than the
    # global cap. Keeps streaming uploads working without bloating the
    # global default.
    security_body_limit_exempt_paths: str = "/storage/v1/object,/functions"

    # Functions (v0.3)
    functions_dir: str = "./functions"
    functions_hot_reload: bool = True
    functions_max_body_bytes: int = 5 * 1024 * 1024
    functions_max_handler_seconds: float = 30.0

    # Realtime (v0.4)
    realtime_enabled: bool = True
    realtime_notify_channel: str = "realtime:changes"
    realtime_max_connections: int = 1000
    realtime_max_subs_per_conn: int = 100
    # Server-side timeout: close socket with 1001 if no heartbeat arrives within this window.
    # Client SDK sends heartbeats every 25 s; default gives 5 s of grace.
    realtime_heartbeat_timeout_seconds: int = 30
    realtime_broker_queue_size: int = 1000
    realtime_rls_check_timeout_s: float = 1.0
    realtime_broadcast_self_default: bool = False

    # Jobs (v0.5)
    jobs_enabled: bool = True
    jobs_backend: Literal["pg"] = "pg"
    jobs_cron_backend: Literal["pg_cron", "inproc", "off"] = "pg_cron"
    jobs_queue_default: str = "default"
    jobs_poll_interval_s: float = 1.0
    jobs_concurrency: int = 5
    jobs_default_max_attempts: int = 3
    jobs_backoff_base_s: float = 5.0
    jobs_backoff_max_s: float = 300.0
    jobs_visibility_timeout_s: float = 300.0
    jobs_visibility_reclaim_batch: int = 10
    jobs_drain_timeout_s: float = 30.0
    jobs_dev_inprocess: bool = False
    arq_redis_url: str = "redis://localhost:6379"
    dramatiq_broker_url: str = "redis://localhost:6379"

    # Backups (v1.1.4)
    backups_dir: str = "./backups"
    backup_timeout_s: int = 1800
    # "host"   — invoke pg_dump from the worker's PATH (production: bundle it
    #            in the worker image; bare-metal: install postgresql-client).
    # "docker" — exec pg_dump inside the running postgres container (dev with
    #            docker-compose; uses the postgres image's bundled binary so
    #            the version always matches the server and no host install
    #            is needed).
    backup_via: Literal["host", "docker"] = "docker"
    # No default: scaffolded projects pre-fill this in .env (`<project>-db`),
    # and `_build_args` raises a clear error when docker mode is selected
    # without a container name configured.
    backup_docker_container: str | None = None

    log_level: str = "INFO"
    log_json: bool = True

    # Comma-separated dotted module paths to import at boot, e.g.
    # `myapp.jobs,myapp.hooks`. Imports happen before FastAPI app
    # construction (so @job / @cron / @on decorators register) and again
    # before the job worker starts. Env var: `EXTENSIONS=…`.
    extensions: Annotated[list[str], NoDecode] = []

    @field_validator("extensions", mode="before")
    @classmethod
    def _split_extensions(cls, v: object) -> object:
        if isinstance(v, str):
            return [part.strip() for part in v.split(",") if part.strip()]
        return v

    # Django-style Python config module declaring EXTENSIONS, EXTRA_ROUTERS,
    # EXTRA_MIDDLEWARE. Loaded before FastAPI app construction. The scaffold's
    # manage.py shim sets this for you. Env var: `SUPYTHON_SETTINGS_MODULE=…`.
    # Prefix differs from `EXTENSIONS=` deliberately: parallels Django's
    # `DJANGO_SETTINGS_MODULE` and avoids collision with unrelated tooling.
    settings_module: str | None = Field(
        default=None,
        validation_alias="SUPYTHON_SETTINGS_MODULE",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def export_env_file() -> None:
    """Export the env file ``Settings`` reads into ``os.environ``.

    pydantic-settings loads ``env_file`` into the typed ``Settings`` model only;
    it never touches ``os.environ``. Code that resolves a *dynamically-named*
    secret — one whose env var name is not known until runtime (e.g. read from a
    DB column) and so cannot be a typed ``Settings`` field but must be read via
    ``os.environ.get(<name>)`` — therefore sees nothing from ``.env`` when the
    process is launched by supython itself (``supython dev``, ``worker run``, a
    CLI subcommand). In a container it works only by accident: docker-compose's
    ``env_file:`` injects ``.env`` into the real process environment first.

    Mirror ``uvicorn --env-file``: load the same file with ``override=False`` so
    variables already present in the real environment (set by the orchestrator)
    always win over a checked-in ``.env``. The path is sourced from the same
    ``SettingsConfigDict.env_file`` ``Settings`` uses, never re-hardcoded.
    Idempotent — safe to call from every boot path; a missing file is a no-op.
    """
    env_file = Settings.model_config.get("env_file")
    if not env_file:
        return
    encoding = Settings.model_config.get("env_file_encoding") or "utf-8"
    paths = [env_file] if isinstance(env_file, str | Path) else list(env_file)
    # pydantic gives the *last* listed file precedence; load_dotenv(override=
    # False) gives the *first*-loaded value precedence — so walk in reverse to
    # preserve that ordering while still letting the real environment win.
    for path in reversed(paths):
        load_dotenv(path, override=False, encoding=encoding)
