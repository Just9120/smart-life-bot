"""OAuth token exchange boundary models (Sprint 6.3a skeleton)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


_REDACTED = "<redacted>"


class OAuthTokenProvider(StrEnum):
    GOOGLE = "google"


class OAuthTokenType(StrEnum):
    BEARER = "Bearer"


class OAuthTokenExchangeResultCode(StrEnum):
    SUCCESS = "success"
    INVALID_REQUEST = "invalid_request"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    EXCHANGE_FAILED = "exchange_failed"
    TOKEN_STORAGE_NOT_CONFIGURED = "token_storage_not_configured"


@dataclass(frozen=True, slots=True)
class OAuthTokenExchangeRequest:
    user_id: int
    provider: OAuthTokenProvider = OAuthTokenProvider.GOOGLE
    authorization_code: str = ""
    redirect_uri: str = ""
    code_verifier: str | None = None

    def __repr__(self) -> str:
        return (
            "OAuthTokenExchangeRequest("
            f"user_id={self.user_id!r}, "
            f"provider={self.provider.value!r}, "
            f"authorization_code={_REDACTED!r}, "
            f"redirect_uri={self.redirect_uri!r}, "
            f"code_verifier={_REDACTED if self.code_verifier else None!r}"
            ")"
        )


@dataclass(frozen=True, slots=True)
class OAuthTokenBundle:
    provider: OAuthTokenProvider
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    expires_in_seconds: int | None = None
    scopes: tuple[str, ...] = ()
    token_type: OAuthTokenType = OAuthTokenType.BEARER
    id_token: str | None = None
    created_at: datetime | None = None

    def __repr__(self) -> str:
        return (
            "OAuthTokenBundle("
            f"provider={self.provider.value!r}, "
            f"access_token={_REDACTED!r}, "
            f"refresh_token={_REDACTED if self.refresh_token else None!r}, "
            f"expires_at={self.expires_at!r}, "
            f"expires_in_seconds={self.expires_in_seconds!r}, "
            f"scopes={self.scopes!r}, "
            f"token_type={self.token_type.value!r}, "
            f"id_token={_REDACTED if self.id_token else None!r}, "
            f"created_at={self.created_at!r}"
            ")"
        )


@dataclass(frozen=True, slots=True)
class OAuthTokenExchangeResult:
    code: OAuthTokenExchangeResultCode
    message: str
    user_id: int | None = None
    provider: OAuthTokenProvider | None = None
