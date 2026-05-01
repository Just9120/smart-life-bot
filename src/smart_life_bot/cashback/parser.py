from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .models import ALLOWED_OWNERS

RU_MONTHS = {
    "январь": 1, "января": 1, "февраль": 2, "февраля": 2, "март": 3, "марта": 3,
    "апрель": 4, "апреля": 4, "май": 5, "мая": 5, "июнь": 6, "июня": 6,
    "июль": 7, "июля": 7, "август": 8, "августа": 8, "сентябрь": 9, "сентября": 9,
    "октябрь": 10, "октября": 10, "ноябрь": 11, "ноября": 11, "декабрь": 12, "декабря": 12,
}


def normalize_category_key(value: str) -> str:
    value = value.strip().lower().replace("ё", "е")
    return re.sub(r"\s+", " ", value)

def normalize_bank_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    cleaned = re.sub(r"\s*-\s*", "-", cleaned)
    canonical_key = re.sub(r"[\s-]+", "", cleaned).lower().replace("ё", "е")
    if canonical_key == "тбанк":
        return "Т-Банк"
    return cleaned


def parse_month_token(token: str, today: date) -> str | None:
    t = normalize_category_key(token)
    if re.fullmatch(r"\d{4}-\d{2}", t):
        parsed = _parse_year_month_token(t)
        if parsed is None:
            return None
        year, month = parsed
        return f"{year:04d}-{month:02d}"
    month = RU_MONTHS.get(t)
    if month is None:
        return None
    return f"{today.year:04d}-{month:02d}"


def in_transition_period(today: date) -> bool:
    return today.day >= 25


@dataclass(frozen=True, slots=True)
class ParsedAdd:
    bank: str
    owner: str
    category: str
    percent: float
    month: str | None


def parse_structured_add(text: str, today: date) -> ParsedAdd | None:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) in (4, 5):
        bank, owner = parts[0], parts[1]
        if len(parts) == 5:
            month = parse_month_token(parts[2], today)
            category, percent_raw = parts[3], parts[4]
        else:
            month = None
            category, percent_raw = parts[2], parts[3]
        percent = parse_percent_value(percent_raw)
        if percent is not None:
            return ParsedAdd(bank=bank, owner=owner, category=category, percent=percent, month=month)

    return _parse_space_fallback(text, today)


def _parse_space_fallback(text: str, today: date) -> ParsedAdd | None:
    tokens = [t.strip() for t in re.split(r"[\s,]+", text.strip()) if t.strip()]
    if len(tokens) < 4:
        return None

    percent_match = re.match(r"^(\d+(?:[\.,]\d+)?)%$", tokens[-1])
    if not percent_match:
        return None
    percent = float(percent_match.group(1).replace(",", "."))

    owner_indexes = [idx for idx, token in enumerate(tokens[:-1]) if token in ALLOWED_OWNERS]
    if len(owner_indexes) != 1:
        return None
    owner_idx = owner_indexes[0]
    owner = tokens[owner_idx]

    bank_tokens = tokens[:owner_idx]
    if not bank_tokens:
        return None

    cursor = owner_idx + 1
    month: str | None = None
    if cursor < len(tokens) - 1:
        maybe_month = parse_month_token(tokens[cursor], today)
        if maybe_month is not None:
            month = maybe_month
            cursor += 1

    category_tokens = tokens[cursor:-1]
    if not category_tokens:
        return None

    return ParsedAdd(
        bank=" ".join(bank_tokens),
        owner=owner,
        category=" ".join(category_tokens),
        percent=percent,
        month=month,
    )


def parse_percent_value(raw: str) -> float | None:
    match = re.match(r"^\s*(\d+(?:[\.,]\d+)?)\s*%?\s*$", raw)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    if value <= 0:
        return None
    return value


def validate_owner(owner: str) -> bool:
    return owner.strip() in ALLOWED_OWNERS


def looks_like_cashback_add_attempt(text: str) -> bool:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 3 and "%" in text:
        return True
    tokens = [t for t in re.split(r"[\s,]+", text.strip()) if t]
    if len(tokens) < 4:
        return False
    if not re.match(r"^\d+(?:[\.,]\d+)?%$", tokens[-1]):
        return False
    return any(token in ALLOWED_OWNERS for token in tokens[:-1])


def has_invalid_explicit_month_token(text: str, today: date) -> bool:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) == 5:
        month_token = parts[2]
        if re.fullmatch(r"\d{4}-\d{2}", normalize_category_key(month_token)):
            return parse_month_token(month_token, today) is None
        return False

    tokens = [t.strip() for t in re.split(r"[\s,]+", text.strip()) if t.strip()]
    if len(tokens) < 5:
        return False
    owner_indexes = [idx for idx, token in enumerate(tokens[:-1]) if token in ALLOWED_OWNERS]
    if len(owner_indexes) != 1:
        return False
    month_idx = owner_indexes[0] + 1
    if month_idx >= len(tokens) - 1:
        return False
    month_token = tokens[month_idx]
    if re.fullmatch(r"\d{4}-\d{2}", normalize_category_key(month_token)):
        return parse_month_token(month_token, today) is None
    return False


def _parse_year_month_token(value: str) -> tuple[int, int] | None:
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
