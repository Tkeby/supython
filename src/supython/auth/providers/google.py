"""Google OAuth2 provider."""

from . import ProviderProfile
from .oauth import OAuthProvider


class GoogleProvider(OAuthProvider):
    name = "google"
    AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
    DEFAULT_SCOPE = "openid email profile"

    def _profile_from_userinfo(self, data: dict) -> ProviderProfile:
        # OIDC userinfo carries `email_verified`; Google may serve it as a
        # bool or the string "true" depending on endpoint version.
        verified = data.get("email_verified")
        return ProviderProfile(
            provider_user_id=data["sub"],
            email=data.get("email", ""),
            email_verified=verified is True or verified == "true",
            raw=data,
        )
