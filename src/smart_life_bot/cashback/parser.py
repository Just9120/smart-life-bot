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


def parse_month_token(token: str, today: date) -> str | None:
    t = normalize_category_key(token)
    if re.fullmatch(r"\d{4}-\d{2}", t):
        return t
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
    parsed = _parse_comma_separated_add(text, today)
    if parsed is not None:
        return parsed
    return _parse_space_separated_add(text, today)


def _parse_percent(raw: str) -> float | None:
    m = re.match(r"^\s*(\d+(?:[\.,]\d+)?)\s*%?\s*$", raw)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _parse_comma_separated_add(text: str, today: date) -> ParsedAdd | None:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) not in (4, 5):
        return None
    bank, owner = parts[0], parts[1]
    if len(parts) == 5:
        month = parse_month_token(parts[2], today)
        category, percent_raw = parts[3], parts[4]
    else:
        month = None
        category, percent_raw = parts[2], parts[3]
    percent = _parse_percent(percent_raw)
    if percent is None:
        return None
    return ParsedAdd(bank=bank, owner=owner, category=category, percent=percent, month=month)


def _parse_space_separated_add(text: str, today: date) -> ParsedAdd | None:
    tokens = [t.strip() for t in text.replace(",", " ").split() if t.strip()]
    if len(tokens) < 4:
        return None
    percent = _parse_percent(tokens[-1])
    if percent is None:
        return None

    owners = [i for i, token in enumerate(tokens[:-1]) if token in ALLOWED_OWNERS]
    if len(owners) != 1:
        return None
    owner_index = owners[0]
    owner = tokens[owner_index]

    bank_tokens = tokens[:owner_index]
    if not bank_tokens:
        return None
    bank = " ".join(bank_tokens).strip()
    if not bank:
        return None

    between = tokens[owner_index + 1 : -1]
    if not between:
        return None

    month = None
    category_tokens = between
    maybe_month = parse_month_token(between[0], today)
    if maybe_month is not None:
        month = maybe_month
        category_tokens = between[1:]

    if not category_tokens:
        return None
    category = " ".join(category_tokens).strip()
    if not category:
        return None

    return ParsedAdd(bank=bank, owner=owner, category=category, percent=percent, month=month)


def validate_owner(owner: str) -> bool:
    return owner.strip() in ALLOWED_OWNERS


def looks_like_cashback_add_attempt(text: str) -> bool:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 3 and "%" in text:
        return True
    tokens = [t.strip() for t in text.replace(",", " ").split() if t.strip()]
    if len(tokens) < 4:
        return False
    if not any(token in ALLOWED_OWNERS for token in tokens):
        return False
    return _parse_percent(tokens[-1]) is not None
