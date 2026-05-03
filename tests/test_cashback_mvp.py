from datetime import date
from zipfile import ZipFile
from io import BytesIO

from smart_life_bot.application.cashback_use_cases import AddCashbackCategoryUseCase, CompleteTransitionCashbackCategoryUseCase, ListActiveCashbackCategoriesUseCase, QueryCashbackCategoryUseCase, RequestDeleteCashbackCategoryUseCase, SoftDeleteCashbackCategoryUseCase, format_month_label
from smart_life_bot.application.cashback_export import ExportCashbackCategoriesUseCase
from smart_life_bot.cashback.parser import normalize_bank_name, parse_owner_first_multi_add, parse_structured_add
from smart_life_bot.cashback.sqlite import SQLiteCashbackCategoriesRepository
from smart_life_bot.storage.sqlite import create_sqlite_connection, init_sqlite_schema


def _repo():
    c = create_sqlite_connection('sqlite:///:memory:')
    init_sqlite_schema(c)
    return SQLiteCashbackCategoriesRepository(c)


def test_structured_add_parse():
    parsed = parse_structured_add('Альфа, Владимир, Супермаркеты, 5%', date(2026,5,3))
    assert parsed is not None
    assert parsed.owner == 'Владимир'
    assert parsed.percent == 5


def test_bank_name_normalization_t_bank_variants_and_unknown_cleanup():
    assert normalize_bank_name("Т-Банк") == "Т-Банк"
    assert normalize_bank_name("Т-банк") == "Т-Банк"
    assert normalize_bank_name("т-банк") == "Т-Банк"
    assert normalize_bank_name("Т банк") == "Т-Банк"
    assert normalize_bank_name("т банк") == "Т-Банк"
    assert normalize_bank_name("ТБанк") == "Т-Банк"
    assert normalize_bank_name("тбанк") == "Т-Банк"
    assert normalize_bank_name("  My   Bank  ") == "My Bank"
    assert normalize_bank_name("  My -  Bank  ") == "My-Bank"



def test_structured_add_space_separated_and_missing_final_comma():
    today = date(2026, 5, 3)
    spaced = parse_structured_add('Т-Банк Владимир Аптеки 5%', today)
    assert spaced is not None
    assert spaced.bank == 'Т-Банк'
    assert spaced.owner == 'Владимир'
    assert spaced.category == 'Аптеки'
    assert spaced.percent == 5

    spaced_month_ru = parse_structured_add('Т-Банк Владимир май Аптеки 5%', today)
    assert spaced_month_ru is not None
    assert spaced_month_ru.month == '2026-05'

    spaced_month_iso = parse_structured_add('Т-Банк Владимир 2026-05 Аптеки 5%', today)
    assert spaced_month_iso is not None
    assert spaced_month_iso.month == '2026-05'

    missing_final_comma = parse_structured_add('Т-Банк, Владимир, Аптеки 5%', today)
    assert missing_final_comma is not None
    assert missing_final_comma.bank == 'Т-Банк'
    assert missing_final_comma.owner == 'Владимир'
    assert missing_final_comma.category == 'Аптеки'
    assert missing_final_comma.percent == 5


def test_owner_first_multi_add_parsing_variants():
    today = date(2026, 5, 3)
    comma = parse_owner_first_multi_add("Владимир, Т-Банк, Супермаркеты 5%, Аптеки 5%", today)
    assert comma is not None and comma.owner == "Владимир" and len(comma.pairs) == 2
    with_ru_month = parse_owner_first_multi_add("Владимир Т-Банк май Супермаркеты 5% Аптеки 5%", today)
    assert with_ru_month is not None and with_ru_month.month == "2026-05"
    with_iso_month = parse_owner_first_multi_add("Владимир Т-Банк 2026-05 Дом и ремонт 7% Аптеки 5%", today)
    assert with_iso_month is not None and with_iso_month.pairs[0][0] == "Дом и ремонт"


def test_owner_first_multi_add_up_to_five_and_atomic_invalid():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    ok = add.execute("Владимир Т-Банк Супермаркеты 5% Аптеки 5% АЗС 3%")
    assert ok is not None and "обработал 3 категории" in ok.text
    too_many = add.execute("Владимир Т-Банк A 1% B 2% C 3% D 4% E 5% F 6%")
    assert too_many is not None and too_many.error_code == "too_many_categories"
    bad = add.execute("Владимир Т-Банк Аптеки 5% Кафе")
    assert bad is not None and bad.status == "invalid_format"
    assert len(repo.list_active("2026-05")) == 3


