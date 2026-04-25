"""Parser mode router implementation behind MessageParser protocol."""

from __future__ import annotations

from dataclasses import dataclass

from smart_life_bot.domain.enums import ParserMode
from smart_life_bot.parsing.interfaces import MessageParser
from smart_life_bot.parsing.models import ParsingResult
from smart_life_bot.storage.interfaces import UserPreferencesRepository


@dataclass(slots=True)
class ParserModeRouter:
    """Route parsing through parser mode preference with safe Python fallbacks."""

    user_preferences_repo: UserPreferencesRepository
    python_parser: MessageParser
    default_parser_mode: ParserMode = ParserMode.PYTHON

    def parse(self, text: str, user_id: int) -> ParsingResult:
        try:
            preferences = self.user_preferences_repo.get_or_create_for_user(
                user_id=user_id,
                default_parser_mode=self.default_parser_mode,
            )
            parser_mode = preferences.parser_mode
        except ValueError:
            return self._parse_with_metadata(
                text=text,
                user_id=user_id,
                parser_mode=ParserMode.PYTHON,
                parser_router="python_fallback_invalid_preference",
            )

        if parser_mode is ParserMode.PYTHON:
            return self._parse_with_metadata(
                text=text,
                user_id=user_id,
                parser_mode=ParserMode.PYTHON,
                parser_router="python",
            )

        if parser_mode is ParserMode.AUTO:
            return self._parse_with_metadata(
                text=text,
                user_id=user_id,
                parser_mode=ParserMode.AUTO,
                parser_router="python_fallback",
                llm_fallback_available=False,
            )

        if parser_mode is ParserMode.LLM:
            return self._parse_with_metadata(
                text=text,
                user_id=user_id,
                parser_mode=ParserMode.LLM,
                parser_router="python_fallback_llm_not_implemented",
                llm_fallback_available=False,
            )

        return self._parse_with_metadata(
            text=text,
            user_id=user_id,
            parser_mode=ParserMode.PYTHON,
            parser_router="python_fallback_invalid_preference",
        )

    def _parse_with_metadata(
        self,
        *,
        text: str,
        user_id: int,
        parser_mode: ParserMode,
        parser_router: str,
        llm_fallback_available: bool | None = None,
    ) -> ParsingResult:
        result = self.python_parser.parse(text=text, user_id=user_id)

        metadata = dict(result.draft.metadata)
        metadata["parser_mode"] = parser_mode.value
        metadata["parser_router"] = parser_router
        if llm_fallback_available is not None:
            metadata["llm_fallback_available"] = str(llm_fallback_available).lower()

        result.draft.metadata = metadata
        return result
