from __future__ import annotations

from datetime import UTC, datetime

import pytest

from smart_life_bot.parsing.rule_based import RuleBasedMessageParser


FIXED_NOW = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)


def _parser(now: datetime = FIXED_NOW) -> RuleBasedMessageParser:
    return RuleBasedMessageParser(default_timezone="UTC", now_provider=lambda: now)


def test_parses_iso_date_time() -> None:
    result = _parser().parse("Созвон 2026-04-26 15:00", user_id=42)

    assert result.draft.title == "Созвон"
    assert result.draft.start_at == datetime(2026, 4, 26, 15, 0, tzinfo=UTC)
    assert result.draft.end_at is None
    assert result.draft.timezone == "UTC"


def test_parses_russian_date_time() -> None:
    result = _parser().parse("Созвон 26.04.2026 15:00", user_id=42)

    assert result.draft.title == "Созвон"
    assert result.draft.start_at == datetime(2026, 4, 26, 15, 0, tzinfo=UTC)
    assert result.draft.end_at is None


@pytest.mark.parametrize(
    ("text", "expected_start_at"),
    [
        ("Психотерапевт 27.04.26 15:00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("Психотерапевт 27.04.26, 15:00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("Психотерапевт 27.04.26 15 00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("Психотерапевт 27.04.26, 15 00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("Психотерапевт 27.04.2026, 15:00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("Психотерапевт 27.04.2026, 15 00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("Психотерапевт 27 апреля 2026 15:00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("Психотерапевт 27 апреля 26 15:00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("Психотерапевт 27 апреля 2026, 15 00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("Психотерапевт 27 апр 2026 15:00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("Психотерапевт 27 апр. 26, 15 00", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("27 апреля 2026 15:00 психотерапевт", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
        ("27 апр 26 15 00 психотерапевт", datetime(2026, 4, 27, 15, 0, tzinfo=UTC)),
    ],
)
def test_parses_compact_and_month_name_formats(text: str, expected_start_at: datetime) -> None:
    result = _parser().parse(text, user_id=42)

    assert result.draft.start_at == expected_start_at
    assert result.draft.end_at is None
    assert result.is_ambiguous is False


@pytest.mark.parametrize(
    ("text", "expected_title"),
    [
        ("Психотерапевт 27.04.26, 15 00", "Психотерапевт"),
        ("Психотерапевт 27 апреля 2026, 15:00", "Психотерапевт"),
        ("27 апреля 2026 15:00 психотерапевт", "психотерапевт"),
    ],
)
def test_clean_title_extraction_for_new_formats(text: str, expected_title: str) -> None:
    result = _parser().parse(text, user_id=42)

    assert result.draft.title == expected_title


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


def test_parses_relative_tomorrow_with_spaced_time() -> None:
    result = _parser().parse("завтра в 15 00 психотерапевт", user_id=42)

    assert result.draft.title == "психотерапевт"
    assert result.draft.start_at == datetime(2026, 4, 26, 15, 0, tzinfo=UTC)


def test_parses_today_time_with_spaced_time_separator() -> None:
    result = _parser().parse("в 15 00 психотерапевт", user_id=42)

    assert result.draft.title == "психотерапевт"
    assert result.draft.start_at == datetime(2026, 4, 25, 15, 0, tzinfo=UTC)


def test_month_name_without_year_uses_current_year_for_future_date() -> None:
    result = _parser(now=datetime(2026, 4, 1, 12, 0, tzinfo=UTC)).parse(
        "Психотерапевт 27 апреля, 15:00",
        user_id=42,
    )

    assert result.draft.start_at == datetime(2026, 4, 27, 15, 0, tzinfo=UTC)


def test_month_name_without_year_uses_next_year_for_past_date() -> None:
    result = _parser(now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC)).parse(
        "Психотерапевт 27 апреля, 15:00",
        user_id=42,
    )

    assert result.draft.start_at == datetime(2027, 4, 27, 15, 0, tzinfo=UTC)


def test_month_short_without_year_with_spaced_time() -> None:
    result = _parser(now=datetime(2026, 4, 1, 12, 0, tzinfo=UTC)).parse(
        "Психотерапевт 27 апр 15 00",
        user_id=42,
    )

    assert result.draft.title == "Психотерапевт"
    assert result.draft.start_at == datetime(2026, 4, 27, 15, 0, tzinfo=UTC)


def test_two_digit_year_uses_deterministic_century_mapping() -> None:
    twenty_six = _parser().parse("Психотерапевт 27.04.26 15:00", user_id=42)
    ninety_nine = _parser().parse("Психотерапевт 27.04.99 15:00", user_id=42)

    assert twenty_six.draft.start_at == datetime(2026, 4, 27, 15, 0, tzinfo=UTC)
    assert ninety_nine.draft.start_at == datetime(1999, 4, 27, 15, 0, tzinfo=UTC)


def test_no_default_duration_without_keyword() -> None:
    result = _parser().parse("в 15:00 созвон", user_id=42)

    assert result.draft.start_at == datetime(2026, 4, 25, 15, 0, tzinfo=UTC)
    assert result.draft.end_at is None


def test_duration_free_text_is_not_parsed_or_consumed_as_control_instruction() -> None:
    result = _parser().parse("завтра в 15:00 созвон длительность 30 минут", user_id=42)

    assert result.draft.title == "созвон длительность 30 минут"
    assert result.draft.start_at == datetime(2026, 4, 26, 15, 0, tzinfo=UTC)
    assert result.draft.end_at is None


def test_duration_free_text_in_hours_is_not_parsed() -> None:
    result = _parser().parse("послезавтра в 10:00 встреча длительность 2 часа", user_id=42)

    assert result.draft.title == "встреча длительность 2 часа"
    assert result.draft.start_at == datetime(2026, 4, 27, 10, 0, tzinfo=UTC)
    assert result.draft.end_at is None




def test_free_text_reminder_phrase_is_not_parsed_or_consumed() -> None:
    result = _parser().parse("Тест завтра в 15:00 уведомить за 10 минут", user_id=42)

    assert result.draft.start_at == datetime(2026, 4, 26, 15, 0, tzinfo=UTC)
    assert result.draft.reminder_minutes is None
    assert result.draft.title == "Тест уведомить за 10 минут"


def test_free_text_reminder_phrase_does_not_set_reminder_without_time() -> None:
    result = _parser().parse("уведомить за 10 минут", user_id=42)

    assert result.draft.start_at is None
    assert result.draft.reminder_minutes is None
    assert result.draft.title == "уведомить за 10 минут"


def test_title_falls_back_to_normalized_input_when_fully_consumed() -> None:
    result = _parser().parse("завтра в 15:00 длительность 30 минут", user_id=42)

    assert result.draft.title == "длительность 30 минут"


@pytest.mark.parametrize(
    "text",
    [
        "Психотерапевт 99.99.26 15 00",
        "Психотерапевт 31 февраля 2026 15:00",
        "Психотерапевт 27 апреля 2026 99 99",
    ],
)
def test_invalid_date_or_time_returns_ambiguous_parse_without_crash(text: str) -> None:
    result = _parser().parse(text, user_id=42)

    assert result.draft.start_at is None
    assert result.draft.end_at is None
    assert result.confidence == 0.3
    assert result.is_ambiguous is True
    assert result.issues == ["missing_start_at"]


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
