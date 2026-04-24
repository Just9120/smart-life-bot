"""Observability model constants and enums."""

from enum import Enum


class ErrorCategory(str, Enum):
    PARSING_AMBIGUITY = "parsing_ambiguity"
    VALIDATION_ERROR = "validation_error"
    MISSING_AUTH = "missing_auth"
    PROVIDER_AUTH_FAILURE = "provider_auth_failure"
    CALENDAR_WRITE_FAILURE = "calendar_write_failure"
    STATE_INCONSISTENCY = "state_inconsistency"
    INTERNAL_ERROR = "internal_error"
