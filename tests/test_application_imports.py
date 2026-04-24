from smart_life_bot.application.interfaces import ApplicationDependencies
from smart_life_bot.application.use_cases import (
    CancelEventDraftUseCase,
    ConfirmEventDraftUseCase,
    EditEventDraftFieldUseCase,
    ProcessIncomingMessageUseCase,
)


def test_application_contracts_import() -> None:
    assert ApplicationDependencies is not None
    assert ProcessIncomingMessageUseCase is not None
    assert ConfirmEventDraftUseCase is not None
    assert EditEventDraftFieldUseCase is not None
    assert CancelEventDraftUseCase is not None
