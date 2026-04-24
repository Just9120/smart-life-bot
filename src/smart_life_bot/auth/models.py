"""Auth-layer models."""

from dataclasses import dataclass

from smart_life_bot.domain.enums import GoogleAuthMode


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: int
    auth_mode: GoogleAuthMode
    credentials_handle: str
