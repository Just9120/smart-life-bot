from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from smart_life_bot.cashback.models import ALLOWED_OWNERS, CashbackAddInput
from smart_life_bot.cashback.parser import has_invalid_explicit_month_token, has_invalid_owner_first_explicit_month_token, in_transition_period, looks_like_cashback_add_attempt, normalize_bank_name, normalize_category_key, normalize_category_search_key, parse_owner_first_multi_add, parse_percent_value, parse_structured_add, validate_owner

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
    status: Literal["added", "updated", "already_exists", "invalid_owner", "transition_month_required", "not_cashback_add", "query_found", "query_not_found", "invalid_month", "list_found", "list_empty", "delete_confirmation", "delete_cancelled", "deleted", "delete_not_found", "delete_invalid_callback", "invalid_format", "edit_percent_not_found", "edit_percent_invalid", "edit_percent_updated", "edit_percent_no_change"]
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
                "Удалить эту кэшбек-категорию из активных?\n"
                f"{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}\n\n"
                "После подтверждения категория исчезнет из активных."
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


class RequestEditCashbackCategoryPercentUseCase:
    def __init__(self, repo) -> None:
        self.repo = repo

    def execute(self, record_id_raw: str) -> CashbackResult:
        if not record_id_raw.isdigit():
            return CashbackResult(status="edit_percent_not_found", text="Не удалось разобрать запись. Открой «📋 Активные категории» заново.")
        record = self.repo.get_by_id(int(record_id_raw))
        if record is None or record.is_deleted:
            return CashbackResult(status="edit_percent_not_found", text="Запись не найдена или уже неактуальна. Обнови «📋 Активные категории».")
        month_label = format_month_label(record.target_month)
        return CashbackResult(
            status="edit_percent_no_change",
            text=f"Изменение процента:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — сейчас {record.percent:g}% — {month_label}",
            target_month=record.target_month,
            records=(record,),
            old_percent=record.percent,
            new_percent=record.percent,
        )


class UpdateCashbackCategoryPercentUseCase:
    def __init__(self, repo) -> None:
        self.repo = repo

    def execute(self, record_id_raw: str, percent_raw: str) -> CashbackResult:
        if not record_id_raw.isdigit():
            return CashbackResult(status="edit_percent_not_found", text="Не удалось разобрать запись. Открой «📋 Активные категории» заново.")
        percent = parse_percent_value(percent_raw)
        if percent is None:
            return CashbackResult(
                status="edit_percent_invalid",
                text="Не получилось распознать процент.\nНапиши, например: 7%, 7,5% или 7.5%.",
                error_code="invalid_percent",
            )
        updated = self.repo.update_percent(int(record_id_raw), percent)
        if updated is None:
            return CashbackResult(status="edit_percent_not_found", text="Запись не найдена или уже неактуальна. Обнови «📋 Активные категории».")
        record, change = updated
        month_label = format_month_label(record.target_month)
        if change == "no_change":
            return CashbackResult(
                status="edit_percent_no_change",
                text=f"Процент уже такой — ничего не изменил.\n{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}",
                target_month=record.target_month,
                records=(record,),
                old_percent=record.percent,
                new_percent=record.percent,
            )
        return CashbackResult(
            status="edit_percent_updated",
            text=f"Готово, обновил процент.\n{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}",
            target_month=record.target_month,
            records=(record,),
            updated=True,
            new_percent=record.percent,
        )


