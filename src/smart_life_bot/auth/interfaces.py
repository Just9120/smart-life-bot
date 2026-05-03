"""Auth provider abstraction."""

from typing import Protocol

from .models import AuthContext
from .token_models import OAuthTokenBundle, OAuthTokenExchangeRequest


class GoogleAuthProvider(Protocol):
    def resolve_auth_context(self, user_id: int) -> AuthContext:
        """Resolve provider credentials handle for a user."""


class OAuthTokenExchangeProvider(Protocol):
    def exchange_code(self, request: OAuthTokenExchangeRequest) -> OAuthTokenBundle:
        """Exchange an OAuth authorization code for provider token bundle."""


class OAuthTokenRepository(Protocol):
    def save_token_bundle(self, *, user_id: int, token_bundle: OAuthTokenBundle) -> None:
        """Persist OAuth token bundle for user/provider."""

    def get_token_bundle(self, *, user_id: int, provider: str) -> OAuthTokenBundle | None:
        """Get persisted token bundle by user/provider."""

    def delete_token_bundle(self, *, user_id: int, provider: str) -> None:
        """Delete persisted token bundle by user/provider."""
