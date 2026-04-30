from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from smart_life_bot.cashback.models import ALLOWED_OWNERS, CashbackAddInput
from smart_life_bot.cashback.parser import in_transition_period, normalize_category_key, parse_structured_add, validate_owner


@dataclass(frozen=True, slots=True)
class CashbackResult:
    status: Literal["added", "updated", "invalid_owner", "transition_month_required", "not_cashback_add", "query_found", "query_not_found", "invalid_month"]
    text: str
    target_month: str | None = None
    created: bool = False
    updated: bool = False
    records: tuple = ()
    old_percent: float | None = None
    new_percent: float | None = None
    error_code: str | None = None
    allowed_owners: tuple[str, ...] = ()


class AddCashbackCategoryUseCase:
    def __init__(self, repo, *, now_provider=None) -> None:
        self.repo = repo
        self.now_provider = now_provider or (lambda: datetime.now(UTC).date())

    def execute(self, text: str) -> CashbackResult | None:
        today = self.now_provider()
        parsed = parse_structured_add(text, today)
        if parsed is None:
            return None
        if len([p.strip() for p in text.split(",") if p.strip()]) == 5 and parsed.month is None:
            return CashbackResult(status="invalid_month", text="Некорректный формат месяца. Используй русское название месяца или YYYY-MM.", error_code="invalid_month")
        if not validate_owner(parsed.owner):
            return CashbackResult(status="invalid_owner", text=f"Не понял владельца карты. Доступные владельцы: {', '.join(ALLOWED_OWNERS)}.", error_code="invalid_owner", allowed_owners=ALLOWED_OWNERS)
        if parsed.month is None:
            if in_transition_period(today):
                return CashbackResult(status="transition_month_required", text="Сейчас переходный период между месяцами. Укажи месяц явно, например: Альфа, Владимир, май, Супермаркеты, 5%", error_code="transition_month_required")
            month = f"{today.year:04d}-{today.month:02d}"
        else:
            month = parsed.month
        record, updated, old = self.repo.upsert(CashbackAddInput(parsed.bank, parsed.owner, parsed.category, parsed.percent, month, text))
        month_label = month
        if updated:
            return CashbackResult(status="updated", text=f"Обновил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — было {old:g}%, стало {record.percent:g}% — {month_label}", target_month=month, updated=True, records=(record,), old_percent=old, new_percent=record.percent)
        return CashbackResult(status="added", text=f"Готово. Добавил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}", target_month=month, created=True, records=(record,), new_percent=record.percent)


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
            return CashbackResult(status="query_not_found", text=f"На {month} по категории «{text.strip()}» ничего не найдено.", target_month=month)
        lines = [f"🏆 Кэшбек: {rows[0].category_raw} — {month}", ""]
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. {r.owner_name} — {r.bank_name} — {r.percent:g}%")
        return CashbackResult(status="query_found", text="\n".join(lines), target_month=month, records=tuple(rows))
