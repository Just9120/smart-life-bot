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
