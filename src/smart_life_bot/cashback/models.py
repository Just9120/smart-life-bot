from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

ALLOWED_OWNERS = ("Виктор", "Владимир", "Елена")


@dataclass(frozen=True, slots=True)
class CashbackCategoryRecord:
    id: int
    owner_name: str
    bank_name: str
    category_raw: str
    category_key: str
    percent: float
    target_month: str
    source_text: str
    created_at: datetime
    updated_at: datetime
    is_deleted: bool


@dataclass(frozen=True, slots=True)
class CashbackAddInput:
    bank_name: str
    owner_name: str
    category_raw: str
    percent: float
    target_month: str
    source_text: str
