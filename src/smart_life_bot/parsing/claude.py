"""Anthropic Claude-backed parser behind MessageParser abstraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from smart_life_bot.domain.models import EventDraft

from .models import ParsingResult


@dataclass(slots=True)
class ClaudeMessageParser:
    """LLM parser implementation using Anthropic Messages API."""

    model: str
    api_key: str
    default_timezone: str
    timeout_seconds: int
    max_retries: int
    max_tokens: int
    client: Any | None = None

    def parse(self, text: str, user_id: int) -> ParsingResult:
        normalized = " ".join(text.strip().split())
        metadata = {
            "source": "claude-parser",
            "raw_text": normalized,
            "user_id": str(user_id),
            "llm_provider": "anthropic",
            "llm_model": self.model,
            "llm_parser": "claude",
        }
        if not normalized:
            return self._failed_result(title="Untitled event", metadata=metadata)

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": _build_user_prompt(
                            text=normalized,
                            default_timezone=self.default_timezone,
                        ),
                    }
                ],
            )
            raw_payload = _extract_text_from_response(response)
            payload = json.loads(raw_payload)
            return _payload_to_parsing_result(
                payload=payload,
                normalized_text=normalized,
                default_timezone=self.default_timezone,
                metadata=metadata,
            )
        except Exception:  # noqa: BLE001
            return self._failed_result(title=normalized, metadata=metadata)

    @property
    def _client(self) -> Any:
        if self.client is None:
            try:
                from anthropic import Anthropic
            except ModuleNotFoundError as exc:
                raise RuntimeError("anthropic package is required for ClaudeMessageParser") from exc
            self.client = Anthropic(
                api_key=self.api_key,
                timeout=self.timeout_seconds,
                max_retries=self.max_retries,
            )
        return self.client

    def _failed_result(self, *, title: str, metadata: dict[str, str]) -> ParsingResult:
        failure_metadata = dict(metadata)
        failure_metadata["llm_error"] = "parse_failed"
        return ParsingResult(
            draft=EventDraft(
                title=title,
                start_at=None,
                end_at=None,
                timezone=self.default_timezone,
                metadata=failure_metadata,
            ),
            confidence=0.0,
            is_ambiguous=True,
            issues=["missing_start_at", "llm_parse_failed"],
        )


_SYSTEM_PROMPT = (
    "You parse calendar event text into strict JSON. "
    "Output JSON only, no markdown, no prose. "
    "Never include secrets."
)


def _build_user_prompt(*, text: str, default_timezone: str) -> str:
    return (
        "Input can be Russian or English. "
        "Use this JSON schema exactly: "
        '{"title":"string","start_at":"ISO-8601 datetime string or null",'
        '"end_at":"ISO-8601 datetime string or null","timezone":"IANA timezone string",'
        '"description":"string or null","location":"string or null",'
        '"is_ambiguous":true,"confidence":0.0,"issues":["string"]}. '
        "Rules: use default timezone when missing; do not invent date/time; "
        "if start is unclear set start_at=null,end_at=null,is_ambiguous=true and include missing_start_at; "
        "if duration is absent but start exists use 60 minutes. "
        f"Default timezone: {default_timezone}. "
        f"Input: {text}"
    )


def _extract_text_from_response(response: Any) -> str:
    content = getattr(response, "content", None)
    if not isinstance(content, list) or not content:
        raise ValueError("missing content")

    chunks: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            chunks.append(text)
    if not chunks:
        raise ValueError("text content is empty")
    return "\n".join(chunks)


def _parse_iso_datetime(value: str | None, *, timezone: str) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed


def _payload_to_parsing_result(
    *,
    payload: dict[str, Any],
    normalized_text: str,
    default_timezone: str,
    metadata: dict[str, str],
) -> ParsingResult:
    if not isinstance(payload, dict):
        raise ValueError("payload must be object")

    timezone_raw = payload.get("timezone")
    if not isinstance(timezone_raw, str) or not timezone_raw.strip():
        timezone = default_timezone
    else:
        timezone = timezone_raw.strip()

    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return _ambiguous_validation_result(
            issue="invalid_timezone",
            title=normalized_text,
            timezone=default_timezone,
            metadata=metadata,
        )

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        title = normalized_text

    start_at = _parse_iso_datetime(payload.get("start_at"), timezone=timezone)
    end_at = _parse_iso_datetime(payload.get("end_at"), timezone=timezone)
    if start_at is not None and end_at is not None and end_at <= start_at:
        return _ambiguous_validation_result(
            issue="invalid_time_range",
            title=title,
            timezone=timezone,
            metadata=metadata,
        )

    issues_raw = payload.get("issues")
    issues = [item for item in issues_raw if isinstance(item, str)] if isinstance(issues_raw, list) else []

    confidence_raw = payload.get("confidence")
    confidence = float(confidence_raw) if isinstance(confidence_raw, int | float) else 0.0
    confidence = max(0.0, min(confidence, 1.0))

    is_ambiguous = bool(payload.get("is_ambiguous"))
    if start_at is None and "missing_start_at" not in issues:
        issues.append("missing_start_at")
        is_ambiguous = True

    description = payload.get("description")
    if not isinstance(description, str):
        description = None

    location = payload.get("location")
    if not isinstance(location, str):
        location = None

    return ParsingResult(
        draft=EventDraft(
            title=title,
            start_at=start_at,
            end_at=end_at,
            timezone=timezone,
            description=description,
            location=location,
            metadata=dict(metadata),
        ),
        confidence=confidence,
        is_ambiguous=is_ambiguous,
        issues=issues,
    )


def _ambiguous_validation_result(
    *,
    issue: str,
    title: str,
    timezone: str,
    metadata: dict[str, str],
) -> ParsingResult:
    draft_metadata = dict(metadata)
    draft_metadata["llm_error"] = "validation_failed"
    return ParsingResult(
        draft=EventDraft(
            title=title,
            start_at=None,
            end_at=None,
            timezone=timezone,
            metadata=draft_metadata,
        ),
        confidence=0.0,
        is_ambiguous=True,
        issues=[issue, "missing_start_at"],
    )
