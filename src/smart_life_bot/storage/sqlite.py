"""SQLite storage implementation for repository contracts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from smart_life_bot.domain.enums import ConversationState, EventLogErrorCategory, EventLogStatus, ParserMode
from smart_life_bot.domain.models import ConversationStateSnapshot, EventDraft
from smart_life_bot.storage.interfaces import (
    EventLogEntry,
    ProviderCredentialsRecord,
    UserOAuthConnectionStateRecord,
    UserRecord,
    UserPreferencesRecord,
)


def utcnow_iso() -> str:
    """Return UTC timestamp in ISO-8601 string format."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def create_sqlite_connection(database_url: str) -> sqlite3.Connection:
    """Create sqlite3 connection from limited DATABASE_URL formats."""
    if database_url == "sqlite:///:memory:":
        connection = sqlite3.connect(":memory:")
    elif database_url.startswith("sqlite:///"):
        db_path = database_url.removeprefix("sqlite:///")
        if not db_path:
            raise ValueError("DATABASE_URL sqlite:/// path must not be empty.")
        resolved = Path(db_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(resolved))
    else:
        raise ValueError(
            "Unsupported DATABASE_URL format. Supported: sqlite:///:memory: or sqlite:///./path/to/file.db."
        )

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_sqlite_schema(connection: sqlite3.Connection) -> None:
    """Initialize SQLite tables required by storage contracts."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id INTEGER NOT NULL UNIQUE,
            timezone TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS provider_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            auth_mode TEXT NOT NULL,
            credentials_encrypted TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            UNIQUE (user_id, provider, auth_mode)
        );

        CREATE TABLE IF NOT EXISTS conversation_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            state TEXT NOT NULL,
            draft_payload TEXT,
            active_field TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS events_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            raw_text TEXT,
            parsed_payload TEXT,
            status TEXT NOT NULL,
            google_event_id TEXT,
            error_code TEXT,
            error_details TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER PRIMARY KEY,
            parser_mode TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS cashback_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_name TEXT NOT NULL,
            bank_name TEXT NOT NULL,
            category_raw TEXT NOT NULL,
            category_key TEXT NOT NULL,
            percent REAL NOT NULL,
            target_month TEXT NOT NULL,
            source_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            UNIQUE (target_month, owner_name, bank_name, category_key)
        );

        CREATE TABLE IF NOT EXISTS user_oauth_connection_state (
            user_id INTEGER PRIMARY KEY,
            status TEXT NOT NULL,
            state_token_hash TEXT,
            error_code TEXT,
            connected_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """
    )
    connection.commit()


def _row_to_user_record(row: sqlite3.Row) -> UserRecord:
    return UserRecord(
        id=row["id"],
        telegram_user_id=row["telegram_user_id"],
        timezone=row["timezone"],
        created_at=_parse_iso_datetime(row["created_at"]),
        updated_at=_parse_iso_datetime(row["updated_at"]),
    )


def _serialize_draft(draft: EventDraft | None) -> str | None:
    if draft is None:
        return None

    payload = asdict(draft)
    if draft.start_at is not None:
        payload["start_at"] = draft.start_at.isoformat()
    if draft.end_at is not None:
        payload["end_at"] = draft.end_at.isoformat()
    return json.dumps(payload)


def _deserialize_draft(payload: str | None) -> EventDraft | None:
    if payload is None:
        return None

    data = json.loads(payload)
    if data.get("start_at"):
        data["start_at"] = datetime.fromisoformat(data["start_at"])
    if data.get("end_at"):
        data["end_at"] = datetime.fromisoformat(data["end_at"])
    return EventDraft(**data)


def _row_to_event_log_entry(row: sqlite3.Row) -> EventLogEntry:
    parsed_payload = json.loads(row["parsed_payload"]) if row["parsed_payload"] else None
    return EventLogEntry(
        id=row["id"],
        user_id=row["user_id"],
        raw_text=row["raw_text"],
        parsed_payload=parsed_payload,
        status=EventLogStatus(row["status"]),
        google_event_id=row["google_event_id"],
        error_code=row["error_code"],
        error_details=row["error_details"],
        created_at=_parse_iso_datetime(row["created_at"]),
        updated_at=_parse_iso_datetime(row["updated_at"]),
    )


class SQLiteUsersRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_by_telegram_id(self, telegram_user_id: int) -> UserRecord | None:
        row = self._connection.execute(
            """
            SELECT id, telegram_user_id, timezone, created_at, updated_at
            FROM users
            WHERE telegram_user_id = ?
            """,
            (telegram_user_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_user_record(row)

    def create(self, telegram_user_id: int, timezone: str | None = None) -> UserRecord:
        now_iso = utcnow_iso()
        cursor = self._connection.execute(
            """
            INSERT INTO users (telegram_user_id, timezone, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (telegram_user_id, timezone, now_iso, now_iso),
        )
        self._connection.commit()
        return self._get_by_id_or_raise(cursor.lastrowid)

    def get_or_create_by_telegram_id(
        self,
        telegram_user_id: int,
        timezone: str | None = None,
    ) -> UserRecord:
        existing = self.get_by_telegram_id(telegram_user_id)
        if existing is not None:
            return existing
        return self.create(telegram_user_id=telegram_user_id, timezone=timezone)

    def _get_by_id_or_raise(self, user_id: int) -> UserRecord:
        row = self._connection.execute(
            """
            SELECT id, telegram_user_id, timezone, created_at, updated_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"User with id={user_id} not found after write.")
        return _row_to_user_record(row)


class SQLiteProviderCredentialsRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_for_user(
        self,
        user_id: int,
        provider: str,
        auth_mode: str,
    ) -> ProviderCredentialsRecord | None:
        row = self._connection.execute(
            """
            SELECT id, user_id, provider, auth_mode, credentials_encrypted, created_at, updated_at
            FROM provider_credentials
            WHERE user_id = ? AND provider = ? AND auth_mode = ?
            """,
            (user_id, provider, auth_mode),
        ).fetchone()
        if row is None:
            return None
        return ProviderCredentialsRecord(
            id=row["id"],
            user_id=row["user_id"],
            provider=row["provider"],
            auth_mode=row["auth_mode"],
            credentials_encrypted=row["credentials_encrypted"],
            created_at=_parse_iso_datetime(row["created_at"]),
            updated_at=_parse_iso_datetime(row["updated_at"]),
        )

    def save_for_user(
        self,
        user_id: int,
        provider: str,
        auth_mode: str,
        credentials_encrypted: str,
    ) -> ProviderCredentialsRecord:
        now_iso = utcnow_iso()
        self._connection.execute(
            """
            INSERT INTO provider_credentials (
                user_id,
                provider,
                auth_mode,
                credentials_encrypted,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, provider, auth_mode)
            DO UPDATE SET
                credentials_encrypted = excluded.credentials_encrypted,
                updated_at = excluded.updated_at
            """,
            (user_id, provider, auth_mode, credentials_encrypted, now_iso, now_iso),
        )
        self._connection.commit()

        record = self.get_for_user(user_id=user_id, provider=provider, auth_mode=auth_mode)
        if record is None:
            raise LookupError("Credentials not found after write.")
        return record


class SQLiteConversationStateRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, user_id: int) -> ConversationStateSnapshot | None:
        row = self._connection.execute(
            """
            SELECT user_id, state, draft_payload, active_field
            FROM conversation_state
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return ConversationStateSnapshot(
            user_id=row["user_id"],
            state=ConversationState(row["state"]),
            draft=_deserialize_draft(row["draft_payload"]),
            editing_field=row["active_field"],
        )

    def set(self, snapshot: ConversationStateSnapshot) -> None:
        now_iso = utcnow_iso()
        self._connection.execute(
            """
            INSERT INTO conversation_state (user_id, state, draft_payload, active_field, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (user_id)
            DO UPDATE SET
                state = excluded.state,
                draft_payload = excluded.draft_payload,
                active_field = excluded.active_field,
                updated_at = excluded.updated_at
            """,
            (
                snapshot.user_id,
                snapshot.state.value,
                _serialize_draft(snapshot.draft),
                snapshot.editing_field,
                now_iso,
            ),
        )
        self._connection.commit()

    def reset(self, user_id: int) -> None:
        self._connection.execute("DELETE FROM conversation_state WHERE user_id = ?", (user_id,))
        self._connection.commit()


class SQLiteUserPreferencesRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_for_user(self, user_id: int) -> UserPreferencesRecord | None:
        row = self._connection.execute(
            """
            SELECT user_id, parser_mode, created_at, updated_at
            FROM user_preferences
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return UserPreferencesRecord(
            user_id=row["user_id"],
            parser_mode=ParserMode(row["parser_mode"]),
            created_at=_parse_iso_datetime(row["created_at"]),
            updated_at=_parse_iso_datetime(row["updated_at"]),
        )

    def get_or_create_for_user(
        self,
        user_id: int,
        default_parser_mode: ParserMode,
    ) -> UserPreferencesRecord:
        existing = self.get_for_user(user_id=user_id)
        if existing is not None:
            return existing
        return self.set_parser_mode(user_id=user_id, parser_mode=default_parser_mode)

    def set_parser_mode(self, user_id: int, parser_mode: ParserMode) -> UserPreferencesRecord:
        now_iso = utcnow_iso()
        self._connection.execute(
            """
            INSERT INTO user_preferences (user_id, parser_mode, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (user_id)
            DO UPDATE SET
                parser_mode = excluded.parser_mode,
                updated_at = excluded.updated_at
            """,
            (user_id, parser_mode.value, now_iso, now_iso),
        )
        self._connection.commit()
        record = self.get_for_user(user_id)
        if record is None:
            raise LookupError("User preferences not found after write.")
        return record


class SQLiteEventsLogRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def append(self, entry: EventLogEntry) -> EventLogEntry:
        now_iso = utcnow_iso()
        cursor = self._connection.execute(
            """
            INSERT INTO events_log (
                user_id,
                raw_text,
                parsed_payload,
                status,
                google_event_id,
                error_code,
                error_details,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.user_id,
                entry.raw_text,
                json.dumps(entry.parsed_payload) if entry.parsed_payload is not None else None,
                entry.status.value,
                entry.google_event_id,
                entry.error_code,
                entry.error_details,
                now_iso,
                now_iso,
            ),
        )
        self._connection.commit()
        inserted = self.get_by_id(cursor.lastrowid)
        if inserted is None:
            raise LookupError("Events log entry not found after insert.")
        return inserted

    def update_status(
        self,
        entry_id: int,
        status: EventLogStatus,
        error_category: EventLogErrorCategory | None = None,
        google_event_id: str | None = None,
        error_code: str | None = None,
        error_details: str | None = None,
    ) -> None:
        resolved_error_code = error_code or (error_category.value if error_category else None)
        self._connection.execute(
            """
            UPDATE events_log
            SET
                status = ?,
                google_event_id = COALESCE(?, google_event_id),
                error_code = COALESCE(?, error_code),
                error_details = COALESCE(?, error_details),
                updated_at = ?
            WHERE id = ?
            """,
            (status.value, google_event_id, resolved_error_code, error_details, utcnow_iso(), entry_id),
        )
        self._connection.commit()

    def get_by_id(self, entry_id: int) -> EventLogEntry | None:
        row = self._connection.execute(
            """
            SELECT
                id, user_id, raw_text, parsed_payload, status, google_event_id, error_code, error_details,
                created_at, updated_at
            FROM events_log
            WHERE id = ?
            """,
            (entry_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_event_log_entry(row)

    def list_for_user(self, user_id: int) -> list[EventLogEntry]:
        rows = self._connection.execute(
            """
            SELECT
                id, user_id, raw_text, parsed_payload, status, google_event_id, error_code, error_details,
                created_at, updated_at
            FROM events_log
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,),
        ).fetchall()
        return [_row_to_event_log_entry(row) for row in rows]


def _row_to_oauth_state_record(row: sqlite3.Row) -> UserOAuthConnectionStateRecord:
    return UserOAuthConnectionStateRecord(
        user_id=row["user_id"],
        status=row["status"],
        state_token_hash=row["state_token_hash"],
        error_code=row["error_code"],
        connected_at=_parse_iso_datetime(row["connected_at"]) if row["connected_at"] else None,
        revoked_at=_parse_iso_datetime(row["revoked_at"]) if row["revoked_at"] else None,
        created_at=_parse_iso_datetime(row["created_at"]),
        updated_at=_parse_iso_datetime(row["updated_at"]),
    )


class SQLiteUserOAuthConnectionStateRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_for_user(self, user_id: int) -> UserOAuthConnectionStateRecord | None:
        row = self._connection.execute(
            "SELECT * FROM user_oauth_connection_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return _row_to_oauth_state_record(row) if row is not None else None

    def get_by_state_token_hash(self, state_token_hash: str) -> UserOAuthConnectionStateRecord | None:
        row = self._connection.execute(
            "SELECT * FROM user_oauth_connection_state WHERE state_token_hash = ?",
            (state_token_hash,),
        ).fetchone()
        return _row_to_oauth_state_record(row) if row is not None else None

    def get_or_create_for_user(self, user_id: int) -> UserOAuthConnectionStateRecord:
        existing = self.get_for_user(user_id)
        if existing is not None:
            return existing
        now_iso = utcnow_iso()
        self._connection.execute(
            """
            INSERT INTO user_oauth_connection_state (user_id, status, created_at, updated_at)
            VALUES (?, 'not_connected', ?, ?)
            """,
            (user_id, now_iso, now_iso),
        )
        self._connection.commit()
        record = self.get_for_user(user_id)
        if record is None:
            raise LookupError("OAuth state not found after create.")
        return record

    def mark_pending(self, user_id: int, state_token_hash: str) -> UserOAuthConnectionStateRecord:
        base = self.get_or_create_for_user(user_id)
        now_iso = utcnow_iso()
        self._connection.execute(
            """
            UPDATE user_oauth_connection_state
            SET status = 'pending', state_token_hash = ?, error_code = NULL, revoked_at = NULL, updated_at = ?
            WHERE user_id = ?
            """,
            (state_token_hash, now_iso, base.user_id),
        )
        self._connection.commit()
        return self.get_or_create_for_user(user_id)

    def mark_disconnected(self, user_id: int) -> UserOAuthConnectionStateRecord:
        base = self.get_or_create_for_user(user_id)
        now_iso = utcnow_iso()
        self._connection.execute(
            """
            UPDATE user_oauth_connection_state
            SET status = 'not_connected', state_token_hash = NULL, error_code = NULL, revoked_at = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (now_iso, now_iso, base.user_id),
        )
        self._connection.commit()
        return self.get_or_create_for_user(user_id)

    def mark_error(self, user_id: int, error_code: str) -> UserOAuthConnectionStateRecord:
        base = self.get_or_create_for_user(user_id)
        now_iso = utcnow_iso()
        self._connection.execute(
            """
            UPDATE user_oauth_connection_state
            SET status = 'error', error_code = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (error_code, now_iso, base.user_id),
        )
        self._connection.commit()
        return self.get_or_create_for_user(user_id)