def test_owner_first_multi_add_transition_batch_completes_for_selected_month() -> None:
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 4, 26))
    transition = add.execute("Владимир Т-Банк Супермаркеты 5% Аптеки 5%")
    assert transition is not None
    assert transition.status == "transition_month_required"
    assert transition.candidate_months == ("2026-04", "2026-05")
    assert transition.pending_add is not None
    assert repo.list_active("2026-04") == []
    assert repo.list_active("2026-05") == []

    complete = CompleteTransitionCashbackCategoryUseCase(repo).execute(transition.pending_add, "2026-05")
    assert complete.status == "added"
    assert "обработал 2 категории" in complete.text
    assert "1. Супермаркеты" in complete.text
    assert "2. Аптеки" in complete.text
    active = repo.list_active("2026-05")
    assert len(active) == 2


def test_invalid_owner_first_iso_month_rejected_without_writes() -> None:
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    comma = add.execute("Владимир, Т-Банк, 2026-13, Супермаркеты 5%, Аптеки 5%")
    assert comma is not None
    assert comma.status == "invalid_month"
    assert comma.error_code == "invalid_month"
    space = add.execute("Владимир Т-Банк 2026-99 Супермаркеты 5% Аптеки 5%")
    assert space is not None
    assert space.status == "invalid_month"
    assert space.error_code == "invalid_month"
    space_multi_token_bank = add.execute("Владимир Т банк 2026-99 Супермаркеты 5% Аптеки 5%")
    assert space_multi_token_bank is not None
    assert space_multi_token_bank.status == "invalid_month"
    assert space_multi_token_bank.error_code == "invalid_month"
    space_multi_token_bank_zero = add.execute("Владимир Т банк 2026-00 Супермаркеты 5%")
    assert space_multi_token_bank_zero is not None
    assert space_multi_token_bank_zero.status == "invalid_month"
    assert space_multi_token_bank_zero.error_code == "invalid_month"
    assert repo.list_active("2026-05") == []
def test_upsert_and_query_sorted():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026,5,3))
    add.execute('Альфа, Владимир, Супермаркеты, 5%')
    add.execute('Т-Банк, Елена, Супермаркеты, 7%')
    text = QueryCashbackCategoryUseCase(repo, now_provider=lambda: date(2026,5,3)).execute('Супермаркеты').text
    assert '1. Елена — Т-Банк — 7%' in text


def test_transition_requires_explicit_month():
    repo = _repo()
    result = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026,4,26)).execute('Альфа, Владимир, Супермаркеты, 5%')
    assert result is not None
    assert result.status == "transition_month_required"
    assert result.candidate_months == ("2026-04", "2026-05")
    assert result.pending_add is not None


def test_transition_complete_with_selected_month_and_invalid_month_fail_safe():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 4, 26))
    transition = add.execute("Альфа, Владимир, Супермаркеты, 5%")
    assert transition is not None and transition.pending_add is not None
    complete = CompleteTransitionCashbackCategoryUseCase(repo)
    may = complete.execute(transition.pending_add, "2026-05")
    assert may.status == "added"
    assert may.target_month == "2026-05"
    bad = complete.execute(transition.pending_add, "bad")
    assert bad.status == "invalid_month"


def test_category_normalization_query_and_duplicate_update():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    first = add.execute('Альфа, Владимир, Супер   маркеты, 5%')
    second = add.execute('Альфа, Владимир, супер маркеты, 7%')
    assert first is not None and first.status == 'added'
    assert second is not None and second.status == 'updated'
    assert second.old_percent == 5
    assert second.new_percent == 7
    rows = QueryCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute('супер маркеты')
    assert rows.status == 'query_found'
    assert len(rows.records) == 1
    assert rows.records[0].percent == 7




def test_duplicate_same_percent_returns_already_exists_and_does_not_create_extra_row():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    first = add.execute("Т-Банк, Владимир, Аптеки, 5%")
    second = add.execute("Т-Банк, Владимир, Аптеки, 5%")
    assert first is not None and first.status == "added"
    assert second is not None and second.status == "already_exists"
    assert "Такая категория уже есть" in second.text
    active = repo.list_active("2026-05")
    assert len(active) == 1
    assert active[0].percent == 5


