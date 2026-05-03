"""Transport-agnostic OAuth callback boundary models (Sprint 6.2 skeleton)."""

from dataclasses import dataclass
from enum import StrEnum


class OAuthCallbackResultCode(StrEnum):
    SUCCESS = "success"
    MISSING_STATE = "missing_state"
    INVALID_STATE = "invalid_state"
    PROVIDER_ERROR = "provider_error"
    TOKEN_EXCHANGE_PENDING = "token_exchange_pending"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class OAuthCallbackRequest:
    state: str | None
    code: str | None = None
    error: str | None = None
    error_description: str | None = None


@dataclass(frozen=True, slots=True)
class OAuthCallbackResult:
    code: OAuthCallbackResultCode
    message: str
    user_id: int | None = None
    redirect_hint: str | None = None

