"""GitHub OAuth2 provider."""

from . import ProviderProfile
from .oauth import OAuthProvider


class GitHubProvider(OAuthProvider):
    name = "github"
    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    # GitHub requires Accept: application/json to return JSON (not form-encoded).
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USERINFO_URL = "https://api.github.com/user"
    DEFAULT_SCOPE = "read:user user:email"

    def _profile_from_userinfo(self, data: dict) -> ProviderProfile:
        # GitHub users may have a null public email; the service layer will
        # reject the profile if the email is empty.
        return ProviderProfile(
            provider_user_id=str(data["id"]),
            email=data.get("email") or "",
            raw=data,
        )
