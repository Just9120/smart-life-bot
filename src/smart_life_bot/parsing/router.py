"""Parser mode router implementation behind MessageParser protocol."""

from __future__ import annotations

from dataclasses import dataclass

from smart_life_bot.domain.enums import ParserMode
from smart_life_bot.parsing.interfaces import MessageParser
from smart_life_bot.parsing.models import ParsingResult
from smart_life_bot.storage.interfaces import UserPreferencesRepository


@dataclass(slots=True)
class ParserModeRouter:
    """Route parsing through parser mode preference with safe fallbacks."""

    user_preferences_repo: UserPreferencesRepository
    python_parser: MessageParser
    llm_parser: MessageParser | None = None
    default_parser_mode: ParserMode = ParserMode.PYTHON
    auto_confidence_threshold: float = 0.85

    def parse(self, text: str, user_id: int) -> ParsingResult:
        try:
            preferences = self.user_preferences_repo.get_or_create_for_user(
                user_id=user_id,
                default_parser_mode=self.default_parser_mode,
            )
            parser_mode = preferences.parser_mode
        except ValueError:
            return self._parse_python_with_metadata(
                text=text,
                user_id=user_id,
                parser_mode=ParserMode.PYTHON,
                parser_router="python_fallback_invalid_preference",
            )

        if parser_mode is ParserMode.PYTHON:
            return self._parse_python_with_metadata(
                text=text,
                user_id=user_id,
                parser_mode=ParserMode.PYTHON,
                parser_router="python",
            )

        if parser_mode is ParserMode.LLM:
            if self.llm_parser is None:
                return self._parse_python_with_metadata(
                    text=text,
                    user_id=user_id,
                    parser_mode=ParserMode.LLM,
                    parser_router="python_fallback_llm_not_configured",
                    llm_fallback_available=False,
                )
            return self._merge_metadata(
                self.llm_parser.parse(text=text, user_id=user_id),
                parser_mode=ParserMode.LLM,
                parser_router="llm",
            )

        if parser_mode is ParserMode.AUTO:
            python_result = self.python_parser.parse(text=text, user_id=user_id)
            llm_available = self.llm_parser is not None
            if self._should_use_python_result(python_result):
                return self._merge_metadata(
                    python_result,
                    parser_mode=ParserMode.AUTO,
                    parser_router="python",
                    llm_fallback_available=llm_available,
                )

            if self.llm_parser is not None:
                llm_result = self.llm_parser.parse(text=text, user_id=user_id)
                return self._merge_metadata(
                    llm_result,
                    parser_mode=ParserMode.AUTO,
                    parser_router="llm_fallback",
                    llm_fallback_available=True,
                )

            return self._merge_metadata(
                python_result,
                parser_mode=ParserMode.AUTO,
                parser_router="python_fallback_llm_not_configured",
                llm_fallback_available=False,
            )

        return self._parse_python_with_metadata(
            text=text,
            user_id=user_id,
            parser_mode=ParserMode.PYTHON,
            parser_router="python_fallback_invalid_preference",
        )

    def _parse_python_with_metadata(
        self,
        *,
        text: str,
        user_id: int,
        parser_mode: ParserMode,
        parser_router: str,
        llm_fallback_available: bool | None = None,
    ) -> ParsingResult:
        return self._merge_metadata(
            self.python_parser.parse(text=text, user_id=user_id),
            parser_mode=parser_mode,
            parser_router=parser_router,
            llm_fallback_available=llm_fallback_available,
        )

    def _merge_metadata(
        self,
        result: ParsingResult,
        *,
        parser_mode: ParserMode,
        parser_router: str,
        llm_fallback_available: bool | None = None,
    ) -> ParsingResult:
        metadata = dict(result.draft.metadata)
        metadata["parser_mode"] = parser_mode.value
        metadata["parser_router"] = parser_router
        if llm_fallback_available is not None:
            metadata["llm_fallback_available"] = str(llm_fallback_available).lower()
        result.draft.metadata = metadata
        return result

    def _should_use_python_result(self, result: ParsingResult) -> bool:
        if result.is_ambiguous:
            return False
        if result.confidence < self.auto_confidence_threshold:
            return False
        return "missing_start_at" not in result.issues
