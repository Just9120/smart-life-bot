"""Auth provider abstraction."""

from typing import Protocol

from .models import AuthContext


class GoogleAuthProvider(Protocol):
    def resolve_auth_context(self, user_id: int) -> AuthContext:
        """Resolve provider credentials handle for a user."""
