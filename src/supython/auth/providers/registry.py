"""Provider registry: maps provider name → configured Provider instance."""

from ...settings import get_settings
from . import Provider
from .github import GitHubProvider
from .google import GoogleProvider


def get_provider(name: str) -> Provider:
    """Return a configured provider by name, or raise KeyError if unavailable."""
    s = get_settings()
    if name == "google" and s.google_client_id and s.google_client_secret:
        return GoogleProvider(s.google_client_id, s.google_client_secret)
    if name == "github" and s.github_client_id and s.github_client_secret:
        return GitHubProvider(s.github_client_id, s.github_client_secret)
    raise KeyError(f"Unknown or unconfigured OAuth provider: {name!r}")
