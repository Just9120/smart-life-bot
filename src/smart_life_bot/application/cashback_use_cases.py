from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from smart_life_bot.cashback.models import ALLOWED_OWNERS, CashbackAddInput
from smart_life_bot.cashback.parser import in_transition_period, looks_like_cashback_add_attempt, normalize_category_key, parse_structured_add, validate_owner

RU_MONTH_LABELS = {
    1: "январь", 2: "февраль", 3: "март", 4: "апрель", 5: "май", 6: "июнь",
    7: "июль", 8: "август", 9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь",
}


def format_month_label(target_month: str) -> str:
    parsed = parse_year_month(target_month)
    if parsed is None:
        return target_month
    year, month = parsed
    return f"{RU_MONTH_LABELS.get(month, f'{month:02d}')} {year}"


def parse_year_month(value: str) -> tuple[int, int] | None:
    try:
        year_raw, month_raw = value.split("-", maxsplit=1)
        year = int(year_raw)
        month = int(month_raw)
    except (AttributeError, TypeError, ValueError):
        return None
    if not (1 <= month <= 12):
        return None
    if not (1900 <= year <= 2100):
        return None
    return year, month


def shift_year_month(value: str, *, delta: int) -> str | None:
    parsed = parse_year_month(value)
    if parsed is None:
        return None
    year, month = parsed
    absolute = year * 12 + (month - 1) + delta
    next_year, month_index = divmod(absolute, 12)
    return f"{next_year:04d}-{month_index + 1:02d}"


def current_year_month(today: date) -> str:
    return f"{today.year:04d}-{today.month:02d}"


@dataclass(frozen=True, slots=True)
class CashbackResult:
    status: Literal["added", "updated", "invalid_owner", "transition_month_required", "not_cashback_add", "query_found", "query_not_found", "invalid_month", "list_found", "list_empty", "delete_confirmation", "delete_cancelled", "deleted", "delete_not_found", "delete_invalid_callback", "invalid_format"]
    text: str
    target_month: str | None = None
    created: bool = False
    updated: bool = False
    records: tuple = ()
    old_percent: float | None = None
    new_percent: float | None = None
    error_code: str | None = None
    allowed_owners: tuple[str, ...] = ()
    owner_filter: str | None = None
    candidate_months: tuple[str, ...] = ()
    pending_add: CashbackAddInput | None = None


class RequestDeleteCashbackCategoryUseCase:
    def __init__(self, repo) -> None:
        self.repo = repo

    def execute(self, record_id_raw: str) -> CashbackResult:
        if not record_id_raw.isdigit():
            return CashbackResult(status="delete_invalid_callback", text="Не удалось разобрать запись для удаления. Открой «📋 Активные категории» заново.")
        record = self.repo.get_by_id(int(record_id_raw))
        if record is None or record.is_deleted:
            return CashbackResult(status="delete_not_found", text="Запись уже неактуальна или была удалена. Обнови список «📋 Активные категории».")
        month_label = format_month_label(record.target_month)
        return CashbackResult(
            status="delete_confirmation",
            text=(
                "Подтверди деактивацию категории:\n"
                f"{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}\n\n"
                "После подтверждения запись исчезнет из активных списков."
            ),
            target_month=record.target_month,
            records=(record,),
        )


class SoftDeleteCashbackCategoryUseCase:
    def __init__(self, repo) -> None:
        self.repo = repo

    def execute(self, record_id_raw: str) -> CashbackResult:
        if not record_id_raw.isdigit():
            return CashbackResult(status="delete_invalid_callback", text="Некорректная кнопка удаления. Открой «📋 Активные категории» заново.")
        deleted = self.repo.soft_delete(int(record_id_raw))
        if deleted is None:
            return CashbackResult(status="delete_not_found", text="Запись уже удалена или не найдена. Обнови список «📋 Активные категории».")
        month_label = format_month_label(deleted.target_month)
        return CashbackResult(
            status="deleted",
            text=f"Деактивировано:\n{deleted.owner_name} — {deleted.bank_name} — {deleted.category_raw} — {deleted.percent:g}% — {month_label}",
            target_month=deleted.target_month,
            records=(deleted,),
            updated=True,
        )


