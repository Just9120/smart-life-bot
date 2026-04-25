from __future__ import annotations

from datetime import UTC, datetime

from smart_life_bot.domain.enums import ParserMode
from smart_life_bot.domain.models import EventDraft
from smart_life_bot.parsing.models import ParsingResult
from smart_life_bot.parsing.router import ParserModeRouter
from smart_life_bot.storage.sqlite import (
    SQLiteUserPreferencesRepository,
    SQLiteUsersRepository,
    create_sqlite_connection,
    init_sqlite_schema,
)


class SpyPythonParser:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def parse(self, text: str, user_id: int) -> ParsingResult:
        self.calls.append((text, user_id))
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 4, 26, 15, 0, tzinfo=UTC),
                end_at=datetime(2026, 4, 26, 16, 0, tzinfo=UTC),
                timezone="UTC",
                metadata={
                    "source": "rule-based-parser",
                    "raw_text": text,
                    "user_id": str(user_id),
                },
            ),
            confidence=0.95,
            is_ambiguous=False,
            issues=[],
        )


def _build_router() -> tuple[ParserModeRouter, SQLiteUserPreferencesRepository, int]:
    connection = create_sqlite_connection("sqlite:///:memory:")
    init_sqlite_schema(connection)
    users_repo = SQLiteUsersRepository(connection)
    user = users_repo.create(telegram_user_id=4242)

    preferences_repo = SQLiteUserPreferencesRepository(connection)
    router = ParserModeRouter(
        user_preferences_repo=preferences_repo,
        python_parser=SpyPythonParser(),
    )
    return router, preferences_repo, user.id


def test_default_preference_routes_to_python_and_creates_preference() -> None:
    router, preferences_repo, user_id = _build_router()

    result = router.parse("Meeting tomorrow", user_id=user_id)

    preferences = preferences_repo.get_for_user(user_id)
    assert preferences is not None
    assert preferences.parser_mode is ParserMode.PYTHON

    assert result.draft.metadata["parser_mode"] == "python"
    assert result.draft.metadata["parser_router"] == "python"


def test_existing_python_preference_routes_to_python() -> None:
    router, preferences_repo, user_id = _build_router()
    preferences_repo.set_parser_mode(user_id=user_id, parser_mode=ParserMode.PYTHON)

    result = router.parse("Python mode", user_id=user_id)

    assert result.draft.metadata["parser_mode"] == "python"
    assert result.draft.metadata["parser_router"] == "python"


def test_auto_preference_routes_to_python_fallback() -> None:
    router, preferences_repo, user_id = _build_router()
    preferences_repo.set_parser_mode(user_id=user_id, parser_mode=ParserMode.AUTO)

    result = router.parse("Auto mode", user_id=user_id)

    assert result.draft.metadata["parser_mode"] == "auto"
    assert result.draft.metadata["parser_router"] == "python_fallback"
    assert result.draft.metadata["llm_fallback_available"] == "false"


def test_llm_preference_routes_to_python_fallback_not_implemented() -> None:
    router, preferences_repo, user_id = _build_router()
    preferences_repo.set_parser_mode(user_id=user_id, parser_mode=ParserMode.LLM)

    result = router.parse("LLM mode", user_id=user_id)

    assert result.draft.metadata["parser_mode"] == "llm"
    assert result.draft.metadata["parser_router"] == "python_fallback_llm_not_implemented"
    assert result.draft.metadata["llm_fallback_available"] == "false"


def test_router_preserves_metadata_from_underlying_python_parser() -> None:
    router, _, user_id = _build_router()

    result = router.parse("Preserve metadata", user_id=user_id)

    assert result.draft.metadata["source"] == "rule-based-parser"
    assert result.draft.metadata["raw_text"] == "Preserve metadata"
    assert result.draft.metadata["user_id"] == str(user_id)


def test_invalid_preference_in_db_falls_back_to_python_without_crash() -> None:
    router, preferences_repo, user_id = _build_router()
    preferences_repo._connection.execute(  # noqa: SLF001
        """
        INSERT INTO user_preferences (user_id, parser_mode, created_at, updated_at)
        VALUES (?, 'invalid-mode', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
        ON CONFLICT (user_id)
        DO UPDATE SET parser_mode = excluded.parser_mode
        """,
        (user_id,),
    )
    preferences_repo._connection.commit()  # noqa: SLF001

    result = router.parse("Invalid mode fallback", user_id=user_id)

    assert result.draft.metadata["parser_mode"] == "python"
    assert result.draft.metadata["parser_router"] == "python_fallback_invalid_preference"