class AddCashbackCategoryUseCase:
    def __init__(self, repo, *, now_provider=None) -> None:
        self.repo = repo
        self.now_provider = now_provider or (lambda: datetime.now(UTC).date())

    def execute(self, text: str) -> CashbackResult | None:
        today = self.now_provider()
        if has_invalid_owner_first_explicit_month_token(text, today):
            return CashbackResult(status="invalid_month", text="Некорректный месяц.\nИспользуй русское название месяца или YYYY-MM, например: май или 2026-05.", error_code="invalid_month")
        parsed_multi = parse_owner_first_multi_add(text, today)
        if parsed_multi is not None:
            if len(parsed_multi.pairs) > 5:
                return CashbackResult(status="invalid_format", text="Можно добавить не больше 5 категорий за раз.", error_code="too_many_categories")
            month = parsed_multi.month
            if month is None and in_transition_period(today):
                current_month = current_year_month(today)
                next_month = shift_year_month(current_month, delta=1)
                candidate_months = (current_month, next_month) if next_month is not None else (current_month,)
                return CashbackResult(
                    status="transition_month_required",
                    text="Сейчас переходный период между месяцами. К какому месяцу отнести категории?",
                    error_code="transition_month_required",
                    candidate_months=candidate_months,
                    pending_add=CashbackAddInput(normalize_bank_name(parsed_multi.bank), parsed_multi.owner, "\n".join(f"{c}|{p}" for c, p in parsed_multi.pairs), 0.0, current_month, text),
                )
            target_month = month or current_year_month(today)
            lines = [f"Готово, обработал {len(parsed_multi.pairs)} категории за {format_month_label(target_month)}:"]
            updated = created = False
            records = []
            for idx, (category, percent) in enumerate(parsed_multi.pairs, start=1):
                record, change, _old = self.repo.upsert(CashbackAddInput(normalize_bank_name(parsed_multi.bank), parsed_multi.owner, category, percent, target_month, text))
                records.append(record)
                if change == "updated":
                    updated = True
                    lines.append(f"{idx}. {category} — обновлено до {record.percent:g}%")
                elif change == "no_change":
                    lines.append(f"{idx}. {category} — уже было {record.percent:g}%")
                else:
                    created = True
                    lines.append(f"{idx}. {category} — добавлено {record.percent:g}%")
            return CashbackResult(status="added", text="\n".join(lines), target_month=target_month, created=created, updated=updated, records=tuple(records))
        normalized_tokens = [t for t in text.replace(",", " ").split() if t]
        if normalized_tokens and normalized_tokens[0] in ALLOWED_OWNERS and "%" in text:
            return CashbackResult(
                status="invalid_format",
                text=(
                    "Не получилось распознать категории.\n"
                    "Формат: Владимир, Т-Банк, май, Супермаркеты 5%, Аптеки 5%"
                ),
                error_code="invalid_format",
            )

        if has_invalid_explicit_month_token(text, today):
            return CashbackResult(status="invalid_month", text="Некорректный месяц.\nИспользуй русское название месяца или YYYY-MM, например: май или 2026-05.", error_code="invalid_month")
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
                    pending_add=CashbackAddInput(normalize_bank_name(parsed.bank), parsed.owner, parsed.category, parsed.percent, current_month, text),
                )
            month = current_year_month(today)
        else:
            month = parsed.month
        normalized_bank = normalize_bank_name(parsed.bank)
        record, change, old = self.repo.upsert(CashbackAddInput(normalized_bank, parsed.owner, parsed.category, parsed.percent, month, text))
        month_label = format_month_label(month)
        if change == "updated":
            return CashbackResult(status="updated", text=f"Обновил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — было {old:g}%, стало {record.percent:g}% — {month_label}", target_month=month, updated=True, records=(record,), old_percent=old, new_percent=record.percent)
        if change == "no_change":
            return CashbackResult(status="already_exists", text=f"Такая категория уже есть:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}", target_month=month, records=(record,), old_percent=old, new_percent=record.percent)
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
        if payload.percent == 0.0 and "|" in payload.category_raw:
            lines_raw = [line.strip() for line in payload.category_raw.splitlines() if line.strip()]
            parsed_pairs: list[tuple[str, float]] = []
            for line in lines_raw:
                category, percent_raw = line.split("|", maxsplit=1)
                parsed_pairs.append((category, float(percent_raw)))
            if len(parsed_pairs) > 5:
                return CashbackResult(status="invalid_format", text="Можно добавить не больше 5 категорий за раз.", error_code="too_many_categories")
            lines = [f"Готово, обработал {len(parsed_pairs)} категории за {format_month_label(selected_month)}:"]
            records = []
            created = updated = False
            for idx, (category, percent) in enumerate(parsed_pairs, start=1):
                record, change, _old = self.repo.upsert(CashbackAddInput(payload.bank_name, payload.owner_name, category, percent, selected_month, payload.source_text))
                records.append(record)
                if change == "updated":
                    updated = True
                    lines.append(f"{idx}. {category} — обновлено до {record.percent:g}%")
                elif change == "no_change":
                    lines.append(f"{idx}. {category} — уже было {record.percent:g}%")
                else:
                    created = True
                    lines.append(f"{idx}. {category} — добавлено {record.percent:g}%")
            return CashbackResult(status="added", text="\n".join(lines), target_month=selected_month, created=created, updated=updated, records=tuple(records))
        record, change, old = self.repo.upsert(
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
        if change == "updated":
            return CashbackResult(status="updated", text=f"Обновил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — было {old:g}%, стало {record.percent:g}% — {month_label}", target_month=selected_month, updated=True, records=(record,), old_percent=old, new_percent=record.percent)
        if change == "no_change":
            return CashbackResult(status="already_exists", text=f"Такая категория уже есть:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}", target_month=selected_month, records=(record,), old_percent=old, new_percent=record.percent)
        return CashbackResult(status="added", text=f"Готово. Добавил кэшбек:\n{record.owner_name} — {record.bank_name} — {record.category_raw} — {record.percent:g}% — {month_label}", target_month=selected_month, created=True, records=(record,), new_percent=record.percent)


class QueryCashbackCategoryUseCase:
    def __init__(self, repo, *, now_provider=None) -> None:
        self.repo = repo
        self.now_provider = now_provider or (lambda: datetime.now(UTC).date())

    def execute(self, text: str) -> CashbackResult:
        today = self.now_provider()
        month = current_year_month(today)
        month_label = format_month_label(month)
        key = normalize_category_search_key(text)
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
                return CashbackResult(status="list_empty", target_month=target_month, owner_filter=None, records=(), text=f"На {month_label} активных кэшбек-категорий пока нет.\nМожно выбрать другой месяц или добавить категорию.")
            return CashbackResult(
                status="list_empty",
                target_month=target_month,
                owner_filter=owner_name,
                records=(),
                text=f"На {month_label} у {owner_name} пока нет активных кэшбек-категорий.\nМожно выбрать другого владельца, другой месяц или добавить категорию.",
            )

        lines = [f"Активные кэшбек-категории — {month_label}"]
        if owner_name is not None:
            lines.extend([f"Владелец: {owner_name}", ""])
        else:
            lines.append("")
        current = None
        global_index = 0
        for row in rows:
            if row.category_raw != current:
                if current is not None:
                    lines.append("")
                current = row.category_raw
                lines.append(current)
            global_index += 1
            if owner_name is None:
                row_text = f"{global_index}. {row.owner_name} — {row.bank_name} — {row.percent:g}%"
            else:
                row_text = f"{global_index}. {row.bank_name} — {row.percent:g}%"
            lines.append(row_text)

        return CashbackResult(status="list_found", target_month=target_month, owner_filter=owner_name, records=rows, text="\n".join(lines))