def test_duplicate_same_percent_space_separated_returns_already_exists():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    add.execute("Т-Банк Владимир Аптеки 5%")
    repeated = add.execute("Т-Банк Владимир Аптеки 5%")
    assert repeated is not None and repeated.status == "already_exists"
    listed = ListActiveCashbackCategoriesUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute()
    assert listed.status == "list_found"
    assert len(listed.records) == 1


def test_duplicate_same_percent_with_normalized_bank_returns_already_exists_and_single_active_row():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    first = add.execute("Т-Банк Владимир Аптеки 5%")
    second = add.execute("Т-банк Владимир Аптеки 5%")
    assert first is not None and first.status == "added"
    assert second is not None and second.status == "already_exists"
    active = repo.list_active("2026-05")
    assert len(active) == 1
    assert active[0].bank_name == "Т-Банк"


def test_changed_percent_with_normalized_bank_updates_existing_row():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    first = add.execute("Т-Банк Владимир Аптеки 5%")
    second = add.execute("т банк Владимир Аптеки 7%")
    assert first is not None and first.status == "added"
    assert second is not None and second.status == "updated"
    assert second.old_percent == 5
    assert second.new_percent == 7
    active = repo.list_active("2026-05")
    assert len(active) == 1
    assert active[0].bank_name == "Т-Банк"
    assert active[0].percent == 7


def test_cashback_export_xlsx_is_structurally_valid_and_contains_expected_values() -> None:
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    add.execute("Тест & Банк, Владимир, 2026-05, Кафе <обед>, 7.5%")
    result = ExportCashbackCategoriesUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute("2026-05")
    assert result.status == "ok"
    assert result.content is not None

    with ZipFile(BytesIO(result.content)) as archive:
        names = set(archive.namelist())
        assert "[Content_Types].xml" in names
        assert "_rels/.rels" in names
        assert "xl/workbook.xml" in names
        assert "xl/_rels/workbook.xml.rels" in names
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/styles.xml" in names
        worksheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        styles_xml = archive.read("xl/styles.xml").decode("utf-8")

    assert "Кэшбек — май 2026" in worksheet_xml
    assert "owner" in worksheet_xml
    assert "Владимир" in worksheet_xml
    assert "Тест &amp; Банк" in worksheet_xml
    assert "Кафе &lt;обед&gt;" in worksheet_xml
    assert "7.5%" in worksheet_xml
    assert "2026-05" in worksheet_xml
    assert "active" in worksheet_xml
    assert "autoFilter" in worksheet_xml
    assert "pane" in worksheet_xml
    assert "<cols>" in worksheet_xml
    assert "styleSheet" in styles_xml

def test_explicit_month_parsing_variants():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 4, 26))
    may = add.execute('Альфа, Владимир, май, Супермаркеты, 5%')
    iso = add.execute('Альфа, Владимир, 2026-05, Супермаркеты, 6%')
    assert may is not None and may.target_month == '2026-05'
    assert iso is not None and iso.target_month == '2026-05'


def test_invalid_month_in_5_part_input_not_saved():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    result = add.execute('Альфа, Владимир, notamonth, Супермаркеты, 5%')
    assert result is not None
    assert result.status == 'invalid_month'
    assert result.error_code == 'invalid_month'
    assert repo.list_active('2026-05') == []


def test_invalid_iso_month_13_comma_add_not_saved():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    result = add.execute("Альфа, Владимир, 2026-13, Супермаркеты, 5%")
    assert result is not None
    assert result.status == "invalid_month"
    assert repo.list_active("2026-05") == []


def test_invalid_iso_month_99_space_add_not_saved():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    result = add.execute("Т-Банк Владимир 2026-99 Аптеки 5%")
    assert result is not None
    assert result.status == "invalid_month"
    assert repo.list_active("2026-05") == []


def test_invalid_iso_zero_month_not_saved():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    result = add.execute("Т-Банк Владимир 2026-00 Аптеки 5%")
    assert result is not None
    assert result.status == "invalid_month"
    assert repo.list_active("2026-05") == []


def test_valid_explicit_iso_month_still_saved():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    result = add.execute("Альфа, Владимир, 2026-05, Супермаркеты, 5%")
    assert result is not None
    assert result.status == "added"
    assert result.target_month == "2026-05"
    assert len(repo.list_active("2026-05")) == 1


