"""Settings parsing (isolated from repo `.env`)."""

import pytest
from pydantic import ValidationError

from supython.settings import Settings


def test_jwt_alg_rejects_hs256() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_alg="HS256")


def test_jwt_secret_env_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "leaked-from-old-env")
    s = Settings(_env_file=None)
    assert not hasattr(s, "jwt_secret"), "`jwt_secret` must not re-appear in Settings"


def test_cors_origins_default_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    s = Settings(_env_file=None)
    assert s.cors_origins == ""


def test_cors_origins_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://app.example.com")
    s = Settings(_env_file=None)
    assert s.cors_origins == "http://localhost:3000,https://app.example.com"


def test_db_pool_and_timeout_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.db_pool_min_size == 1
    assert s.db_pool_max_size == 10
    assert s.db_statement_timeout_ms == 30000


def test_auth_rate_limit_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.auth_rate_limit_enabled is True
    assert s.auth_rate_limit_window_seconds == 60
    assert s.auth_rate_limit_token_per_window == 10
    assert s.auth_rate_limit_signup_per_window == 5
    assert s.auth_rate_limit_recover_per_window == 3
    assert s.auth_rate_limit_otp_per_window == 5
    assert s.auth_rate_limit_magiclink_per_window == 5


def test_magic_link_redirect_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.magic_link_max_ttl == 60 * 60 * 24 * 7
    # Empty by default ⇒ redirects are off until an operator opts in.
    assert s.magic_link_redirect_allowlist == ""


def test_magic_link_redirect_allowlist_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MAGIC_LINK_REDIRECT_ALLOWLIST",
        "https://app.example.com,http://localhost:5173",
    )
    s = Settings(_env_file=None)
    assert s.magic_link_redirect_allowlist == "https://app.example.com,http://localhost:5173"
