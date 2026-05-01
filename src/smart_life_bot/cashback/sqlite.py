from __future__ import annotations

from smart_life_bot.cashback.models import CashbackAddInput, CashbackCategoryRecord
from smart_life_bot.cashback.parser import normalize_category_key
from smart_life_bot.storage.sqlite import _parse_iso_datetime, utcnow_iso


class SQLiteCashbackCategoriesRepository:
    def __init__(self, connection):
        self._connection = connection

    def upsert(self, payload: CashbackAddInput) -> tuple[CashbackCategoryRecord, bool, float | None]:
        category_key = normalize_category_key(payload.category_raw)
        existing = self._connection.execute(
            """SELECT * FROM cashback_categories WHERE target_month=? AND owner_name=? AND bank_name=? AND category_key=? AND is_deleted=0""",
            (payload.target_month, payload.owner_name, payload.bank_name, category_key),
        ).fetchone()
        now = utcnow_iso()
        if existing is not None:
            old = float(existing["percent"])
            self._connection.execute("UPDATE cashback_categories SET percent=?, source_text=?, updated_at=? WHERE id=?", (payload.percent, payload.source_text, now, existing["id"]))
            self._connection.commit()
            row = self._connection.execute("SELECT * FROM cashback_categories WHERE id=?", (existing["id"],)).fetchone()
            return self._to_record(row), True, old
        self._connection.execute(
            """INSERT INTO cashback_categories (owner_name, bank_name, category_raw, category_key, percent, target_month, source_text, created_at, updated_at, is_deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (payload.owner_name, payload.bank_name, payload.category_raw, category_key, payload.percent, payload.target_month, payload.source_text, now, now),
        )
        self._connection.commit()
        row = self._connection.execute("SELECT * FROM cashback_categories ORDER BY id DESC LIMIT 1").fetchone()
        return self._to_record(row), False, None

    def query(self, category_key: str, target_month: str) -> list[CashbackCategoryRecord]:
        rows = self._connection.execute(
            "SELECT * FROM cashback_categories WHERE category_key=? AND target_month=? AND is_deleted=0 ORDER BY percent DESC, owner_name ASC",
            (category_key, target_month),
        ).fetchall()
        return [self._to_record(r) for r in rows]

    def list_active(self, target_month: str) -> list[CashbackCategoryRecord]:
        rows = self._connection.execute("SELECT * FROM cashback_categories WHERE target_month=? AND is_deleted=0 ORDER BY category_key ASC, percent DESC", (target_month,)).fetchall()
        return [self._to_record(r) for r in rows]

    def list_active_by_owner(self, target_month: str, owner_name: str) -> list[CashbackCategoryRecord]:
        rows = self._connection.execute(
            "SELECT * FROM cashback_categories WHERE target_month=? AND owner_name=? AND is_deleted=0 ORDER BY category_key ASC, percent DESC",
            (target_month, owner_name),
        ).fetchall()
        return [self._to_record(r) for r in rows]

    def get_by_id(self, record_id: int) -> CashbackCategoryRecord | None:
        row = self._connection.execute(
            "SELECT * FROM cashback_categories WHERE id=?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return self._to_record(row)

    def soft_delete(self, record_id: int) -> CashbackCategoryRecord | None:
        now = utcnow_iso()
        cursor = self._connection.execute(
            "UPDATE cashback_categories SET is_deleted=1, updated_at=? WHERE id=? AND is_deleted=0",
            (now, record_id),
        )
        if cursor.rowcount == 0:
            return None
        self._connection.commit()
        row = self._connection.execute("SELECT * FROM cashback_categories WHERE id=?", (record_id,)).fetchone()
        if row is None:
            return None
        return self._to_record(row)

    def _to_record(self, row) -> CashbackCategoryRecord:
        return CashbackCategoryRecord(id=row["id"], owner_name=row["owner_name"], bank_name=row["bank_name"], category_raw=row["category_raw"], category_key=row["category_key"], percent=float(row["percent"]), target_month=row["target_month"], source_text=row["source_text"], created_at=_parse_iso_datetime(row["created_at"]), updated_at=_parse_iso_datetime(row["updated_at"]), is_deleted=bool(row["is_deleted"]))
