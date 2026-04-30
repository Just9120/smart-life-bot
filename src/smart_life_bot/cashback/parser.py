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
    return re.sub(r"\s+", " ", value.strip().lower().replace("ё", "е"))


def parse_month_token(token: str, today: date) -> str | None:
    t = normalize_category_key(token)
    if re.fullmatch(r"\d{4}-\d{2}", t):
        return t
    month = RU_MONTHS.get(t)
    return f"{today.year:04d}-{month:02d}" if month else None


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
    if len(parts) not in (4, 5):
        return None
    bank, owner = parts[0], parts[1]
    if len(parts) == 5:
        month = parse_month_token(parts[2], today)
        if month is None:
            raise ValueError("invalid_month")
        category, percent_raw = parts[3], parts[4]
    else:
        month = None
        category, percent_raw = parts[2], parts[3]
    m = re.match(r"^\s*(\d+(?:[\.,]\d+)?)\s*%?\s*$", percent_raw)
    if not m:
        return None
    return ParsedAdd(bank=bank, owner=owner, category=category, percent=float(m.group(1).replace(",", ".")), month=month)


def validate_owner(owner: str) -> bool:
    return owner.strip() in ALLOWED_OWNERS
