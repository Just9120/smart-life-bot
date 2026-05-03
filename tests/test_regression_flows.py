from __future__ import annotations

from datetime import date

from smart_life_bot.bot import (
    CALLBACK_CONFIRM,
    CALLBACK_DURATION,
    CALLBACK_EDIT,
    CALLBACK_CANCEL,
    CALLBACK_REMINDERS,
    CALLBACK_CASHBACK_LIST_MONTH_PREFIX,
    CALLBACK_CASHBACK_EXPORT_CURRENT,
    CALLBACK_CASHBACK_EXPORT_PICKER_PREFIX,
    CALLBACK_CASHBACK_EXPORT_SELECT_PREFIX,
    CALLBACK_CASHBACK_EXPORT_CANCEL,
)
from smart_life_bot.application.cashback_use_cases import AddCashbackCategoryUseCase
from smart_life_bot.cashback.sqlite import SQLiteCashbackCategoriesRepository
from smart_life_bot.storage.sqlite import create_sqlite_connection, init_sqlite_schema
from test_telegram_transport import (
    MissingStartAtParser,
    _build_router,
    _build_router_without_reminders,
)


def test_regression_calendar_preview_confirm_gate_before_write() -> None:
    router, deps = _build_router()

    response = router.handle_text_message(telegram_user_id=92001, text="Тест завтра в 15:00")

    assert "Проверь черновик события" in response.text
    assert len(deps.calendar_service.requests) == 0
    user = deps.users_repo.get_by_telegram_id(92001)
    assert user is not None
    assert deps.state_repo.get(user.id) is not None
    assert ("✅ Создать событие", CALLBACK_CONFIRM) in response.buttons


def test_regression_calendar_write_only_after_explicit_confirm() -> None:
    router, deps = _build_router()

    router.handle_text_message(telegram_user_id=92002, text="Тест завтра в 15:00")
    assert len(deps.calendar_service.requests) == 0

    response = router.handle_callback(telegram_user_id=92002, callback_data=CALLBACK_CONFIRM)

    assert len(deps.calendar_service.requests) == 1
    assert "Event created successfully" in response.text


def test_regression_missing_start_at_draft_cannot_be_confirmed() -> None:
    router, deps = _build_router()
    deps.parser = MissingStartAtParser()

    preview = router.handle_text_message(telegram_user_id=92003, text="Событие без даты")
    stale_confirm = router.handle_callback(telegram_user_id=92003, callback_data=CALLBACK_CONFIRM)

    assert ("✅ Создать событие", CALLBACK_CONFIRM) not in preview.buttons
    assert len(deps.calendar_service.requests) == 0
    assert (
        "Cannot confirm event" in stale_confirm.text
        or "устарел" in stale_confirm.text
        or "No pending draft for confirmation" in stale_confirm.text
    )


def test_regression_start_footer_contains_calendar_and_cashback() -> None:
    router, _ = _build_router()

    response = router.handle_start()

    assert ("📅 Календарь", "💳 Кэшбек") in response.reply_keyboard


def test_regression_calendar_menu_navigation_never_creates_events() -> None:
    router, deps = _build_router()

    menu = router.handle_text_message(telegram_user_id=92004, text="📅 Календарь")
    quick = router.handle_callback(telegram_user_id=92004, callback_data="calendar:mode:quick")
    personal = router.handle_callback(telegram_user_id=92004, callback_data="calendar:mode:personal")

    assert "Текущий режим: 📅 Календарь" in menu.text
    assert ("⚡ Быстрый режим", "calendar:mode:quick") in menu.buttons
    assert ("🔐 Личный Google Calendar", "calendar:mode:personal") in menu.buttons
    assert "Быстрый режим" in quick.text
    assert "foundation-режим" in personal.text
    assert len(deps.calendar_service.requests) == 0


