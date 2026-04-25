"""Deterministic rule-based parser baseline for MVP demo flows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from smart_life_bot.domain.models import EventDraft

from .models import ParsingResult

_DEFAULT_DURATION_MINUTES = 60


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
        start_at = _extract_explicit_datetime(normalized, timezone, consumed_spans)

        relative_day_offset: int | None = None
        if start_at is None:
            relative_match = re.search(r"\b(послезавтра|завтра|сегодня)\b", normalized, flags=re.IGNORECASE)
            if relative_match:
                consumed_spans.append(relative_match.span())
                token = relative_match.group(1).lower()
                if token == "сегодня":
                    relative_day_offset = 0
                elif token == "завтра":
                    relative_day_offset = 1
                elif token == "послезавтра":
                    relative_day_offset = 2

            time_match = re.search(r"\b(?:в\s*)?(\d{1,2}):(\d{2})\b", normalized, flags=re.IGNORECASE)
            if time_match:
                consumed_spans.append(time_match.span())
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    date = now.date()
                    if relative_day_offset is not None:
                        date = date + timedelta(days=relative_day_offset)
                    start_at = datetime(
                        date.year,
                        date.month,
                        date.day,
                        hour,
                        minute,
                        tzinfo=ZoneInfo(timezone),
                    )

        duration_minutes = _DEFAULT_DURATION_MINUTES
        duration_match = re.search(
            r"\bна\s+(?:(\d+)\s*минут(?:у|ы)?|(\d+)\s*час(?:а|ов)?)\b",
            normalized,
            flags=re.IGNORECASE,
        )
        if duration_match:
            consumed_spans.append(duration_match.span())
            minutes = duration_match.group(1)
            hours = duration_match.group(2)
            if minutes is not None:
                duration_minutes = int(minutes)
            elif hours is not None:
                duration_minutes = int(hours) * 60

        title = _extract_title(normalized, consumed_spans)
        if not title:
            title = normalized or "Untitled event"

        end_at = start_at + timedelta(minutes=duration_minutes) if start_at is not None else None

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
    consumed_spans: list[tuple[int, int]],
) -> datetime | None:
    for pattern, order in (
        (r"\b(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})\b", (1, 2, 3, 4, 5)),
        (r"\b(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})\b", (3, 2, 1, 4, 5)),
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        consumed_spans.append(match.span())
        try:
            year = int(match.group(order[0]))
            month = int(match.group(order[1]))
            day = int(match.group(order[2]))
            hour = int(match.group(order[3]))
            minute = int(match.group(order[4]))
            return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(timezone))
        except ValueError:
            return None
    return None


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
