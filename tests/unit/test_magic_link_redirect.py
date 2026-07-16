"""Unit tests for magic-link redirect validation + TTL clamping.

Pure functions — no DB, no app. Covers the origin allowlist (the security
boundary that stops a magic link being aimed at a token-stealing site) and the
per-request TTL clamp.
"""

import pytest

from supython.auth import service


class _S:
    """Minimal stand-in for Settings (only the fields the clamp reads)."""

    def __init__(self, default_ttl: int, max_ttl: int) -> None:
        self.magic_link_token_ttl = default_ttl
        self.magic_link_max_ttl = max_ttl


ALLOWLIST = "https://app.example.com,http://localhost:5173"


class TestValidateRedirect:
    def test_allowlisted_origin_passes_and_returns_url(self):
        url = "https://app.example.com/accept-invite?token=abc#frag"
        assert service.validate_magic_link_redirect(url, ALLOWLIST) == url

    def test_localhost_with_port_matches(self):
        url = "http://localhost:5173/onboarding"
        assert service.validate_magic_link_redirect(url, ALLOWLIST) == url

    def test_origin_match_is_case_insensitive_on_host(self):
        url = "https://APP.example.com/x"
        assert service.validate_magic_link_redirect(url, ALLOWLIST) == url

    def test_unlisted_origin_rejected(self):
        with pytest.raises(service.AuthError) as ei:
            service.validate_magic_link_redirect("https://evil.example.com/x", ALLOWLIST)
        assert ei.value.code == "invalid_redirect"
        assert ei.value.status == 400

    def test_wrong_port_rejected(self):
        with pytest.raises(service.AuthError):
            service.validate_magic_link_redirect("http://localhost:9999/x", ALLOWLIST)

    def test_wrong_scheme_rejected(self):
        # Right host, wrong scheme — origin includes scheme, so this must fail.
        with pytest.raises(service.AuthError):
            service.validate_magic_link_redirect("http://app.example.com/x", ALLOWLIST)

    def test_empty_allowlist_rejects_everything(self):
        with pytest.raises(service.AuthError):
            service.validate_magic_link_redirect("https://app.example.com/x", "")

    @pytest.mark.parametrize(
        "bad",
        [
            "app.example.com/x",  # no scheme
            "ftp://app.example.com/x",  # non-http scheme
            "javascript:alert(1)",  # scheme, no netloc
            "https://user:pass@app.example.com/x",  # embedded credentials
            "",  # empty
            "/relative/path",  # relative
        ],
    )
    def test_malformed_targets_rejected(self, bad):
        with pytest.raises(service.AuthError) as ei:
            service.validate_magic_link_redirect(bad, ALLOWLIST)
        assert ei.value.code == "invalid_redirect"


class TestClampTtl:
    def test_none_uses_default(self):
        assert service._clamp_magic_link_ttl(None, _S(900, 604800)) == 900

    def test_within_bounds_passes_through(self):
        assert service._clamp_magic_link_ttl(3600, _S(900, 604800)) == 3600

    def test_over_max_clamps_down(self):
        assert service._clamp_magic_link_ttl(999999999, _S(900, 604800)) == 604800

    def test_under_floor_clamps_up(self):
        assert service._clamp_magic_link_ttl(5, _S(900, 604800)) == 60