class AddCashbackCategoryUseCase:
    def __init__(self, repo, *, now_provider=None) -> None:
        self.repo = repo
        self.now_provider = now_provider or (lambda: datetime.now(UTC).date())

    def execute(self, text: str) -> CashbackResult | None:
        today = self.now_provider()
        parsed = parse_structured_add(text, today)
        if parsed is None:
            if looks_like_cashback_add_attempt(text):
                return CashbackResult(
                    status="invalid_format",
                    text=(
                        "Не понял формат кэшбека.\n"
                        "Формат с запятыми: Т-Банк, Владимир, Аптеки, 5%\n"
                        "Или коротко: Т-Банк Владимир Аптеки 5%"
                    ),
                    error_code="invalid_format",
                )
            return None
        if len([p.strip() for p in text.split(",") if p.strip()]) == 5 and parsed.month is None:
            return CashbackResult(status="invalid_month", text="Некорректный месяц.\nИспользуй русское название месяца или YYYY-MM, например: май или 2026-05.", error_code="invalid_month")
        if not validate_owner(parsed.owner):
            return CashbackResult(status="invalid_owner", text=f"Не понял владельца карты.\nДоступные владельцы: {', '.join(ALLOWED_OWNERS)}.\n\nФормат добавления:\nАльфа, Владимир, май, Супермаркеты, 5%", error_code="invalid_owner", allowed_owners=ALLOWED_OWNERS)
        if parsed.month is None:
            if in_transition_period(today):
                current_month = current_year_month(today)
                next_month = shift_year_month(current_month, delta=1)
                candidate_months = (current_month, next_month) if next_month is not None else (current_month,)
                return CashbackResult(
                    status="transition_month_required",
                    text="Сейчас переходный период между месяцами. К какому месяцу отнести категорию?",
                    error_code="transition_month_required",
                    candidate_months=candidate_months,
                    pending_add=CashbackAddInput(parsed.bank, parsed.owner, parsed.category, parsed.percent, current_month, text),
                )
            month = current_year_month(today)
        else:
            month = parsed.month
        record, updated, old = self.repo.upsert(CashbackAddInput(parsed.bank, parsed.owner, parsed.category, parsed.percent, month, text))
        month_label = format_month_label(month)
        if updated:
            return CashbackResult(status="updated", text=f"Обновил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — было {old:g}%, стало {record.percent:g}% — {month_label}", target_month=month, updated=True, records=(record,), old_percent=old, new_percent=record.percent)
        return CashbackResult(status="added", text=f"Готово. Добавил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}", target_month=month, created=True, records=(record,), new_percent=record.percent)


class CompleteTransitionCashbackCategoryUseCase:
    def __init__(self, repo) -> None:
        self.repo = repo

    def execute(self, payload: CashbackAddInput, selected_month: str) -> CashbackResult:
        if parse_year_month(selected_month) is None:
            return CashbackResult(
                status="invalid_month",
                text="Некорректный месяц в кнопке. Открой «💳 Кэшбек» и попробуй снова.",
                error_code="invalid_month",
            )
        record, updated, old = self.repo.upsert(
            CashbackAddInput(
                payload.bank_name,
                payload.owner_name,
                payload.category_raw,
                payload.percent,
                selected_month,
                payload.source_text,
            )
        )
        month_label = format_month_label(selected_month)
        if updated:
            return CashbackResult(status="updated", text=f"Обновил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — было {old:g}%, стало {record.percent:g}% — {month_label}", target_month=selected_month, updated=True, records=(record,), old_percent=old, new_percent=record.percent)
        return CashbackResult(status="added", text=f"Готово. Добавил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}", target_month=selected_month, created=True, records=(record,), new_percent=record.percent)


class QueryCashbackCategoryUseCase:
    def __init__(self, repo, *, now_provider=None) -> None:
        self.repo = repo
        self.now_provider = now_provider or (lambda: datetime.now(UTC).date())

    def execute(self, text: str) -> CashbackResult:
        today = self.now_provider()
        month = current_year_month(today)
        month_label = format_month_label(month)
        key = normalize_category_key(text)
        rows = self.repo.query(key, month)
        if not rows:
            return CashbackResult(status="query_not_found", text=f"На {month_label} по категории «{text.strip()}» ничего не найдено.\n\nПроверь название категории или открой 📋 Активные категории.", target_month=month)
        lines = [f"🏆 Кэшбек: {rows[0].category_raw} — {month_label}", ""]
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. {r.owner_name} — {r.bank_name} — {r.percent:g}%")
        return CashbackResult(status="query_found", text="\n".join(lines), target_month=month, records=tuple(rows))


class ListActiveCashbackCategoriesUseCase:
    def __init__(self, repo, *, now_provider=None) -> None:
        self.repo = repo
        self.now_provider = now_provider or (lambda: datetime.now(UTC).date())

    def execute(self, month: str | None = None, owner_name: str | None = None) -> CashbackResult:
        today = self.now_provider()
        target_month = month or current_year_month(today)
        month_label = format_month_label(target_month)
        if owner_name is not None and not validate_owner(owner_name):
            return CashbackResult(
                status="list_empty",
                target_month=target_month,
                owner_filter=None,
                text="Не удалось применить фильтр владельца. Открой «📋 Активные категории» заново.",
                error_code="invalid_owner_filter",
            )

        if owner_name is None:
            rows = tuple(self.repo.list_active(target_month))
        else:
            rows = tuple(self.repo.list_active_by_owner(target_month, owner_name))
        if not rows:
            if owner_name is None:
                return CashbackResult(status="list_empty", target_month=target_month, owner_filter=None, records=(), text=f"На {month_label} кэшбек-категорий пока нет.\n\nДобавь первую категорию в формате:\nАльфа, Владимир, май, Супермаркеты, 5%")
            return CashbackResult(
                status="list_empty",
                target_month=target_month,
                owner_filter=owner_name,
                records=(),
                text=f"На {month_label} для владельца {owner_name} кэшбек-категорий пока нет.",
            )

        header = f"📋 Активные категории кэшбека — {month_label}"
        if owner_name is not None:
            header = f"{header} — {owner_name}"
        lines = [header, ""]
        current = None
        global_index = 0
        for row in rows:
            if row.category_raw != current:
                if current is not None:
                    lines.append("")
                current = row.category_raw
                lines.append(current)
                lines.append("")
            global_index += 1
            lines.append(f"{global_index}. {row.owner_name} — {row.bank_name} — {row.percent:g}%")

        return CashbackResult(status="list_found", target_month=target_month, owner_filter=owner_name, records=rows, text="\n".join(lines))
