"""Models for parsing pipeline outputs."""

from dataclasses import dataclass, field

from smart_life_bot.domain.models import EventDraft


@dataclass(frozen=True, slots=True)
class ParsingResult:
    draft: EventDraft
    confidence: float
    is_ambiguous: bool
    issues: list[str] = field(default_factory=list)
