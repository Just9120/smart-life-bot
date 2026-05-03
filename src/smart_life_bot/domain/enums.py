"""Domain enums for state transitions and statuses."""

from enum import Enum


class ConversationState(str, Enum):
    IDLE = "IDLE"
    WAITING_PREVIEW_CONFIRMATION = "WAITING_PREVIEW_CONFIRMATION"
    EDITING_FIELD = "EDITING_FIELD"
    SAVING = "SAVING"


class GoogleAuthMode(str, Enum):
    OAUTH_USER_MODE = "oauth_user_mode"
    SERVICE_ACCOUNT_SHARED_CALENDAR_MODE = "service_account_shared_calendar_mode"


class ParserMode(str, Enum):
    PYTHON = "python"
    AUTO = "auto"
    LLM = "llm"


class EventLogStatus(str, Enum):
    RECEIVED = "received"
    PREVIEW_READY = "preview_ready"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    SAVED = "saved"
    FAILED = "failed"


class EventLogErrorCategory(str, Enum):
    PARSING_AMBIGUITY = "parsing_ambiguity"
    VALIDATION_ERROR = "validation_error"
    MISSING_AUTH = "missing_auth"
    PROVIDER_AUTH_FAILURE = "provider_auth_failure"
    CALENDAR_WRITE_FAILURE = "calendar_write_failure"
    STATE_INCONSISTENCY = "state_inconsistency"
    INTERNAL_ERROR = "internal_error"


class OAuthConnectionStatus(str, Enum):
    NOT_CONNECTED = "not_connected"
    PENDING = "pending"
    CONNECTED = "connected"
    ERROR = "error"