def test_invalid_owner_result_contains_allowed_owners_and_not_saved():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    result = add.execute('Альфа, Иван, Супермаркеты, 5%')
    assert result is not None
    assert result.status == 'invalid_owner'
    assert 'Виктор' in result.allowed_owners
    assert repo.list_active('2026-05') == []


def test_list_active_categories_found_and_empty():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026,5,3))
    add.execute('Альфа, Владимир, Супермаркеты, 5%')
    add.execute('Т-Банк, Елена, Супермаркеты, 3%')
    found = ListActiveCashbackCategoriesUseCase(repo, now_provider=lambda: date(2026,5,3)).execute()
    assert found.status == "list_found"
    assert found.target_month == "2026-05"
    assert "май 2026" in found.text
    assert "1. Владимир — Альфа — 5%" in found.text
    assert "2. Елена — Т-Банк — 3%" in found.text
    assert "#1" not in found.text

    empty = ListActiveCashbackCategoriesUseCase(repo, now_provider=lambda: date(2026,6,3)).execute()
    assert empty.status == "list_empty"
    assert empty.target_month == "2026-06"


def test_list_active_categories_selected_month_only():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    add.execute("Альфа, Владимир, май, Супермаркеты, 5%")
    add.execute("Т-Банк, Елена, июнь, Аптеки, 7%")
    may = ListActiveCashbackCategoriesUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute(month="2026-05")
    june = ListActiveCashbackCategoriesUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute(month="2026-06")
    assert may.status == "list_found"
    assert "Супермаркеты" in may.text
    assert "Аптеки" not in may.text
    assert june.status == "list_found"
    assert "Аптеки" in june.text


def test_list_active_categories_uses_global_numbering_across_categories():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    add.execute("Альфа, Владимир, АЗС, 2%")
    add.execute("Т-Банк, Елена, Супермаркеты, 7%")
    result = ListActiveCashbackCategoriesUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute()
    assert result.status == "list_found"
    assert "1. Владимир — Альфа — 2%" in result.text
    assert "2. Елена — Т-Банк — 7%" in result.text


def test_month_label_and_readable_month_in_messages():
    repo = _repo()
    assert format_month_label("2026-05") == "май 2026"
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026,5,3)).execute('Альфа, Владимир, Супермаркеты, 5%')
    assert add is not None
    assert add.target_month == "2026-05"
    assert "май 2026" in add.text
    query = QueryCashbackCategoryUseCase(repo, now_provider=lambda: date(2026,5,3)).execute('Аптеки')
    assert query.target_month == "2026-05"
    assert "май 2026" in query.text


def test_soft_delete_hides_from_list_and_query_and_updates_timestamp():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    added = add.execute("Альфа, Владимир, Супермаркеты, 5%")
    assert added is not None
    record_id = added.records[0].id
    before = repo.get_by_id(record_id)
    assert before is not None and before.is_deleted is False
    deleted_result = SoftDeleteCashbackCategoryUseCase(repo).execute(str(record_id))
    assert deleted_result.status == "deleted"
    after = repo.get_by_id(record_id)
    assert after is not None and after.is_deleted is True
    assert after.updated_at >= before.updated_at
    assert repo.list_active("2026-05") == []
    assert QueryCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute("Супермаркеты").status == "query_not_found"


def test_delete_request_and_not_found_fail_safe_results():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    added = add.execute("Альфа, Владимир, Супермаркеты, 5%")
    assert added is not None
    request = RequestDeleteCashbackCategoryUseCase(repo).execute(str(added.records[0].id))
    assert request.status == "delete_confirmation"
    assert "Владимир" in request.text
    assert "Альфа" in request.text
    SoftDeleteCashbackCategoryUseCase(repo).execute(str(added.records[0].id))
    not_found = SoftDeleteCashbackCategoryUseCase(repo).execute(str(added.records[0].id))
    assert not_found.status == "delete_not_found"
    invalid = RequestDeleteCashbackCategoryUseCase(repo).execute("bad")
    assert invalid.status == "delete_invalid_callback"


