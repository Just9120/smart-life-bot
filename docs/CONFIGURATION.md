# Configuration / Env Model — Smart Life Ops Bot

## 1. Назначение

Документ фиксирует baseline переменных окружения для Phase 1 и разделяет:

- обязательные общие переменные;
- optional переменные;
- auth-mode-specific переменные.

Реальные значения, ключи и токены в документации не указываются.

## 2. Обязательные переменные (runtime foundation)

| Переменная | Обязательность | Пример placeholder | Чувствительная | Назначение |
|---|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Required | `<telegram_bot_token>` | **Да** | Токен Telegram-бота. |
| `GOOGLE_AUTH_MODE` | Required | `oauth_user_mode` | Нет | Выбранный auth mode (`oauth_user_mode` или `service_account_shared_calendar_mode`). |
| `DATABASE_URL` | Required | `sqlite:///./data/smart_life_bot.db` | Нет* | Строка подключения к хранилищу. |
| `DEFAULT_TIMEZONE` | Required | `UTC` | Нет | Таймзона по умолчанию, если пользовательская не задана. |

\* Может считаться чувствительной, если включает credentials (например, future PostgreSQL DSN с паролем).

Текущая runtime-реализация storage поддерживает минимум:
- `sqlite:///./data/smart_life_bot.db` (file-based SQLite, директория создается автоматически);
- `sqlite:///:memory:` (in-memory для тестов).

Runtime composition layer использует `DATABASE_URL` напрямую при `build_runtime(settings)` и всегда выполняет инициализацию SQLite schema при bootstrap.
Bootstrap-сообщение runtime не должно выводить raw `DATABASE_URL`; вместо этого используется безопасный признак конфигурации/back-end marker.

## 3. Optional переменные с default в коде

| Переменная | Default в `load_settings()` | Пример placeholder | Чувствительная | Назначение |
|---|---|---|---|---|
| `APP_ENV` | `dev` | `dev` | Нет | Режим приложения (`development`/`staging`/`production`). |
| `LOG_LEVEL` | `INFO` | `INFO` | Нет | Уровень логирования (`DEBUG`/`INFO`/`WARNING`/`ERROR`). |

## 4. Дополнительные optional переменные (пока не используются runtime foundation)

| Переменная | Пример placeholder | Чувствительная | Назначение |
|---|---|---|---|
| `LOG_FORMAT` | `json` | Нет | Формат логов (`json`/`text`). |
| `APP_PORT` | `8080` | Нет | Runtime-порт для web-компонентов (когда появятся). |
| `STATE_TTL_HOURS` | `24` | Нет | Время жизни conversation state (если включено). **Pending в архитектуре.** |

## 5. Переменные только для `oauth_user_mode`

| Переменная | Обязательность в режиме | Пример placeholder | Чувствительная | Назначение |
|---|---|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | Optional (станет required при runtime OAuth flow) | `<google_oauth_client_id>` | Умеренно | OAuth client id. |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Optional (станет required при runtime OAuth flow) | `<google_oauth_client_secret>` | **Да** | OAuth client secret. |
| `GOOGLE_OAUTH_REDIRECT_URI` | Optional (станет required при runtime OAuth flow) | `https://<your-domain>/oauth/google/callback` | Нет | Redirect URI для OAuth callback flow. |

## 6. Переменные только для `service_account_shared_calendar_mode`

| Переменная | Обязательность в режиме | Пример placeholder | Чувствительная | Назначение |
|---|---|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | **Required** при `service_account_shared_calendar_mode` | `<json_or_path_placeholder>` | **Да** | Service account credentials (raw JSON string или путь до JSON файла). |
| `GOOGLE_SHARED_CALENDAR_ID` | **Required** при `service_account_shared_calendar_mode` | `primary` / `<calendar_id>@group.calendar.google.com` | Нет | Calendar ID shared-календаря, куда выполняется запись событий. |

## 7. Правила безопасной работы с env

- Секреты (`TELEGRAM_BOT_TOKEN`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_SERVICE_ACCOUNT_JSON`) не коммитятся в Git.
- Для CI/CD и production используются только защищённые secret stores (GitHub Secrets/серверные env).
- В логах секреты маскируются; полные значения не выводятся.
- Для `service_account_shared_calendar_mode` целевой календарь должен быть явно расшарен на email service account, иначе create-event операции будут завершаться provider error.

## 8. Pending / Open questions

1. Нужен ли отдельный `ENCRYPTION_KEY` для шифрования `credentials_encrypted` на MVP-этапе runtime. **Open question**.
2. Нужна ли отдельная env-переменная для явного разделения `GOOGLE_SERVICE_ACCOUNT_JSON_RAW` и `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` при переходе к production hardening. **Open question**.


## 9. Safe preflight before VPS polling

Перед запуском polling на VPS рекомендуется выполнить безопасную диагностику:

```bash
python -m smart_life_bot.runtime.preflight
```

Preflight проверяет конфигурацию, таймзону, SQLite schema и runtime composition без запуска polling и без сетевых вызовов Telegram/Google API.

Для `service_account_shared_calendar_mode` допускаются два формата `GOOGLE_SERVICE_ACCOUNT_JSON`:
- raw JSON string;
- filesystem path до JSON-файла (рекомендуется для VPS эксплуатации).

`service_account` JSON и `.env` нельзя коммитить в репозиторий.
