from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from smart_life_bot.cashback.models import ALLOWED_OWNERS, CashbackAddInput
from smart_life_bot.cashback.parser import in_transition_period, normalize_category_key, parse_structured_add, validate_owner


@dataclass(frozen=True, slots=True)
class CashbackResult:
    text: str


class AddCashbackCategoryUseCase:
    def __init__(self, repo, *, now_provider=None) -> None:
        self.repo = repo
        self.now_provider = now_provider or (lambda: datetime.now(UTC).date())

    def execute(self, text: str) -> CashbackResult | None:
        today = self.now_provider()
        parsed = parse_structured_add(text, today)
        if parsed is None:
            return None
        if not validate_owner(parsed.owner):
            return CashbackResult(f"Не понял владельца карты. Доступные владельцы: {', '.join(ALLOWED_OWNERS)}.")
        if parsed.month is None:
            if in_transition_period(today):
                return CashbackResult("Сейчас переходный период между месяцами. Укажи месяц явно, например: Альфа, Владимир, май, Супермаркеты, 5%")
            month = f"{today.year:04d}-{today.month:02d}"
        else:
            month = parsed.month
        record, updated, old = self.repo.upsert(CashbackAddInput(parsed.bank, parsed.owner, parsed.category, parsed.percent, month, text))
        month_label = month
        if updated:
            return CashbackResult(f"Обновил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — было {old:g}%, стало {record.percent:g}% — {month_label}")
        return CashbackResult(f"Готово. Добавил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}")


class QueryCashbackCategoryUseCase:
    def __init__(self, repo, *, now_provider=None) -> None:
        self.repo = repo
        self.now_provider = now_provider or (lambda: datetime.now(UTC).date())

    def execute(self, text: str) -> CashbackResult:
        today = self.now_provider()
        month = f"{today.year:04d}-{today.month:02d}"
        key = normalize_category_key(text)
        rows = self.repo.query(key, month)
        if not rows:
            return CashbackResult(f"На {month} по категории «{text.strip()}» ничего не найдено.")
        lines = [f"🏆 Кэшбек: {rows[0].category_raw} — {month}", ""]
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. {r.owner_name} — {r.bank_name} — {r.percent:g}%")
        return CashbackResult("\n".join(lines))
