"""Application-level draft validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from smart_life_bot.domain.models import EventDraft


@dataclass(frozen=True, slots=True)
class DraftValidationIssue:
    code: str
    message: str
    preview_hint: str


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def detect_draft_validation_issue(draft: EventDraft, *, require_start_at: bool) -> DraftValidationIssue | None:
    if require_start_at and draft.start_at is None:
        return DraftValidationIssue(
            code="missing_start_at",
            message="Cannot confirm event: start time is required before saving.",
            preview_hint="Нужно указать start_at перед созданием события. Используйте /edit start_at <ISO-8601 datetime>.",
        )

    timezone_value = draft.timezone
    if timezone_value is None or not timezone_value.strip():
        return DraftValidationIssue(
            code="invalid_timezone",
            message="Cannot confirm event: timezone must be a valid IANA timezone (for example Europe/Amsterdam).",
            preview_hint="Нужно указать валидный timezone. Используйте /edit timezone Europe/Amsterdam.",
        )

    try:
        ZoneInfo(timezone_value)
    except ZoneInfoNotFoundError:
        return DraftValidationIssue(
            code="invalid_timezone",
            message="Cannot confirm event: timezone must be a valid IANA timezone (for example Europe/Amsterdam).",
            preview_hint="Нужно указать валидный timezone. Используйте /edit timezone Europe/Amsterdam.",
        )

    if draft.start_at is not None and draft.end_at is not None:
        start_is_aware = _is_timezone_aware(draft.start_at)
        end_is_aware = _is_timezone_aware(draft.end_at)
        if start_is_aware != end_is_aware:
            return DraftValidationIssue(
                code="mixed_datetime_awareness",
                message=(
                    "Cannot confirm event: start_at and end_at must both be timezone-aware "
                    "or both timezone-naive."
                ),
                preview_hint=(
                    "start_at и end_at должны быть в одном формате timezone-awareness. "
                    "Отредактируйте даты в согласованном ISO-8601 формате."
                ),
            )
        if draft.end_at <= draft.start_at:
            return DraftValidationIssue(
                code="invalid_time_range",
                message="Cannot confirm event: end_at must be later than start_at.",
                preview_hint="end_at должен быть позже start_at.",
            )

    return None


def require_valid_draft(draft: EventDraft, *, require_start_at: bool) -> None:
    issue = detect_draft_validation_issue(draft, require_start_at=require_start_at)
    if issue is not None:
        raise ValueError(issue.message)
