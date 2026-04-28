"""Use-cases for Phase 1 event capture flow."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from smart_life_bot.calendar.models import CalendarEventCreateRequest
from smart_life_bot.domain.enums import ConversationState, EventLogErrorCategory, EventLogStatus, ParserMode
from smart_life_bot.domain.models import ConversationStateSnapshot, EventDraft
from smart_life_bot.storage.interfaces import EventLogEntry, UserPreferencesRecord

from .draft_validation import require_valid_draft
from .dto import (
    CancelEventDraftInput,
    ConfirmEventDraftInput,
    EditEventDraftFieldInput,
    IncomingMessageInput,
    UseCaseResult,
)
from .interfaces import ApplicationDependencies


def _normalized_parser_metadata(parsing_result_confidence: float, parsing_result_is_ambiguous: bool, parsing_result_issues: list[str]) -> dict[str, str]:
    return {
        "parser_confidence": f"{parsing_result_confidence:.2f}",
        "parser_is_ambiguous": str(parsing_result_is_ambiguous).lower(),
        "parser_issues": ",".join(parsing_result_issues),
    }


def _draft_to_payload(draft: EventDraft) -> dict[str, object]:
    return {
        "title": draft.title,
        "start_at": draft.start_at.isoformat() if draft.start_at else None,
        "end_at": draft.end_at.isoformat() if draft.end_at else None,
        "timezone": draft.timezone,
        "description": draft.description,
        "location": draft.location,
        "metadata": draft.metadata,
    }


def _extract_event_log_id(draft: EventDraft | None) -> int | None:
    if draft is None:
        return None

    value = draft.metadata.get("event_log_id")
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _require_valid_event_log_id(draft: EventDraft) -> int | None:
    value = draft.metadata.get("event_log_id")
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError("Malformed event_log_id in pending draft metadata") from error


def _parse_datetime_field(value: str, field_name: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Invalid datetime format for '{field_name}'") from error


def _clone_draft_with_update(draft: EventDraft, **changes: object) -> EventDraft:
    updated_draft = replace(draft, **changes)
    updated_draft.metadata = dict(draft.metadata)
    return updated_draft


def _apply_draft_field_edit(draft: EventDraft, field_name: str, field_value: str) -> EventDraft:
    if field_name == "title":
        normalized = field_value.strip()
        if not normalized:
            raise ValueError("Title must be a non-empty string")
        return _clone_draft_with_update(draft, title=normalized)

    if field_name == "start_at":
        normalized = field_value.strip()
        if not normalized:
            raise ValueError("start_at must be a non-empty ISO-8601 datetime")
        parsed = _parse_datetime_field(normalized, field_name)
        return _clone_draft_with_update(draft, start_at=parsed)

    if field_name == "end_at":
        normalized = field_value.strip()
        if not normalized:
            return _clone_draft_with_update(draft, end_at=None)
        parsed = _parse_datetime_field(normalized, field_name)
        return _clone_draft_with_update(draft, end_at=parsed)

    if field_name == "timezone":
        normalized = field_value.strip()
        if not normalized:
            raise ValueError("Timezone must be a non-empty string")
        return _clone_draft_with_update(draft, timezone=normalized)

    if field_name == "description":
        normalized = field_value.strip()
        if not normalized:
            return _clone_draft_with_update(draft, description=None)
        return _clone_draft_with_update(draft, description=field_value)

    if field_name == "location":
        normalized = field_value.strip()
        if not normalized:
            return _clone_draft_with_update(draft, location=None)
        return _clone_draft_with_update(draft, location=field_value)

    raise ValueError(f"Unsupported editable field '{field_name}'")


@dataclass(slots=True)
class ProcessIncomingMessageUseCase:
    deps: ApplicationDependencies

    def execute(self, payload: IncomingMessageInput) -> UseCaseResult:
        parsing_result = self.deps.parser.parse(text=payload.text, user_id=payload.user_id)
        draft = parsing_result.draft
        parser_metadata = _normalized_parser_metadata(
            parsing_result_confidence=parsing_result.confidence,
            parsing_result_is_ambiguous=parsing_result.is_ambiguous,
            parsing_result_issues=parsing_result.issues,
        )
        draft.metadata = {**draft.metadata, **parser_metadata}

        log_entry = self.deps.events_log_repo.append(
            EventLogEntry(
                id=None,
                user_id=payload.user_id,
                raw_text=payload.text,
                parsed_payload=_draft_to_payload(draft),
                status=EventLogStatus.RECEIVED,
            )
        )
        if log_entry.id is not None:
            self.deps.events_log_repo.update_status(
                entry_id=log_entry.id,
                status=EventLogStatus.PREVIEW_READY,
            )
            draft.metadata["event_log_id"] = str(log_entry.id)

        snapshot = ConversationStateSnapshot(
            user_id=payload.user_id,
            state=ConversationState.WAITING_PREVIEW_CONFIRMATION,
            draft=draft,
        )
        self.deps.state_repo.set(snapshot)
        return UseCaseResult(status="preview_ready", message="Event draft prepared for preview")


@dataclass(slots=True)
class ConfirmEventDraftUseCase:
    deps: ApplicationDependencies

    def execute(self, payload: ConfirmEventDraftInput) -> UseCaseResult:
        snapshot = self.deps.state_repo.get(payload.user_id)
        if snapshot is None or snapshot.state is not ConversationState.WAITING_PREVIEW_CONFIRMATION:
            return UseCaseResult(status="failed", message="No pending draft for confirmation")

        if snapshot.draft is None:
            return UseCaseResult(status="failed", message="Pending state has no draft payload")

        draft = snapshot.draft
        try:
            log_id = _require_valid_event_log_id(draft)
        except Exception as error:  # noqa: BLE001
            log_id = _extract_event_log_id(draft)
            if log_id is not None:
                self.deps.events_log_repo.update_status(
                    entry_id=log_id,
                    status=EventLogStatus.FAILED,
                    error_category=EventLogErrorCategory.INTERNAL_ERROR,
                    error_details=str(error),
                )
            self.deps.state_repo.set(
                ConversationStateSnapshot(
                    user_id=payload.user_id,
                    state=ConversationState.WAITING_PREVIEW_CONFIRMATION,
                    draft=draft,
                )
            )
            self.deps.logger.error("Confirm flow failed", user_id=payload.user_id, error=str(error))
            return UseCaseResult(status="failed", message="Event creation failed")

        try:
            require_valid_draft(draft, require_start_at=True)
        except ValueError as error:
            if log_id is not None:
                self.deps.events_log_repo.update_status(
                    entry_id=log_id,
                    status=EventLogStatus.FAILED,
                    error_category=EventLogErrorCategory.VALIDATION_ERROR,
                    error_details=str(error),
                )
            self.deps.state_repo.set(
                ConversationStateSnapshot(
                    user_id=payload.user_id,
                    state=ConversationState.WAITING_PREVIEW_CONFIRMATION,
                    draft=draft,
                )
            )
            return UseCaseResult(status="failed", message=str(error))

        self.deps.state_repo.set(
            ConversationStateSnapshot(
                user_id=payload.user_id,
                state=ConversationState.SAVING,
                draft=draft,
            )
        )
        try:
            if log_id is not None:
                self.deps.events_log_repo.update_status(entry_id=log_id, status=EventLogStatus.CONFIRMED)
            auth_context = self.deps.auth_provider.resolve_auth_context(user_id=payload.user_id)
            request = CalendarEventCreateRequest(
                title=draft.title,
                start_at_iso=draft.start_at.isoformat() if draft.start_at else "",
                end_at_iso=draft.end_at.isoformat() if draft.end_at else None,
                timezone=draft.timezone or "UTC",
                description=draft.description,
                location=draft.location,
            )
            calendar_result = self.deps.calendar_service.create_event(
                auth_context=auth_context,
                request=request,
            )
        except Exception as error:  # noqa: BLE001
            log_id = _extract_event_log_id(draft)
            if log_id is not None:
                self.deps.events_log_repo.update_status(
                    entry_id=log_id,
                    status=EventLogStatus.FAILED,
                    error_category=EventLogErrorCategory.INTERNAL_ERROR,
                    error_details=str(error),
                )
            self.deps.state_repo.set(
                ConversationStateSnapshot(
                    user_id=payload.user_id,
                    state=ConversationState.WAITING_PREVIEW_CONFIRMATION,
                    draft=draft,
                )
            )
            self.deps.logger.error("Confirm flow failed", user_id=payload.user_id, error=str(error))
            return UseCaseResult(status="failed", message="Event creation failed")

        if log_id is not None:
            self.deps.events_log_repo.update_status(
                entry_id=log_id,
                status=EventLogStatus.SAVED,
                google_event_id=calendar_result.provider_event_id,
            )

        self.deps.state_repo.reset(payload.user_id)
        return UseCaseResult(
            status="success",
            message="Event created successfully",
            provider_event_id=calendar_result.provider_event_id,
            provider_event_html_link=calendar_result.html_link,
        )


@dataclass(slots=True)
class EditEventDraftFieldUseCase:
    deps: ApplicationDependencies

    def execute(self, payload: EditEventDraftFieldInput) -> UseCaseResult:
        snapshot = self.deps.state_repo.get(payload.user_id)
        if snapshot is None:
            return UseCaseResult(status="failed", message="No pending draft for editing")

        if snapshot.state is not ConversationState.WAITING_PREVIEW_CONFIRMATION:
            return UseCaseResult(status="failed", message="Draft editing is unavailable in current state")

        if snapshot.draft is None:
            return UseCaseResult(status="failed", message="Pending state has no draft payload")

        try:
            updated_draft = _apply_draft_field_edit(
                draft=snapshot.draft,
                field_name=payload.field_name,
                field_value=payload.field_value,
            )
            require_valid_draft(updated_draft, require_start_at=False)
        except ValueError as error:
            return UseCaseResult(status="failed", message=str(error))

        self.deps.state_repo.set(
            ConversationStateSnapshot(
                user_id=payload.user_id,
                state=ConversationState.WAITING_PREVIEW_CONFIRMATION,
                draft=updated_draft,
            )
        )
        self.deps.logger.info(
            "Draft field updated",
            user_id=payload.user_id,
            field_name=payload.field_name,
        )
        return UseCaseResult(status="preview_ready", message="Draft updated and ready for preview")


@dataclass(slots=True)
class CancelEventDraftUseCase:
    deps: ApplicationDependencies

    def execute(self, payload: CancelEventDraftInput) -> UseCaseResult:
        snapshot = self.deps.state_repo.get(payload.user_id)
        log_id = _extract_event_log_id(snapshot.draft if snapshot is not None else None)
        if log_id is not None:
            self.deps.events_log_repo.update_status(entry_id=log_id, status=EventLogStatus.CANCELLED)
        self.deps.state_repo.reset(payload.user_id)
        return UseCaseResult(status="cancelled", message="Draft cancelled and state reset to IDLE")


@dataclass(frozen=True, slots=True)
class GetUserSettingsResult:
    parser_mode: ParserMode


@dataclass(slots=True)
class GetUserSettingsUseCase:
    deps: ApplicationDependencies
    default_parser_mode: ParserMode = ParserMode.PYTHON

    def execute(self, *, user_id: int) -> GetUserSettingsResult:
        preferences = self.deps.user_preferences_repo.get_or_create_for_user(
            user_id=user_id,
            default_parser_mode=self.default_parser_mode,
        )
        return GetUserSettingsResult(parser_mode=preferences.parser_mode)


@dataclass(slots=True)
class SetParserModeUseCase:
    deps: ApplicationDependencies
    llm_available: bool = False

    def execute(self, *, user_id: int, parser_mode: ParserMode) -> tuple[UseCaseResult, UserPreferencesRecord]:
        current = self.deps.user_preferences_repo.get_or_create_for_user(
            user_id=user_id,
            default_parser_mode=ParserMode.PYTHON,
        )

        if parser_mode is ParserMode.LLM and not self.llm_available:
            return (
                UseCaseResult(
                    status="not_available",
                    message=(
                        "LLM parser is not available in current runtime configuration. "
                        f"Current parser mode remains {current.parser_mode.value}."
                    ),
                ),
                current,
            )

        updated = self.deps.user_preferences_repo.set_parser_mode(user_id=user_id, parser_mode=parser_mode)
        if parser_mode is ParserMode.AUTO:
            message = "Parser mode updated to Auto. "
            if self.llm_available:
                message += "Auto now uses Python first and Claude fallback for ambiguous cases."
            else:
                message += "Auto currently uses Python/rule-based fallback because LLM is not configured."
            return UseCaseResult(status="success", message=message), updated

        if parser_mode is ParserMode.LLM:
            return UseCaseResult(status="success", message="LLM parser mode is active (Claude)."), updated

        return UseCaseResult(status="success", message="Python/rule-based parser is active."), updated
