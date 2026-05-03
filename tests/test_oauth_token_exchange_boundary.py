from datetime import datetime

from smart_life_bot.application.use_cases import ExchangeOAuthCodeUseCase
from smart_life_bot.auth.token_models import (
    OAuthTokenBundle,
    OAuthTokenExchangeRequest,
    OAuthTokenExchangeResultCode,
    OAuthTokenProvider,
)


class FakeExchangeProvider:
    def __init__(self, token_bundle: OAuthTokenBundle):
        self.token_bundle = token_bundle
        self.seen_request: OAuthTokenExchangeRequest | None = None

    def exchange_code(self, request: OAuthTokenExchangeRequest) -> OAuthTokenBundle:
        self.seen_request = request
        return self.token_bundle


class FakeTokenRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[int, OAuthTokenBundle]] = []

    def save_token_bundle(self, *, user_id: int, token_bundle: OAuthTokenBundle) -> None:
        self.saved.append((user_id, token_bundle))

    def get_token_bundle(self, *, user_id: int, provider: str) -> OAuthTokenBundle | None:
        return None

    def delete_token_bundle(self, *, user_id: int, provider: str) -> None:
        return None


def test_exchange_request_repr_redacts_authorization_code() -> None:
    request = OAuthTokenExchangeRequest(user_id=1, authorization_code="secret-code", redirect_uri="https://example/callback")

    text = repr(request)

    assert "secret-code" not in text
    assert "<redacted>" in text


def test_token_bundle_repr_redacts_sensitive_tokens() -> None:
    bundle = OAuthTokenBundle(
        provider=OAuthTokenProvider.GOOGLE,
        access_token="access-secret",
        refresh_token="refresh-secret",
        id_token="id-secret",
        expires_at=datetime(2026, 1, 1, 0, 0, 0),
    )

    text = repr(bundle)

    assert "access-secret" not in text
    assert "refresh-secret" not in text
    assert "id-secret" not in text
    assert text.count("<redacted>") >= 3


def test_use_case_returns_invalid_request_for_missing_required_fields() -> None:
    use_case = ExchangeOAuthCodeUseCase()

    result = use_case.execute(OAuthTokenExchangeRequest(user_id=0, authorization_code="", redirect_uri=""))

    assert result.code is OAuthTokenExchangeResultCode.INVALID_REQUEST


def test_use_case_returns_provider_not_configured_without_exchange_provider() -> None:
    use_case = ExchangeOAuthCodeUseCase()
    request = OAuthTokenExchangeRequest(user_id=1, authorization_code="code", redirect_uri="https://example/cb")

    result = use_case.execute(request)

    assert result.code is OAuthTokenExchangeResultCode.PROVIDER_NOT_CONFIGURED


def test_use_case_returns_storage_not_configured_and_does_not_persist_auth_code() -> None:
    bundle = OAuthTokenBundle(provider=OAuthTokenProvider.GOOGLE, access_token="token")
    provider = FakeExchangeProvider(bundle)
    use_case = ExchangeOAuthCodeUseCase(exchange_provider=provider, token_repository=None)
    request = OAuthTokenExchangeRequest(user_id=42, authorization_code="one-time-code", redirect_uri="https://example/cb")

    result = use_case.execute(request)

    assert result.code is OAuthTokenExchangeResultCode.TOKEN_STORAGE_NOT_CONFIGURED
    assert provider.seen_request is not None
    assert "one-time-code" not in repr(result)


def test_use_case_success_with_fake_provider_and_fake_repository() -> None:
    bundle = OAuthTokenBundle(provider=OAuthTokenProvider.GOOGLE, access_token="token")
    provider = FakeExchangeProvider(bundle)
    repository = FakeTokenRepository()
    use_case = ExchangeOAuthCodeUseCase(exchange_provider=provider, token_repository=repository)

    result = use_case.execute(
        OAuthTokenExchangeRequest(user_id=101, authorization_code="oauth-code", redirect_uri="https://example/callback")
    )

    assert result.code is OAuthTokenExchangeResultCode.SUCCESS
    assert repository.saved == [(101, bundle)]
