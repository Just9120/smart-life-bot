from datetime import date

from smart_life_bot.application.cashback_use_cases import AddCashbackCategoryUseCase, ListActiveCashbackCategoriesUseCase, QueryCashbackCategoryUseCase, RequestDeleteCashbackCategoryUseCase, SoftDeleteCashbackCategoryUseCase, format_month_label
from smart_life_bot.cashback.parser import parse_structured_add
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


def test_upsert_and_query_sorted():
    repo = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026,5,3))
    add.execute('Альфа, Владимир, Супермаркеты, 5%')
    add.execute('Т-Банк, Елена, Супермаркеты, 7%')
    text = QueryCashbackCategoryUseCase(repo, now_provider=lambda: date(2026,5,3)).execute('Супермаркеты').text
    assert '1. Елена — Т-Банк — 7%' in text


def test_transition_requires_explicit_month():
    repo = _repo()
    msg = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026,4,26)).execute('Альфа, Владимир, Супермаркеты, 5%').text
    assert 'переходный период' in msg


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
