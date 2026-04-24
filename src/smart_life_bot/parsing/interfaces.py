"""Message parser interface."""

from typing import Protocol

from .models import ParsingResult


class MessageParser(Protocol):
    def parse(self, text: str, user_id: int) -> ParsingResult: ...
