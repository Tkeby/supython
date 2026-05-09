"""Shared authlib-based OAuth2 provider base."""

from authlib.integrations.httpx_client import AsyncOAuth2Client

from . import Provider, ProviderProfile


class OAuthProvider(Provider):
    """Concrete base for standard Authorization Code + PKCE providers."""

    AUTHORIZE_URL: str
    TOKEN_URL: str
    USERINFO_URL: str
    DEFAULT_SCOPE: str = "openid email profile"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    async def authorize_url(
        self, state: str, redirect_uri: str, code_verifier: str | None = None
    ) -> str:
        async with AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
            scope=self.DEFAULT_SCOPE,
            code_challenge_method="S256",
        ) as client:
            url, _ = client.create_authorization_url(
                self.AUTHORIZE_URL,
                state=state,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        return url

    async def exchange(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> ProviderProfile:
        async with AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
        ) as client:
            await client.fetch_token(
                self.TOKEN_URL,
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
            resp = await client.get(self.USERINFO_URL)
            resp.raise_for_status()
            data: dict = resp.json()
        return self._profile_from_userinfo(data)

    def _profile_from_userinfo(self, data: dict) -> ProviderProfile:
        raise NotImplementedError
