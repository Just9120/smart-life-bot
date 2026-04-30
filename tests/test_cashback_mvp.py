from datetime import date

from smart_life_bot.application.cashback_use_cases import AddCashbackCategoryUseCase, QueryCashbackCategoryUseCase
from smart_life_bot.cashback.parser import parse_structured_add
from smart_life_bot.cashback.sqlite import SQLiteCashbackCategoriesRepository
from smart_life_bot.storage.sqlite import create_sqlite_connection, init_sqlite_schema


def _repo():
    c = create_sqlite_connection('sqlite:///:memory:')
    init_sqlite_schema(c)
    return SQLiteCashbackCategoriesRepository(c), c


def test_structured_add_parse_month_name_and_yyyy_mm():
    parsed_name = parse_structured_add('Альфа, Владимир, май, Супермаркеты, 5%', date(2026, 4, 20))
    assert parsed_name is not None
    assert parsed_name.month == '2026-05'

    parsed_iso = parse_structured_add('Альфа, Владимир, 2026-05, Супермаркеты, 5%', date(2026, 4, 20))
    assert parsed_iso is not None
    assert parsed_iso.month == '2026-05'


def test_normalization_match_and_duplicate_upsert_update_response():
    repo, conn = _repo()
    add = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3))
    first = add.execute('Альфа, Владимир, Супер   маркеты, 5%')
    second = add.execute('Альфа, Владимир, супер маркеты, 7%')

    assert first is not None and 'Добавил' in first.text
    assert second is not None and 'Обновил кэшбек' in second.text and 'было 5%, стало 7%' in second.text

    rows = conn.execute('SELECT COUNT(*) AS c FROM cashback_categories').fetchone()
    assert rows['c'] == 1
    text = QueryCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute('супер маркеты').text
    assert '7%' in text


def test_transition_requires_explicit_month():
    repo, _ = _repo()
    msg = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 4, 26)).execute('Альфа, Владимир, Супермаркеты, 5%').text
    assert 'переходный период' in msg


def test_invalid_month_in_5part_input_rejected_and_not_saved():
    repo, conn = _repo()
    msg = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute('Альфа, Владимир, notamonth, Супермаркеты, 5%').text
    assert 'Не понял месяц' in msg
    rows = conn.execute('SELECT COUNT(*) AS c FROM cashback_categories').fetchone()
    assert rows['c'] == 0


def test_invalid_owner_rejected_and_not_saved():
    repo, conn = _repo()
    msg = AddCashbackCategoryUseCase(repo, now_provider=lambda: date(2026, 5, 3)).execute('Альфа, Иван, Супермаркеты, 5%').text
    assert 'Не понял владельца карты' in msg
    assert 'Виктор, Владимир, Елена' in msg
    rows = conn.execute('SELECT COUNT(*) AS c FROM cashback_categories').fetchone()
    assert rows['c'] == 0
