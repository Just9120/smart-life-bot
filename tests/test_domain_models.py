from smart_life_bot.domain.enums import ConversationState, GoogleAuthMode
from smart_life_bot.domain.models import ConversationStateSnapshot, EventDraft


def test_domain_models_import_and_construct() -> None:
    draft = EventDraft(title="Meeting")
    snapshot = ConversationStateSnapshot(user_id=1, state=ConversationState.IDLE, draft=draft)

    assert snapshot.draft is draft
    assert GoogleAuthMode.OAUTH_USER_MODE.value == "oauth_user_mode"
