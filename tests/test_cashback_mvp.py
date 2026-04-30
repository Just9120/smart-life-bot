from datetime import date

from smart_life_bot.application.cashback_use_cases import AddCashbackCategoryUseCase, QueryCashbackCategoryUseCase
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
