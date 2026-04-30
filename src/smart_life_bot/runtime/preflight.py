"""Safe runtime preflight diagnostics for VPS readiness checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from smart_life_bot.config.settings import ConfigurationError, Settings, load_settings
from smart_life_bot.domain.enums import GoogleAuthMode
from smart_life_bot.runtime.composition import build_runtime

EXPECTED_SQLITE_TABLES = {
    "users",
    "provider_credentials",
    "conversation_state",
    "events_log",
    "user_preferences",
    "cashback_categories",
}


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class PreflightResult:
    ok: bool
    checks: list[PreflightCheck]


class PreflightError(RuntimeError):
    """Raised when one or more preflight checks fail."""

    def __init__(self, message: str, *, result: PreflightResult) -> None:
        super().__init__(message)
        self.result = result


def _database_backend(database_url: str) -> str:
    if database_url.startswith("sqlite://"):
        return "sqlite"
    return "configured"


def _is_json_payload(value: str) -> bool:
    trimmed = value.lstrip()
    return trimmed.startswith("{")


def _validate_service_account_settings(settings: Settings) -> None:
    if settings.google_auth_mode is not GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE:
        return

    service_account_json = (settings.google_service_account_json or "").strip()
    shared_calendar_id = (settings.google_shared_calendar_id or "").strip()

    if not service_account_json:
        raise ConfigurationError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is required for service_account_shared_calendar_mode"
        )
    if not shared_calendar_id:
        raise ConfigurationError(
            "GOOGLE_SHARED_CALENDAR_ID is required for service_account_shared_calendar_mode"
        )

    if _is_json_payload(service_account_json):
        try:
            json.loads(service_account_json)
        except json.JSONDecodeError as error:
            raise ConfigurationError(
                "GOOGLE_SERVICE_ACCOUNT_JSON must be valid JSON when passed inline"
            ) from error
        return

    path = Path(service_account_json)
    if not path.exists() or not path.is_file():
        raise ConfigurationError("GOOGLE_SERVICE_ACCOUNT_JSON file path does not exist")

    try:
        path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError("GOOGLE_SERVICE_ACCOUNT_JSON file path is not readable") from error


def _validate_llm_settings(settings: Settings) -> None:
    if settings.llm_provider is None:
        return
    if settings.llm_provider != "anthropic":
        raise ConfigurationError("Unsupported LLM_PROVIDER. Supported values: anthropic")
    if not settings.anthropic_api_key:
        raise ConfigurationError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")


def _format_report(settings: Settings, checks: list[PreflightCheck]) -> str:
    check_map = {check.name: check for check in checks}

    lines = [
        "Smart Life Bot preflight diagnostics",
        f"app_env={settings.app_env}",
        f"google_auth_mode={settings.google_auth_mode.value}",
        f"database_backend={_database_backend(settings.database_url)}",
        "database_url_configured=true",
        f"telegram_bot_token_configured={str(bool(settings.telegram_bot_token)).lower()}",
        f"google_service_account_configured={str(bool(settings.google_service_account_json)).lower()}",
        f"google_shared_calendar_id_configured={str(bool(settings.google_shared_calendar_id)).lower()}",
        f"llm_provider={settings.llm_provider or 'none'}",
        f"llm_configured={str(settings.llm_provider == 'anthropic' and bool(settings.anthropic_api_key)).lower()}",
        f"llm_model_configured={str(bool(settings.llm_model)).lower()}",
        f"timezone={settings.default_timezone}",
        f"runtime_composition={check_map.get('runtime_composition', PreflightCheck('', 'failed', '')).status}",
        f"sqlite_schema={check_map.get('sqlite_schema', PreflightCheck('', 'failed', '')).status}",
    ]
    for check in checks:
        lines.append(f"check[{check.name}]={check.status}: {check.detail}")
    return "\n".join(lines)


def run_preflight(settings: Settings | None = None) -> PreflightResult:
    """Run safe diagnostics for environment, runtime composition, and SQLite schema wiring."""
    resolved_settings = settings or load_settings()
    checks: list[PreflightCheck] = []

    try:
        ZoneInfo(resolved_settings.default_timezone)
    except ZoneInfoNotFoundError as error:
        checks.append(
            PreflightCheck(
                name="timezone",
                status="failed",
                detail="DEFAULT_TIMEZONE is invalid or unavailable in runtime tzdata",
            )
        )
        result = PreflightResult(ok=False, checks=checks)
        raise PreflightError("Preflight failed: invalid timezone configuration", result=result) from error
    checks.append(PreflightCheck(name="timezone", status="ok", detail="Timezone is available"))

    try:
        _validate_service_account_settings(resolved_settings)
    except ConfigurationError as error:
        checks.append(
            PreflightCheck(
                name="service_account_config",
                status="failed",
                detail=str(error),
            )
        )
        result = PreflightResult(ok=False, checks=checks)
        raise PreflightError("Preflight failed: invalid service account configuration", result=result) from error

    checks.append(
        PreflightCheck(
            name="service_account_config",
            status="ok",
            detail="Auth-mode-specific configuration validated",
        )
    )

    try:
        _validate_llm_settings(resolved_settings)
    except ConfigurationError as error:
        checks.append(
            PreflightCheck(
                name="llm_config",
                status="failed",
                detail=str(error),
            )
        )
        result = PreflightResult(ok=False, checks=checks)
        raise PreflightError("Preflight failed: invalid llm configuration", result=result) from error
    checks.append(
        PreflightCheck(
            name="llm_config",
            status="ok",
            detail="LLM configuration validated",
        )
    )

    container = None
    try:
        container = build_runtime(resolved_settings)

        if container.runtime is None or container.runtime.router is None:
            raise RuntimeError("Runtime composition returned an incomplete runtime graph")
        checks.append(
            PreflightCheck(
                name="runtime_composition",
                status="ok",
                detail="Runtime and router were composed successfully",
            )
        )

        tables = {
            row[0]
            for row in container.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing_tables = EXPECTED_SQLITE_TABLES.difference(tables)
        if missing_tables:
            raise RuntimeError(f"SQLite schema is missing expected tables: {', '.join(sorted(missing_tables))}")

        checks.append(
            PreflightCheck(
                name="sqlite_schema",
                status="ok",
                detail=f"SQLite schema initialized ({', '.join(sorted(EXPECTED_SQLITE_TABLES))})",
            )
        )
    except Exception as error:
        if all(check.name != "runtime_composition" for check in checks):
            checks.append(
                PreflightCheck(
                    name="runtime_composition",
                    status="failed",
                    detail="Runtime composition failed",
                )
            )
        if all(check.name != "sqlite_schema" for check in checks):
            checks.append(
                PreflightCheck(
                    name="sqlite_schema",
                    status="failed",
                    detail="SQLite schema check failed",
                )
            )
        result = PreflightResult(ok=False, checks=checks)
        raise PreflightError("Preflight failed: runtime or SQLite checks failed", result=result) from error
    finally:
        if container is not None:
            container.connection.close()

    return PreflightResult(ok=True, checks=checks)


def main() -> None:
    """CLI entrypoint for safe VPS preflight diagnostics."""
    try:
        settings = load_settings()
        result = run_preflight(settings)
        print(_format_report(settings, result.checks))
    except (ConfigurationError, PreflightError) as error:
        if isinstance(error, PreflightError):
            print(_format_report(settings, error.result.checks))
        print(f"preflight_error={error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
