"""Deterministic rule-based parser baseline for MVP demo flows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from smart_life_bot.domain.models import EventDraft

from .models import ParsingResult

# Two-digit year mapping rule is intentionally deterministic:
# 00..69 -> 2000..2069, 70..99 -> 1970..1999.
_TWO_DIGIT_YEAR_THRESHOLD = 69

_MONTH_ALIASES: dict[str, int] = {
    "января": 1,
    "янв": 1,
    "февраля": 2,
    "фев": 2,
    "марта": 3,
    "мар": 3,
    "апреля": 4,
    "апр": 4,
    "мая": 5,
    "июня": 6,
    "июн": 6,
    "июля": 7,
    "июл": 7,
    "августа": 8,
    "авг": 8,
    "сентября": 9,
    "сен": 9,
    "сент": 9,
    "октября": 10,
    "окт": 10,
    "ноября": 11,
    "ноя": 11,
    "декабря": 12,
    "дек": 12,
}

_WEEKDAY_ALIASES: dict[str, int] = {
    "пн": 0,
    "понедельник": 0,
    "в понедельник": 0,
    "вт": 1,
    "вторник": 1,
    "во вторник": 1,
    "ср": 2,
    "среда": 2,
    "в среду": 2,
    "чт": 3,
    "четверг": 3,
    "в четверг": 3,
    "пт": 4,
    "пятница": 4,
    "в пятницу": 4,
    "сб": 5,
    "суббота": 5,
    "в субботу": 5,
    "вс": 6,
    "воскресенье": 6,
    "в воскресенье": 6,
}

_WEEKDAY_PATTERN = re.compile(
    r"\b(во\s+вторник|в\s+понедельник|в\s+среду|в\s+четверг|в\s+пятницу|в\s+субботу|в\s+воскресенье|понедельник|вторник|среда|четверг|пятница|суббота|воскресенье|пн|вт|ср|чт|пт|сб|вс)\b",
    flags=re.IGNORECASE,
)


@dataclass(slots=True)
class RuleBasedMessageParser:
    """Dependency-free parser for a narrow set of deterministic RU date/time rules."""

    default_timezone: str
    now_provider: Callable[[], datetime] | None = None

    def parse(self, text: str, user_id: int) -> ParsingResult:
        normalized = _normalize_text(text)
        timezone = self.default_timezone
        now = _resolve_now(self.default_timezone, self.now_provider)

        consumed_spans: list[tuple[int, int]] = []
        start_at, explicit_datetime_seen = _extract_explicit_datetime(normalized, timezone, now, consumed_spans)

        relative_day_offset: int | None = None
        weekday_target: int | None = None
        today_explicit = False
        if start_at is None and not explicit_datetime_seen:
            relative_match = re.search(r"\b(послезавтра|завтра|сегодня)\b", normalized, flags=re.IGNORECASE)
            if relative_match:
                consumed_spans.append(relative_match.span())
                token = relative_match.group(1).lower()
                if token == "сегодня":
                    relative_day_offset = 0
                    today_explicit = True
                elif token == "завтра":
                    relative_day_offset = 1
                elif token == "послезавтра":
                    relative_day_offset = 2

            if not today_explicit:
                weekday_match = _WEEKDAY_PATTERN.search(normalized)
                if weekday_match:
                    consumed_spans.append(weekday_match.span())
                    weekday_target = _WEEKDAY_ALIASES.get(weekday_match.group(1).lower())

            time_match = re.search(r"\b(?:в\s*)?(\d{1,2})(?::|\s)(\d{2})\b", normalized, flags=re.IGNORECASE)
            if time_match:
                consumed_spans.append(time_match.span())
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    date = now.date()
                    if relative_day_offset is not None:
                        date = date + timedelta(days=relative_day_offset)
                    elif weekday_target is not None:
                        delta = (weekday_target - date.weekday()) % 7
                        if delta == 0:
                            delta = 7
                        date = date + timedelta(days=delta)
                    start_at = datetime(
                        date.year,
                        date.month,
                        date.day,
                        hour,
                        minute,
                        tzinfo=ZoneInfo(timezone),
                    )

        title = _extract_title(normalized, consumed_spans)
        if not title:
            title = normalized or "Untitled event"

        end_at = None

        metadata = {
            "source": "rule-based-parser",
            "raw_text": normalized,
            "user_id": str(user_id),
        }

        if start_at is None:
            return ParsingResult(
                draft=EventDraft(
                    title=title,
                    start_at=None,
                    end_at=None,
                    timezone=timezone,
                    metadata=metadata,
                ),
                confidence=0.3,
                is_ambiguous=True,
                issues=["missing_start_at"],
            )

        return ParsingResult(
            draft=EventDraft(
                title=title,
                start_at=start_at,
                end_at=end_at,
                timezone=timezone,
                metadata=metadata,
            ),
            confidence=0.95,
            is_ambiguous=False,
            issues=[],
        )


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def _resolve_now(default_timezone: str, now_provider: Callable[[], datetime] | None) -> datetime:
    timezone = ZoneInfo(default_timezone)
    if now_provider is None:
        return datetime.now(timezone)

    now = now_provider()
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone)
    return now.astimezone(timezone)


def _extract_explicit_datetime(
    text: str,
    timezone: str,
    now: datetime,
    consumed_spans: list[tuple[int, int]],
) -> tuple[datetime | None, bool]:
    for pattern, parser in (
        (
            r"\b(\d{4})-(\d{2})-(\d{2})\s*,?\s*(\d{1,2})(?::|\s)(\d{2})\b",
            _parse_iso_datetime_match,
        ),
        (
            r"\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})\s*,?\s*(\d{1,2})(?::|\s)(\d{2})\b",
            _parse_dotted_datetime_match,
        ),
        (
            r"\b(\d{1,2})\s+([а-яё]+\.?)(?:\s+(\d{4}|\d{2}))?\s*,?\s*(\d{1,2})(?::|\s)(\d{2})\b",
            _parse_month_name_datetime_match,
        ),
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        consumed_spans.append(match.span())
        try:
            parsed = parser(match, timezone, now)
            return parsed, True
        except ValueError:
            return None, True
    return None, False


def _parse_iso_datetime_match(match: re.Match[str], timezone: str, now: datetime) -> datetime:
    del now
    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(timezone))


def _parse_dotted_datetime_match(match: re.Match[str], timezone: str, now: datetime) -> datetime:
    del now
    day = int(match.group(1))
    month = int(match.group(2))
    year = _parse_year_token(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(timezone))


def _parse_month_name_datetime_match(match: re.Match[str], timezone: str, now: datetime) -> datetime:
    day = int(match.group(1))
    month = _parse_month_token(match.group(2))
    year_token = match.group(3)
    hour = int(match.group(4))
    minute = int(match.group(5))

    if year_token is None:
        year = _resolve_year_for_month_without_year(now=now, month=month, day=day)
    else:
        year = _parse_year_token(year_token)

    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(timezone))


def _parse_year_token(year_token: str) -> int:
    value = int(year_token)
    if len(year_token) == 2:
        if value <= _TWO_DIGIT_YEAR_THRESHOLD:
            return 2000 + value
        return 1900 + value
    return value


def _parse_month_token(month_token: str) -> int:
    normalized_token = month_token.rstrip(".").lower()
    month = _MONTH_ALIASES.get(normalized_token)
    if month is None:
        raise ValueError("unsupported month token")
    return month


def _resolve_year_for_month_without_year(now: datetime, month: int, day: int) -> int:
    if (month, day) >= (now.month, now.day):
        return now.year
    return now.year + 1


def _extract_title(text: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return text

    ranges = sorted(spans, key=lambda item: item[0])
    chunks: list[str] = []
    cursor = 0

    for start, end in ranges:
        if start > cursor:
            chunks.append(text[cursor:start])
        cursor = max(cursor, end)
    if cursor < len(text):
        chunks.append(text[cursor:])

    title = " ".join("".join(chunks).split())
    return title.strip(" ,.-")


def _extract_keyword_minutes(text: str, keyword: str) -> tuple[int | None, tuple[int, int] | None]:
    pattern = rf"\b{keyword}\s+((?:\d+\s*час(?:а|ов)?\s*)?(?:\d+\s*минут(?:а|ы|у)?)?)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None, None
    value = match.group(1)
    hours_match = re.search(r"(\d+)\s*час(?:а|ов)?", value, flags=re.IGNORECASE)
    minutes_match = re.search(r"(\d+)\s*минут(?:а|ы|у)?", value, flags=re.IGNORECASE)
    hours = int(hours_match.group(1)) if hours_match else 0
    minutes = int(minutes_match.group(1)) if minutes_match else 0
    total = hours * 60 + minutes
    if total <= 0:
        return None, None
    return total, match.span()
