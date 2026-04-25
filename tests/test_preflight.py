from __future__ import annotations

import json
import socket

import pytest

from smart_life_bot.config.settings import Settings
from smart_life_bot.domain.enums import GoogleAuthMode
from smart_life_bot.runtime.preflight import PreflightError, run_preflight


@pytest.fixture
def base_settings() -> Settings:
    return Settings(
        app_env="dev",
        log_level="INFO",
        telegram_bot_token="test-telegram-token",
        google_auth_mode=GoogleAuthMode.OAUTH_USER_MODE,
        database_url="sqlite:///:memory:",
        default_timezone="UTC",
    )


def test_preflight_passes_in_oauth_user_mode(base_settings: Settings) -> None:
    result = run_preflight(base_settings)

    assert result.ok is True
    assert {check.name for check in result.checks} >= {
        "timezone",
        "service_account_config",
        "runtime_composition",
        "sqlite_schema",
    }


def test_preflight_passes_service_account_mode_with_json_file(tmp_path, base_settings: Settings) -> None:
    service_account_path = tmp_path / "service-account.json"
    service_account_path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "dev-project",
                "private_key_id": "fake-key-id",
                "private_key": "-----BEGIN PRIVATE KEY-----\\nFAKE\\n-----END PRIVATE KEY-----\\n",
                "client_email": "dev@example.iam.gserviceaccount.com",
            }
        ),
        encoding="utf-8",
    )

    result = run_preflight(
        Settings(
            app_env=base_settings.app_env,
            log_level=base_settings.log_level,
            telegram_bot_token=base_settings.telegram_bot_token,
            google_auth_mode=GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE,
            database_url=base_settings.database_url,
            default_timezone=base_settings.default_timezone,
            google_service_account_json=str(service_account_path),
            google_shared_calendar_id="calendar@example.com",
        )
    )

    assert result.ok is True


def test_preflight_passes_service_account_mode_with_raw_json(base_settings: Settings) -> None:
    payload = json.dumps(
        {
            "type": "service_account",
            "project_id": "dev-project",
            "private_key_id": "fake-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\\nFAKE\\n-----END PRIVATE KEY-----\\n",
            "client_email": "dev@example.iam.gserviceaccount.com",
        }
    )

    result = run_preflight(
        Settings(
            app_env=base_settings.app_env,
            log_level=base_settings.log_level,
            telegram_bot_token=base_settings.telegram_bot_token,
            google_auth_mode=GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE,
            database_url=base_settings.database_url,
            default_timezone=base_settings.default_timezone,
            google_service_account_json=payload,
            google_shared_calendar_id="calendar@example.com",
        )
    )

    assert result.ok is True


def test_preflight_fails_when_service_account_json_missing(base_settings: Settings) -> None:
    with pytest.raises(PreflightError, match="service account configuration") as error:
        run_preflight(
            Settings(
                app_env=base_settings.app_env,
                log_level=base_settings.log_level,
                telegram_bot_token=base_settings.telegram_bot_token,
                google_auth_mode=GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE,
                database_url=base_settings.database_url,
                default_timezone=base_settings.default_timezone,
                google_service_account_json=None,
                google_shared_calendar_id="calendar@example.com",
            )
        )

    assert "GOOGLE_SERVICE_ACCOUNT_JSON" in error.value.result.checks[-1].detail


def test_preflight_fails_when_shared_calendar_id_missing(base_settings: Settings) -> None:
    with pytest.raises(PreflightError, match="service account configuration") as error:
        run_preflight(
            Settings(
                app_env=base_settings.app_env,
                log_level=base_settings.log_level,
                telegram_bot_token=base_settings.telegram_bot_token,
                google_auth_mode=GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE,
                database_url=base_settings.database_url,
                default_timezone=base_settings.default_timezone,
                google_service_account_json='{"type":"service_account"}',
                google_shared_calendar_id=None,
            )
        )

    assert "GOOGLE_SHARED_CALENDAR_ID" in error.value.result.checks[-1].detail


def test_preflight_result_does_not_include_raw_telegram_token(base_settings: Settings) -> None:
    result = run_preflight(base_settings)
    serialized = str(result)

    assert base_settings.telegram_bot_token not in serialized


def test_preflight_result_does_not_include_raw_service_account_json(base_settings: Settings) -> None:
    payload = json.dumps(
        {
            "type": "service_account",
            "private_key": "-----BEGIN PRIVATE KEY-----\\nSECRET\\n-----END PRIVATE KEY-----",
        }
    )
    settings = Settings(
        app_env=base_settings.app_env,
        log_level=base_settings.log_level,
        telegram_bot_token=base_settings.telegram_bot_token,
        google_auth_mode=GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE,
        database_url=base_settings.database_url,
        default_timezone=base_settings.default_timezone,
        google_service_account_json=payload,
        google_shared_calendar_id="calendar@example.com",
    )

    result = run_preflight(settings)
    serialized = str(result)

    assert payload not in serialized
    assert "PRIVATE KEY" not in serialized


def test_preflight_does_not_call_network_apis(monkeypatch: pytest.MonkeyPatch, base_settings: Settings) -> None:
    def _deny_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("network calls are not allowed")

    monkeypatch.setattr(socket, "create_connection", _deny_network)

    result = run_preflight(base_settings)
    assert result.ok is True


def test_preflight_sqlite_schema_check_includes_expected_tables(base_settings: Settings) -> None:
    result = run_preflight(base_settings)

    sqlite_check = next(check for check in result.checks if check.name == "sqlite_schema")
    assert "users" in sqlite_check.detail
    assert "provider_credentials" in sqlite_check.detail
    assert "conversation_state" in sqlite_check.detail
    assert "events_log" in sqlite_check.detail
    assert "user_preferences" in sqlite_check.detail
