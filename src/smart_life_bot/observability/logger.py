"""Minimal logger helpers for runtime foundation stage."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass


def get_logger(name: str = "smart_life_bot") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


@dataclass(slots=True)
class ContextLoggerAdapter:
    """Adapter that accepts arbitrary context kwargs in logger calls."""

    logger: logging.Logger

    def info(self, message: str, **extra: object) -> None:
        self._log(logging.INFO, message, **extra)

    def warning(self, message: str, **extra: object) -> None:
        self._log(logging.WARNING, message, **extra)

    def error(self, message: str, **extra: object) -> None:
        self._log(logging.ERROR, message, **extra)

    def _log(self, level: int, message: str, **extra: object) -> None:
        context = _safe_context(extra)
        if context:
            rendered_context = json.dumps(context, ensure_ascii=False, sort_keys=True)
            self.logger.log(level, "%s | context=%s", message, rendered_context)
            return
        self.logger.log(level, message)


def get_context_logger(name: str = "smart_life_bot") -> ContextLoggerAdapter:
    """Return context-aware logger adapter for application use-cases."""
    return ContextLoggerAdapter(logger=get_logger(name=name))


def _safe_context(extra: dict[str, object]) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, value in extra.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
            continue
        safe[key] = repr(value)
    return safe
