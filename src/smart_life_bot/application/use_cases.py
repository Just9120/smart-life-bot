"""Skeleton use-cases for Phase 1 event capture flow."""

from __future__ import annotations

from dataclasses import dataclass

from smart_life_bot.domain.enums import ConversationState
from smart_life_bot.domain.models import ConversationStateSnapshot

from .dto import (
    CancelEventDraftInput,
    ConfirmEventDraftInput,
    EditEventDraftFieldInput,
    IncomingMessageInput,
    UseCaseResult,
)
from .interfaces import ApplicationDependencies


@dataclass(slots=True)
class ProcessIncomingMessageUseCase:
    deps: ApplicationDependencies

    def execute(self, payload: IncomingMessageInput) -> UseCaseResult:
        parsing_result = self.deps.parser.parse(text=payload.text, user_id=payload.user_id)
        snapshot = ConversationStateSnapshot(
            user_id=payload.user_id,
            state=ConversationState.WAITING_PREVIEW_CONFIRMATION,
            draft=parsing_result.draft,
        )
        self.deps.state_repo.set(snapshot)
        return UseCaseResult(status="preview_ready", message="Event draft prepared for preview")


@dataclass(slots=True)
class ConfirmEventDraftUseCase:
    deps: ApplicationDependencies

    def execute(self, payload: ConfirmEventDraftInput) -> UseCaseResult:
        # TODO: implement full confirm flow with auth/calendar integration.
        self.deps.state_repo.set(
            ConversationStateSnapshot(
                user_id=payload.user_id,
                state=ConversationState.SAVING,
            )
        )
        return UseCaseResult(status="pending", message="Event save flow is pending implementation")


@dataclass(slots=True)
class EditEventDraftFieldUseCase:
    deps: ApplicationDependencies

    def execute(self, payload: EditEventDraftFieldInput) -> UseCaseResult:
        # TODO: apply draft field mutation and re-generate preview.
        self.deps.logger.info(
            "Edit draft placeholder invoked",
            user_id=payload.user_id,
            field_name=payload.field_name,
        )
        return UseCaseResult(status="pending", message="Draft editing is pending implementation")


@dataclass(slots=True)
class CancelEventDraftUseCase:
    deps: ApplicationDependencies

    def execute(self, payload: CancelEventDraftInput) -> UseCaseResult:
        self.deps.state_repo.reset(payload.user_id)
        return UseCaseResult(status="cancelled", message="Draft cancelled and state reset to IDLE")