def test_regression_service_account_reminder_gating_keeps_duration_controls() -> None:
    router, _ = _build_router_without_reminders()

    preview = router.handle_text_message(telegram_user_id=92005, text="Team sync")

    assert ("✅ Создать событие", CALLBACK_CONFIRM) in preview.buttons
    assert ("⏱ Длительность", CALLBACK_DURATION) in preview.buttons
    assert ("✏️ Edit", CALLBACK_EDIT) in preview.buttons
    assert ("❌ Cancel", CALLBACK_CANCEL) in preview.buttons
    assert ("🔔 Уведомления", CALLBACK_REMINDERS) not in preview.buttons


def test_regression_cashback_add_query_never_calls_calendar() -> None:
    router, deps = _build_router()

    menu = router.handle_text_message(telegram_user_id=92006, text="💳 Кэшбек")
    add = router.handle_text_message(telegram_user_id=92006, text="Альфа, Владимир, 2026-05, Супермаркеты, 5%")
    query = router.handle_text_message(telegram_user_id=92006, text="Супермаркеты")

    assert "Текущий режим: 💳 Кэшбек" in menu.text
    assert any(label == "➕ Добавить категорию" for label, _ in menu.buttons)
    assert any(label == "🔎 Найти категорию" for label, _ in menu.buttons)
    assert "Добавил кэшбек" in add.text
    listed = router.handle_text_message(telegram_user_id=92006, text="📋 Активные категории")
    assert "Активные кэшбек-категории — май 2026" in listed.text
    assert "🏆 Кэшбек" in query.text
    assert "Владимир — Альфа — 5%" in query.text
    assert len(deps.calendar_service.requests) == 0


def test_regression_cashback_space_separated_add_never_calls_calendar() -> None:
    router, deps = _build_router()

    add = router.handle_text_message(telegram_user_id=92009, text="Т-Банк Владимир Аптеки 5%")
    add_with_month = router.handle_text_message(telegram_user_id=92009, text="Т-Банк Владимир 2026-05 Супермаркеты 3%")
    query = router.handle_text_message(telegram_user_id=92009, text="Аптеки")

    assert "Добавил кэшбек" in add.text or "Обновил кэшбек" in add.text
    assert "Добавил кэшбек" in add_with_month.text or "Обновил кэшбек" in add_with_month.text
    assert "🏆 Кэшбек" in query.text
    assert len(deps.calendar_service.requests) == 0


def test_regression_owner_first_multi_add_in_cashback_mode_has_no_calendar_side_effects() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=92015, text="💳 Кэшбек")

    response = router.handle_text_message(
        telegram_user_id=92015,
        text="Владимир Т-Банк Супермаркеты 5% Аптеки 5%",
    )
    assert "обработал 2 категории" in response.text
    assert "Проверь черновик события" not in response.text
    user = deps.users_repo.get_by_telegram_id(92015)
    assert user is not None
    assert deps.state_repo.get(user.id) is None
    assert router.active_feature_context.get(user.id) == "cashback"
    assert len(deps.calendar_service.requests) == 0


def test_regression_cashback_query_not_found_does_not_fallthrough_to_calendar() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=92010, text="💳 Кэшбек")

    response = router.handle_text_message(telegram_user_id=92010, text="Аптеки")

    assert "ничего не найдено" in response.text
    assert "Проверь черновик события" not in response.text
    user = deps.users_repo.get_by_telegram_id(92010)
    assert user is not None
    assert deps.state_repo.get(user.id) is None
    assert router.active_feature_context.get(user.id) == "cashback"
    assert len(deps.calendar_service.requests) == 0


def test_regression_cashback_mode_plain_text_stays_in_cashback_routing() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=92014, text="💳 Кэшбек")

    response = router.handle_text_message(telegram_user_id=92014, text="Купить хлеб")

    assert "Проверь черновик события" not in response.text
    assert "ничего не найдено" in response.text
    user = deps.users_repo.get_by_telegram_id(92014)
    assert user is not None
    assert deps.state_repo.get(user.id) is None
    assert router.active_feature_context.get(user.id) == "cashback"
    assert len(deps.calendar_service.requests) == 0