def test_list_active_categories_owner_filter_and_invalid_owner():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    add.execute("Альфа, Владимир, май, АЗС, 2%")
    add.execute("Т-Банк, Елена, май, АЗС, 5%")
    filtered = ListActiveCashbackCategoriesUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute(month="2026-05", owner_name="Владимир")
    assert filtered.status == "list_found"
    assert "Владелец: Владимир" in filtered.text
    assert "Елена" not in filtered.text
    assert len(filtered.records) == 1
    empty = ListActiveCashbackCategoriesUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute(month="2026-06", owner_name="Владимир")
    assert empty.status == "list_empty"
    assert "у Владимир" in empty.text
    invalid = ListActiveCashbackCategoriesUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute(month="2026-05", owner_name="Иван")
    assert invalid.error_code == "invalid_owner_filter"


def test_update_percent_by_id_changes_only_percent_and_updated_at():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    add.execute('Альфа, Владимир, Супермаркеты, 5%')
    row = repo.list_active('2026-05')[0]
    created_at = row.created_at
    updated_at = row.updated_at
    from smart_life_bot.application.cashback_use_cases import UpdateCashbackCategoryPercentUseCase
    result = UpdateCashbackCategoryPercentUseCase(repo).execute(str(row.id), '7,5%')
    assert result.status == 'edit_percent_updated'
    changed = repo.get_by_id(row.id)
    assert changed is not None
    assert changed.percent == 7.5
    assert changed.created_at == created_at
    assert changed.updated_at >= updated_at
    assert changed.owner_name == row.owner_name
    assert changed.bank_name == row.bank_name
    assert changed.category_raw == row.category_raw
    assert changed.target_month == row.target_month


def test_update_percent_missing_deleted_and_invalid_fail_safe():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    add.execute('Альфа, Владимир, Супермаркеты, 5%')
    row = repo.list_active('2026-05')[0]
    from smart_life_bot.application.cashback_use_cases import UpdateCashbackCategoryPercentUseCase
    use_case = UpdateCashbackCategoryPercentUseCase(repo)
    bad = use_case.execute(str(row.id), 'abc')
    assert bad.status == 'edit_percent_invalid'
    assert repo.get_by_id(row.id).percent == 5
    repo.soft_delete(row.id)
    deleted = use_case.execute(str(row.id), '7')
    assert deleted.status == 'edit_percent_not_found'
    missing = use_case.execute('9999', '7')
    assert missing.status == 'edit_percent_not_found'


def test_update_percent_same_value_is_noop():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    add.execute('Альфа, Владимир, Супермаркеты, 5%')
    row = repo.list_active('2026-05')[0]
    from smart_life_bot.application.cashback_use_cases import UpdateCashbackCategoryPercentUseCase
    result = UpdateCashbackCategoryPercentUseCase(repo).execute(str(row.id), '5%')
    assert result.status == 'edit_percent_no_change'

def test_cashback_query_aliases_are_deterministic_for_known_categories():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    query = QueryCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    add.execute('Альфа, Владимир, Супермаркеты, 5%')
    add.execute('Т-Банк, Владимир, Аптеки, 7%')
    add.execute('Альфа, Елена, АЗС, 3%')

    products = query.execute('продукты')
    food = query.execute('еда')
    medicines = query.execute('лекарства')
    medicine = query.execute('медицина')
    petrol = query.execute('бензин')
    fuel = query.execute('топливо')

    assert products.status == 'query_found'
    assert '🏆 Кэшбек' in products.text
    assert 'Супермаркеты' in products.text
    assert food.status == 'query_found'
    assert '🏆 Кэшбек' in food.text
    assert 'Супермаркеты' in food.text
    assert medicines.status == 'query_found'
    assert '🏆 Кэшбек' in medicines.text
    assert 'Аптеки' in medicines.text
    assert medicine.status == 'query_found'
    assert '🏆 Кэшбек' in medicine.text
    assert 'Аптеки' in medicine.text
    assert petrol.status == 'query_found'
    assert '🏆 Кэшбек' in petrol.text
    assert 'АЗС' in petrol.text
    assert fuel.status == 'query_found'
    assert '🏆 Кэшбек' in fuel.text
    assert 'АЗС' in fuel.text


def test_cashback_query_aliases_keep_direct_queries_and_unrelated_not_found():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    query = QueryCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    add.execute('Альфа, Владимир, Супермаркеты, 5%')
    add.execute('Т-Банк, Владимир, Аптеки, 7%')
    add.execute('Альфа, Елена, АЗС, 3%')

    assert query.execute('Супермаркеты').status == 'query_found'
    assert query.execute('Аптеки').status == 'query_found'
    assert query.execute('АЗС').status == 'query_found'
    assert query.execute('купить хлеб').status == 'query_not_found'
