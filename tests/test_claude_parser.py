from __future__ import annotations

import json

from smart_life_bot.parsing.claude import ClaudeMessageParser


class _FakeResponseBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeResponseBlock(text)]


class _FakeMessagesClient:
    def __init__(self, response_text: str) -> None:
        self.calls: list[dict[str, object]] = []
        self.response_text = response_text

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self.response_text)


class _FakeAnthropicClient:
    def __init__(self, response_text: str) -> None:
        self.messages = _FakeMessagesClient(response_text)


def test_claude_parser_converts_valid_json_response() -> None:
    payload = {
        "title": "Командный синк",
        "start_at": "2026-05-01T10:00:00+00:00",
        "end_at": None,
        "timezone": "UTC",
        "description": "Weekly",
        "location": "Zoom",
        "is_ambiguous": False,
        "confidence": 0.88,
        "issues": [],
    }
    client = _FakeAnthropicClient(json.dumps(payload))
    parser = ClaudeMessageParser(
        model="claude-haiku-4-5-20251001",
        api_key="test",
        default_timezone="UTC",
        timeout_seconds=20,
        max_retries=2,
        max_tokens=1000,
        client=client,
    )

    result = parser.parse("Синк завтра в 10:00", user_id=42)

    assert result.draft.title == "Командный синк"
    assert result.draft.start_at is not None
    assert result.draft.end_at is None
    assert result.draft.metadata["source"] == "claude-parser"
    assert result.draft.metadata["llm_provider"] == "anthropic"
    assert result.draft.metadata["llm_model"] == "claude-haiku-4-5-20251001"


def test_claude_parser_returns_ambiguous_on_invalid_json() -> None:
    client = _FakeAnthropicClient("not json")
    parser = ClaudeMessageParser(
        model="claude-haiku-4-5-20251001",
        api_key="test",
        default_timezone="UTC",
        timeout_seconds=20,
        max_retries=2,
        max_tokens=1000,
        client=client,
    )

    result = parser.parse("Bad response", user_id=77)

    assert result.is_ambiguous is True
    assert "missing_start_at" in result.issues
    assert result.draft.metadata["source"] == "claude-parser"
    assert result.draft.metadata["llm_error"] == "parse_failed"


def test_claude_parser_returns_ambiguous_on_invalid_timezone() -> None:
    payload = {
        "title": "Sync",
        "start_at": "2026-05-01T10:00:00+00:00",
        "end_at": "2026-05-01T11:00:00+00:00",
        "timezone": "Mars/Olympus",
        "description": None,
        "location": None,
        "is_ambiguous": False,
        "confidence": 0.9,
        "issues": [],
    }
    parser = ClaudeMessageParser(
        model="claude-haiku-4-5-20251001",
        api_key="test",
        default_timezone="UTC",
        timeout_seconds=20,
        max_retries=2,
        max_tokens=1000,
        client=_FakeAnthropicClient(json.dumps(payload)),
    )

    result = parser.parse("Team sync", user_id=10)

    assert result.is_ambiguous is True
    assert result.draft.start_at is None
    assert result.draft.end_at is None
    assert "invalid_timezone" in result.issues


def test_claude_parser_returns_ambiguous_on_malformed_timezone_key() -> None:
    payload = {
        "title": "Sync",
        "start_at": "2026-05-01T10:00:00+00:00",
        "end_at": "2026-05-01T11:00:00+00:00",
        "timezone": "/UTC",
        "description": None,
        "location": None,
        "is_ambiguous": False,
        "confidence": 0.9,
        "issues": [],
    }
    parser = ClaudeMessageParser(
        model="claude-haiku-4-5-20251001",
        api_key="test",
        default_timezone="UTC",
        timeout_seconds=20,
        max_retries=2,
        max_tokens=1000,
        client=_FakeAnthropicClient(json.dumps(payload)),
    )

    result = parser.parse("Team sync", user_id=10)

    assert result.is_ambiguous is True
    assert "invalid_timezone" in result.issues
    assert "llm_parse_failed" not in result.issues


def test_claude_parser_returns_ambiguous_when_end_at_is_before_start_at() -> None:
    payload = {
        "title": "Sync",
        "start_at": "2026-05-01T11:00:00+00:00",
        "end_at": "2026-05-01T10:00:00+00:00",
        "timezone": "UTC",
        "description": None,
        "location": None,
        "is_ambiguous": False,
        "confidence": 0.9,
        "issues": [],
    }
    parser = ClaudeMessageParser(
        model="claude-haiku-4-5-20251001",
        api_key="test",
        default_timezone="UTC",
        timeout_seconds=20,
        max_retries=2,
        max_tokens=1000,
        client=_FakeAnthropicClient(json.dumps(payload)),
    )

    result = parser.parse("Team sync", user_id=10)

    assert result.is_ambiguous is True
    assert "invalid_time_range" in result.issues


def test_claude_parser_returns_ambiguous_when_end_at_equals_start_at() -> None:
    payload = {
        "title": "Sync",
        "start_at": "2026-05-01T10:00:00+00:00",
        "end_at": "2026-05-01T10:00:00+00:00",
        "timezone": "UTC",
        "description": None,
        "location": None,
        "is_ambiguous": False,
        "confidence": 0.9,
        "issues": [],
    }
    parser = ClaudeMessageParser(
        model="claude-haiku-4-5-20251001",
        api_key="test",
        default_timezone="UTC",
        timeout_seconds=20,
        max_retries=2,
        max_tokens=1000,
        client=_FakeAnthropicClient(json.dumps(payload)),
    )

    result = parser.parse("Team sync", user_id=10)

    assert result.is_ambiguous is True
    assert "invalid_time_range" in result.issues
