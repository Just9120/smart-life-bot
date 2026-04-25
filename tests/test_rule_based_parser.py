from __future__ import annotations

from datetime import UTC, datetime

from smart_life_bot.parsing.rule_based import RuleBasedMessageParser


FIXED_NOW = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)


def _parser() -> RuleBasedMessageParser:
    return RuleBasedMessageParser(default_timezone="UTC", now_provider=lambda: FIXED_NOW)


def test_parses_iso_date_time() -> None:
    result = _parser().parse("Созвон 2026-04-26 15:00", user_id=42)

    assert result.draft.title == "Созвон"
    assert result.draft.start_at == datetime(2026, 4, 26, 15, 0, tzinfo=UTC)
    assert result.draft.end_at == datetime(2026, 4, 26, 16, 0, tzinfo=UTC)
    assert result.draft.timezone == "UTC"


def test_parses_russian_date_time() -> None:
    result = _parser().parse("Созвон 26.04.2026 15:00", user_id=42)

    assert result.draft.title == "Созвон"
    assert result.draft.start_at == datetime(2026, 4, 26, 15, 0, tzinfo=UTC)
    assert result.draft.end_at == datetime(2026, 4, 26, 16, 0, tzinfo=UTC)


def test_parses_relative_tomorrow() -> None:
    result = _parser().parse("завтра в 15:00 созвон", user_id=42)

    assert result.draft.title == "созвон"
    assert result.draft.start_at == datetime(2026, 4, 26, 15, 0, tzinfo=UTC)


def test_parses_relative_today() -> None:
    result = _parser().parse("сегодня в 18:30 тренировка", user_id=42)

    assert result.draft.title == "тренировка"
    assert result.draft.start_at == datetime(2026, 4, 25, 18, 30, tzinfo=UTC)


def test_parses_relative_day_after_tomorrow() -> None:
    result = _parser().parse("послезавтра в 10:00 встреча", user_id=42)

    assert result.draft.title == "встреча"
    assert result.draft.start_at == datetime(2026, 4, 27, 10, 0, tzinfo=UTC)


def test_uses_default_60_minute_duration() -> None:
    result = _parser().parse("в 15:00 созвон", user_id=42)

    assert result.draft.start_at == datetime(2026, 4, 25, 15, 0, tzinfo=UTC)
    assert result.draft.end_at == datetime(2026, 4, 25, 16, 0, tzinfo=UTC)


def test_parses_duration_in_minutes() -> None:
    result = _parser().parse("завтра в 15:00 созвон на 30 минут", user_id=42)

    assert result.draft.title == "созвон"
    assert result.draft.start_at == datetime(2026, 4, 26, 15, 0, tzinfo=UTC)
    assert result.draft.end_at == datetime(2026, 4, 26, 15, 30, tzinfo=UTC)


def test_parses_duration_in_hours() -> None:
    result = _parser().parse("послезавтра в 10:00 встреча на 2 часа", user_id=42)

    assert result.draft.title == "встреча"
    assert result.draft.start_at == datetime(2026, 4, 27, 10, 0, tzinfo=UTC)
    assert result.draft.end_at == datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


def test_title_falls_back_to_normalized_input_when_fully_consumed() -> None:
    result = _parser().parse("завтра в 15:00 на 30 минут", user_id=42)

    assert result.draft.title == "завтра в 15:00 на 30 минут"


def test_returns_ambiguous_result_when_start_time_missing() -> None:
    result = _parser().parse("просто созвон без времени", user_id=42)

    assert result.draft.start_at is None
    assert result.draft.end_at is None
    assert result.draft.timezone == "UTC"
    assert result.confidence == 0.3
    assert result.is_ambiguous is True
    assert result.issues == ["missing_start_at"]
    assert result.draft.metadata == {
        "source": "rule-based-parser",
        "raw_text": "просто созвон без времени",
        "user_id": "42",
    }