def test_regression_missing_date_phrase_reaches_calendar_preview() -> None:
    router, deps = _build_router()
    deps.parser = MissingStartAtParser()

    router.handle_text_message(telegram_user_id=92011, text="📅 Календарь")
    response = router.handle_text_message(telegram_user_id=92011, text="Тест без даты")

    assert "Проверь черновик события" in response.text
    assert ("📅 Выбрать дату", "calendar:date:start") in response.buttons
    assert "ничего не найдено" not in response.text
    assert len(deps.calendar_service.requests) == 0


def test_regression_simple_russian_phrase_not_swallowed_by_cashback_query() -> None:
    router, deps = _build_router()
    deps.parser = MissingStartAtParser()

    router.handle_text_message(telegram_user_id=92012, text="📅 Календарь")
    response = router.handle_text_message(telegram_user_id=92012, text="Купить хлеб")

    assert "Проверь черновик события" in response.text
    assert ("📅 Выбрать дату", "calendar:date:start") in response.buttons
    assert "ничего не найдено" not in response.text
    assert len(deps.calendar_service.requests) == 0


def test_regression_common_one_two_word_event_texts_stay_in_calendar_flow() -> None:
    router, deps = _build_router()
    deps.parser = MissingStartAtParser()

    router.handle_text_message(telegram_user_id=92013, text="📅 Календарь")
    for text in ("Созвон", "Тренировка", "Звонок маме"):
        response = router.handle_text_message(telegram_user_id=92013, text=text)
        assert "Проверь черновик события" in response.text
        assert ("📅 Выбрать дату", "calendar:date:start") in response.buttons
        assert "ничего не найдено" not in response.text
        assert len(deps.calendar_service.requests) == 0


def test_regression_cashback_conflict_clarification_does_not_mutate_states() -> None:
    router, deps = _build_router()

    text_conflict = router.handle_text_message(
        telegram_user_id=92007,
        text="Напомни завтра выбрать кэшбек на супермаркеты",
    )
    structured_conflict = router.handle_text_message(
        telegram_user_id=92007,
        text="Альфа, Владимир, Супермаркеты, 5% завтра",
    )

    assert "несколько вариантов" in text_conflict.text
    assert "несколько вариантов" in structured_conflict.text
    user = deps.users_repo.get_by_telegram_id(92007)
    assert user is not None
    assert deps.state_repo.get(user.id) is None
    assert len(deps.calendar_service.requests) == 0


def test_regression_unset_mode_plain_text_requires_explicit_mode() -> None:
    router, deps = _build_router()

    for user_suffix, text in enumerate(("Аптеки", "Супермаркеты", "Созвон", "Тренировка", "Звонок маме", "Тест без даты", "Купить хлеб"), start=1):
        response = router.handle_text_message(telegram_user_id=92100 + user_suffix, text=text)
        assert response.text == "Выбери режим: 📅 Календарь или 💳 Кэшбек."
        assert ("📅 Календарь", "💳 Кэшбек") in response.reply_keyboard
        user = deps.users_repo.get_by_telegram_id(92100 + user_suffix)
        assert user is not None
        assert deps.state_repo.get(user.id) is None


def test_regression_cashback_use_case_structured_fields_exposed() -> None:
    connection = create_sqlite_connection("sqlite:///:memory:")
    init_sqlite_schema(connection)
    repo = SQLiteCashbackCategoriesRepository(connection)
    use_case = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))

    added = use_case.execute("Альфа, Владимир, Супермаркеты, 5%")
    updated = use_case.execute("Альфа, Владимир, Супермаркеты, 7%")

    assert added is not None
    assert added.status == "added"
    assert added.target_month == "2026-05"
    assert added.created is True
    assert added.updated is False
    assert len(added.records) == 1

    assert updated is not None
    assert updated.status == "updated"
    assert updated.target_month == "2026-05"
    assert updated.created is False
    assert updated.updated is True
    assert len(updated.records) == 1
    assert updated.old_percent == 5
    assert updated.new_percent == 7


def test_regression_cashback_selected_empty_month_has_safe_navigation() -> None:
    router, deps = _build_router()
    response = router.handle_callback(telegram_user_id=92008, callback_data=f"{CALLBACK_CASHBACK_LIST_MONTH_PREFIX}2026-07")
    assert "На июль 2026 активных кэшбек-категорий пока нет." in response.text
    buttons = [button for row in response.button_rows for button in row] if response.button_rows else list(response.buttons)
    assert ("Текущий", "cashback:list:current") in buttons
    assert len(deps.calendar_service.requests) == 0


