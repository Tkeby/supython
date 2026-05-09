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
