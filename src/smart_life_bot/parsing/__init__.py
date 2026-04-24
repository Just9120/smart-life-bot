"""Parsing abstraction layer."""

from .interfaces import MessageParser
from .models import ParsingResult

__all__ = ["MessageParser", "ParsingResult"]
