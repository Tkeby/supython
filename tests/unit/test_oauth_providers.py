"""Unit tests for OAuth provider base classes."""

from urllib.parse import parse_qs, urlparse

import pytest

from supython.auth.providers.google import GoogleProvider


class TestGoogleProviderPKCE:
    """Verify that OAuthProvider generates proper PKCE parameters via authlib."""

    @pytest.fixture
    def provider(self):
        return GoogleProvider(client_id="test-id", client_secret="test-secret")

    async def test_authorize_url_includes_code_challenge(self, provider):
        verifier = "a" * 43  # minimum valid length
        url = await provider.authorize_url(
            state="test-state",
            redirect_uri="http://localhost/callback",
            code_verifier=verifier,
        )
        qs = parse_qs(urlparse(url).query)
        assert qs["code_challenge_method"] == ["S256"]
        assert "code_challenge" in qs
        # authlib S256 challenge is base64url(SHA256(verifier))
        assert qs["code_challenge"][0] != verifier
        assert len(qs["code_challenge"][0]) > 0

    async def test_authorize_url_without_verifier_omits_challenge(self, provider):
        url = await provider.authorize_url(
            state="test-state",
            redirect_uri="http://localhost/callback",
            code_verifier=None,
        )
        qs = parse_qs(urlparse(url).query)
        assert "code_challenge" not in qs
        assert "code_challenge_method" not in qs


# ---------------------------------------------------------------------------
# Profile building & email verification flags
# ---------------------------------------------------------------------------

from supython.auth.providers import ProviderProfile  # noqa: E402
from supython.auth.providers.github import GitHubProvider  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code: int, body: object = None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        return self._body


class _FakeClient:
    def __init__(self, emails_response: _FakeResponse) -> None:
        self._resp = emails_response

    async def get(self, url: str) -> _FakeResponse:
        assert url == GitHubProvider.EMAILS_URL
        return self._resp


def test_provider_profile_defaults_to_unverified():
    profile = ProviderProfile(provider_user_id="1", email="a@example.com")
    assert profile.email_verified is False


class TestGoogleProfile:
    provider = GoogleProvider(client_id="cid", client_secret="sec")

    def test_verified_bool(self):
        p = self.provider._profile_from_userinfo(
            {"sub": "g1", "email": "a@example.com", "email_verified": True}
        )
        assert p.email_verified is True

    def test_verified_string(self):
        p = self.provider._profile_from_userinfo(
            {"sub": "g1", "email": "a@example.com", "email_verified": "true"}
        )
        assert p.email_verified is True

    def test_unverified(self):
        p = self.provider._profile_from_userinfo(
            {"sub": "g1", "email": "a@example.com", "email_verified": False}
        )
        assert p.email_verified is False

    def test_missing_flag_is_unverified(self):
        p = self.provider._profile_from_userinfo(
            {"sub": "g1", "email": "a@example.com"}
        )
        assert p.email_verified is False


class TestGitHubProfile:
    provider = GitHubProvider(client_id="cid", client_secret="sec")
    userinfo = {"id": 42, "email": "public@example.com"}

    async def _build(self, emails_body, status=200) -> ProviderProfile:
        client = _FakeClient(_FakeResponse(status, emails_body))
        return await self.provider._build_profile(client, self.userinfo)

    async def test_primary_verified_email_wins(self):
        p = await self._build(
            [
                {"email": "old@example.com", "primary": False, "verified": True},
                {"email": "main@example.com", "primary": True, "verified": True},
            ]
        )
        assert p.email == "main@example.com"
        assert p.email_verified is True
        assert p.provider_user_id == "42"

    async def test_falls_back_to_any_verified_email(self):
        p = await self._build(
            [
                {"email": "main@example.com", "primary": True, "verified": False},
                {"email": "other@example.com", "primary": False, "verified": True},
            ]
        )
        assert p.email == "other@example.com"
        assert p.email_verified is True

    async def test_no_verified_email_falls_back_to_public_unverified(self):
        p = await self._build(
            [{"email": "main@example.com", "primary": True, "verified": False}]
        )
        assert p.email == "public@example.com"
        assert p.email_verified is False

    async def test_emails_endpoint_failure_is_unverified(self):
        p = await self._build(None, status=403)
        assert p.email == "public@example.com"
        assert p.email_verified is False

    def test_sync_profile_from_userinfo_is_unverified(self):
        p = self.provider._profile_from_userinfo(self.userinfo)
        assert p.email == "public@example.com"
        assert p.email_verified is False
