"""GitHub OAuth2 provider."""

from authlib.integrations.httpx_client import AsyncOAuth2Client

from . import ProviderProfile
from .oauth import OAuthProvider


class GitHubProvider(OAuthProvider):
    name = "github"
    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    # GitHub requires Accept: application/json to return JSON (not form-encoded).
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USERINFO_URL = "https://api.github.com/user"
    EMAILS_URL = "https://api.github.com/user/emails"
    DEFAULT_SCOPE = "read:user user:email"

    async def _build_profile(
        self, client: AsyncOAuth2Client, data: dict
    ) -> ProviderProfile:
        # The public profile email on /user is optional and carries no
        # verified flag, so it must not be trusted for account linking.
        # /user/emails (covered by the user:email scope) lists every address
        # with primary/verified bits; only a verified one may be used.
        email, verified = "", False
        resp = await client.get(self.EMAILS_URL)
        if resp.status_code == 200:
            entries = [e for e in resp.json() if e.get("verified")]
            primary = [e for e in entries if e.get("primary")]
            chosen = primary[0] if primary else (entries[0] if entries else None)
            if chosen:
                email, verified = chosen["email"], True
        # Fall back to the public profile email for display only — the
        # service layer refuses email matching when verified is False.
        if not email:
            email = data.get("email") or ""
        return ProviderProfile(
            provider_user_id=str(data["id"]),
            email=email,
            email_verified=verified,
            raw=data,
        )

    def _profile_from_userinfo(self, data: dict) -> ProviderProfile:
        return ProviderProfile(
            provider_user_id=str(data["id"]),
            email=data.get("email") or "",
            email_verified=False,
            raw=data,
        )