def test_regression_cashback_menu_contains_export_button() -> None:
    router, _ = _build_router()

    menu = router.handle_text_message(telegram_user_id=92016, text="💳 Кэшбек")

    assert any(label == "📤 Экспорт XLSX" and cb == CALLBACK_CASHBACK_EXPORT_CURRENT for label, cb in menu.buttons)


def test_regression_cashback_export_is_read_only_and_no_calendar_calls() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=92017, text="Альфа, Владимир, 2026-05, Супермаркеты, 5%")
    before = router.list_active_cashback_categories.execute(month="2026-05")

    picker = router.handle_callback(telegram_user_id=92017, callback_data=CALLBACK_CASHBACK_EXPORT_CURRENT)
    response = router.handle_callback(telegram_user_id=92017, callback_data=picker.button_rows[1][0][1])

    after = router.list_active_cashback_categories.execute(month="2026-05")
    assert response.document_bytes is not None
    assert len(before.records) == len(after.records) == 1
    assert before.records == after.records
    assert len(deps.calendar_service.requests) == 0


def test_regression_cashback_alias_query_in_cashback_mode_has_no_calendar_side_effects() -> None:
    router, deps = _build_router()

    router.handle_text_message(telegram_user_id=92016, text="Альфа, Владимир, 2026-05, Супермаркеты, 5%")
    router.handle_text_message(telegram_user_id=92016, text="💳 Кэшбек")
    response = router.handle_text_message(telegram_user_id=92016, text="продукты")

    assert "🏆 Кэшбек" in response.text
    assert "Супермаркеты" in response.text
    assert "Владимир — Альфа — 5%" in response.text
    assert "Проверь черновик события" not in response.text

    user = deps.users_repo.get_by_telegram_id(92016)
    assert user is not None
    assert deps.state_repo.get(user.id) is None
    assert router.active_feature_context.get(user.id) == "cashback"
    assert len(deps.calendar_service.requests) == 0

    second = router.handle_text_message(telegram_user_id=92016, text="лекарства")
    assert "ничего не найдено" in second.text
    assert "Проверь черновик события" not in second.text
    assert deps.state_repo.get(user.id) is None
    assert router.active_feature_context.get(user.id) == "cashback"
    assert len(deps.calendar_service.requests) == 0

def test_regression_cashback_variant_query_in_cashback_mode_has_no_calendar_side_effects() -> None:
    router, deps = _build_router()

    router.handle_text_message(telegram_user_id=92018, text="Альфа, Елена, 2026-05, АЗС, 3%")
    router.handle_text_message(telegram_user_id=92018, text="💳 Кэшбек")
    response = router.handle_text_message(telegram_user_id=92018, text="заправка")

    assert "🏆 Кэшбек" in response.text
    assert "АЗС" in response.text
    assert "Проверь черновик события" not in response.text

    user = deps.users_repo.get_by_telegram_id(92018)
    assert user is not None
    assert deps.state_repo.get(user.id) is None
    assert router.active_feature_context.get(user.id) == "cashback"
    assert len(deps.calendar_service.requests) == 0



def test_regression_cashback_exact_azs_separator_query_in_active_mode_has_no_calendar_side_effects() -> None:
    router, deps = _build_router()

    router.handle_text_message(telegram_user_id=92019, text="Альфа, Елена, 2026-05, АЗС, 3%")
    router.handle_text_message(telegram_user_id=92019, text="💳 Кэшбек")
    response = router.handle_text_message(telegram_user_id=92019, text="а-з-с")

    assert "🏆 Кэшбек" in response.text
    assert "АЗС" in response.text
    assert "Проверь черновик события" not in response.text

    user = deps.users_repo.get_by_telegram_id(92019)
    assert user is not None
    assert deps.state_repo.get(user.id) is None
    assert router.active_feature_context.get(user.id) == "cashback"
    assert len(deps.calendar_service.requests) == 0
