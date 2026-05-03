from __future__ import annotations

import hashlib

from smart_life_bot.application.use_cases import HandleOAuthCallbackUseCase
from smart_life_bot.auth.callback_models import OAuthCallbackRequest, OAuthCallbackResultCode
from smart_life_bot.runtime.composition import _Dependencies
from smart_life_bot.runtime.fakes import DevFakeCalendarService, DevFakeGoogleAuthProvider
from smart_life_bot.storage.sqlite import (
    SQLiteConversationStateRepository,
    SQLiteEventsLogRepository,
    SQLiteProviderCredentialsRepository,
    SQLiteUserOAuthConnectionStateRepository,
    SQLiteUserPreferencesRepository,
    SQLiteUsersRepository,
    create_sqlite_connection,
    init_sqlite_schema,
)
from smart_life_bot.parsing.rule_based import RuleBasedMessageParser
from smart_life_bot.observability.logger import get_context_logger
from smart_life_bot.domain.enums import GoogleAuthMode


def _build_use_case() -> tuple[HandleOAuthCallbackUseCase, SQLiteUserOAuthConnectionStateRepository, SQLiteUsersRepository]:
    conn = create_sqlite_connection("sqlite:///:memory:")
    init_sqlite_schema(conn)
    users = SQLiteUsersRepository(conn)
    deps = _Dependencies(
        parser=RuleBasedMessageParser(default_timezone="UTC"),
        auth_provider=DevFakeGoogleAuthProvider(auth_mode=GoogleAuthMode.OAUTH_USER_MODE),
        calendar_service=DevFakeCalendarService(),
        users_repo=users,
        user_preferences_repo=SQLiteUserPreferencesRepository(conn),
        credentials_repo=SQLiteProviderCredentialsRepository(conn),
        oauth_state_repo=SQLiteUserOAuthConnectionStateRepository(conn),
        state_repo=SQLiteConversationStateRepository(conn),
        events_log_repo=SQLiteEventsLogRepository(conn),
        logger=get_context_logger(),
    )
    return HandleOAuthCallbackUseCase(deps=deps), deps.oauth_state_repo, users


def test_oauth_callback_missing_state_returns_missing_state() -> None:
    use_case, repo, users = _build_use_case()
    user = users.get_or_create_by_telegram_id(3001, timezone="UTC")
    before = repo.get_or_create_for_user(user.id)

    result = use_case.execute(OAuthCallbackRequest(state=None, code="abc"))

    assert result.code is OAuthCallbackResultCode.MISSING_STATE
    after = repo.get_or_create_for_user(user.id)
    assert after.status == before.status
    assert after.state_token_hash == before.state_token_hash


def test_oauth_callback_invalid_state_returns_invalid_state() -> None:
    use_case, _, _ = _build_use_case()

    result = use_case.execute(OAuthCallbackRequest(state="unknown-state", code="abc"))

    assert result.code is OAuthCallbackResultCode.INVALID_STATE


def test_oauth_callback_provider_error_marks_state_error() -> None:
    use_case, repo, users = _build_use_case()
    user = users.get_or_create_by_telegram_id(3002, timezone="UTC")
    state = "provider-error-state"
    repo.mark_pending(user.id, hashlib.sha256(state.encode("utf-8")).hexdigest())

    result = use_case.execute(OAuthCallbackRequest(state=state, error="access_denied", error_description="user denied"))

    assert result.code is OAuthCallbackResultCode.PROVIDER_ERROR
    updated = repo.get_or_create_for_user(user.id)
    assert updated.status == "error"
    assert updated.error_code == "provider_error"


def test_oauth_callback_code_returns_token_exchange_pending_without_connecting() -> None:
    use_case, repo, users = _build_use_case()
    user = users.get_or_create_by_telegram_id(3003, timezone="UTC")
    state = "token-pending-state"
    repo.mark_pending(user.id, hashlib.sha256(state.encode("utf-8")).hexdigest())

    result = use_case.execute(OAuthCallbackRequest(state=state, code="raw-auth-code"))

    assert result.code is OAuthCallbackResultCode.TOKEN_EXCHANGE_PENDING
    updated = repo.get_or_create_for_user(user.id)
    assert updated.status == "pending"


def test_oauth_callback_state_lookup_uses_hash() -> None:
    use_case, repo, users = _build_use_case()
    user = users.get_or_create_by_telegram_id(3004, timezone="UTC")
    state = "hash-state-check"
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    repo.mark_pending(user.id, state_hash)

    direct = repo.get_by_state_token_hash(state_hash)
    assert direct is not None
    assert direct.user_id == user.id

    result = use_case.execute(OAuthCallbackRequest(state=state, code="abc"))
    assert result.code is OAuthCallbackResultCode.TOKEN_EXCHANGE_PENDING
