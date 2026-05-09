"""OAuth provider abstractions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderProfile:
    """Normalised identity returned by any OAuth provider."""

    provider_user_id: str
    email: str
    raw: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    """Abstract base that each concrete OAuth provider must implement."""

    name: str

    @abstractmethod
    async def authorize_url(
        self, state: str, redirect_uri: str, code_verifier: str | None = None
    ) -> str:
        """Return the full authorization URL to redirect the user to."""
        ...

    @abstractmethod
    async def exchange(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> ProviderProfile:
        """Exchange an authorization code for a normalised ProviderProfile."""
        ...
