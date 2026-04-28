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
    def __init__(self, *, result: ParsingResult | None = None) -> None:
        self.calls: list[tuple[str, int]] = []
        self.result = result

    def parse(self, text: str, user_id: int) -> ParsingResult:
        self.calls.append((text, user_id))
        if self.result is not None:
            return self.result
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


class SpyLLMParser:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def parse(self, text: str, user_id: int) -> ParsingResult:
        self.calls.append((text, user_id))
        return ParsingResult(
            draft=EventDraft(
                title=f"LLM Parsed: {text}",
                start_at=datetime(2026, 4, 27, 9, 0, tzinfo=UTC),
                end_at=datetime(2026, 4, 27, 10, 0, tzinfo=UTC),
                timezone="UTC",
                metadata={
                    "source": "claude-parser",
                    "raw_text": text,
                    "user_id": str(user_id),
                    "llm_parser": "claude",
                },
            ),
            confidence=0.9,
            is_ambiguous=False,
            issues=[],
        )


def _build_router(
    *,
    python_result: ParsingResult | None = None,
    with_llm: bool = False,
) -> tuple[ParserModeRouter, SQLiteUserPreferencesRepository, int, SpyPythonParser, SpyLLMParser | None]:
    connection = create_sqlite_connection("sqlite:///:memory:")
    init_sqlite_schema(connection)
    users_repo = SQLiteUsersRepository(connection)
    user = users_repo.create(telegram_user_id=4242)

    preferences_repo = SQLiteUserPreferencesRepository(connection)
    python_parser = SpyPythonParser(result=python_result)
    llm_parser = SpyLLMParser() if with_llm else None
    router = ParserModeRouter(
        user_preferences_repo=preferences_repo,
        python_parser=python_parser,
        llm_parser=llm_parser,
    )
    return router, preferences_repo, user.id, python_parser, llm_parser


def test_default_preference_routes_to_python_and_creates_preference() -> None:
    router, preferences_repo, user_id, _, _ = _build_router()

    result = router.parse("Meeting tomorrow", user_id=user_id)

    preferences = preferences_repo.get_for_user(user_id)
    assert preferences is not None
    assert preferences.parser_mode is ParserMode.PYTHON

    assert result.draft.metadata["parser_mode"] == "python"
    assert result.draft.metadata["parser_router"] == "python"


def test_llm_mode_calls_llm_when_configured() -> None:
    router, preferences_repo, user_id, python_parser, llm_parser = _build_router(with_llm=True)
    preferences_repo.set_parser_mode(user_id=user_id, parser_mode=ParserMode.LLM)

    result = router.parse("LLM mode", user_id=user_id)

    assert llm_parser is not None
    assert llm_parser.calls == [("LLM mode", user_id)]
    assert python_parser.calls == []
    assert result.draft.metadata["parser_mode"] == "llm"
    assert result.draft.metadata["parser_router"] == "llm"


def test_python_mode_does_not_call_llm() -> None:
    router, preferences_repo, user_id, python_parser, llm_parser = _build_router(with_llm=True)
    preferences_repo.set_parser_mode(user_id=user_id, parser_mode=ParserMode.PYTHON)

    router.parse("Python mode", user_id=user_id)

    assert python_parser.calls == [("Python mode", user_id)]
    assert llm_parser is not None
    assert llm_parser.calls == []


def test_auto_mode_keeps_python_when_confident_and_no_missing_start_issue() -> None:
    confident_result = ParsingResult(
        draft=EventDraft(
            title="Confident",
            start_at=datetime(2026, 4, 26, 15, 0, tzinfo=UTC),
            end_at=datetime(2026, 4, 26, 16, 0, tzinfo=UTC),
            timezone="UTC",
            metadata={"source": "rule-based-parser"},
        ),
        confidence=0.95,
        is_ambiguous=False,
        issues=[],
    )
    router, preferences_repo, user_id, python_parser, llm_parser = _build_router(
        python_result=confident_result,
        with_llm=True,
    )
    preferences_repo.set_parser_mode(user_id=user_id, parser_mode=ParserMode.AUTO)

    result = router.parse("Auto mode", user_id=user_id)

    assert result.draft.metadata["parser_mode"] == "auto"
    assert result.draft.metadata["parser_router"] == "python"
    assert result.draft.metadata["llm_fallback_available"] == "true"
    assert python_parser.calls == [("Auto mode", user_id)]
    assert llm_parser is not None
    assert llm_parser.calls == []


def test_auto_mode_calls_llm_when_python_result_is_ambiguous() -> None:
    ambiguous_result = ParsingResult(
        draft=EventDraft(
            title="Ambiguous",
            start_at=None,
            end_at=None,
            timezone="UTC",
            metadata={"source": "rule-based-parser"},
        ),
        confidence=0.2,
        is_ambiguous=True,
        issues=["missing_start_at"],
    )
    router, preferences_repo, user_id, python_parser, llm_parser = _build_router(
        python_result=ambiguous_result,
        with_llm=True,
    )
    preferences_repo.set_parser_mode(user_id=user_id, parser_mode=ParserMode.AUTO)

    result = router.parse("Need fallback", user_id=user_id)

    assert result.draft.metadata["parser_mode"] == "auto"
    assert result.draft.metadata["parser_router"] == "llm_fallback"
    assert result.draft.metadata["llm_fallback_available"] == "true"
    assert python_parser.calls == [("Need fallback", user_id)]
    assert llm_parser is not None
    assert llm_parser.calls == [("Need fallback", user_id)]


def test_llm_mode_without_configuration_falls_back_to_python() -> None:
    router, preferences_repo, user_id, _, _ = _build_router(with_llm=False)
    preferences_repo.set_parser_mode(user_id=user_id, parser_mode=ParserMode.LLM)

    result = router.parse("LLM mode", user_id=user_id)

    assert result.draft.metadata["parser_mode"] == "llm"
    assert result.draft.metadata["parser_router"] == "python_fallback_llm_not_configured"
    assert result.draft.metadata["llm_fallback_available"] == "false"


def test_invalid_preference_in_db_falls_back_to_python_without_crash() -> None:
    router, preferences_repo, user_id, _, _ = _build_router()
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
