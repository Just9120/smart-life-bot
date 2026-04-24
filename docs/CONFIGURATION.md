# Configuration / Env Model — Smart Life Ops Bot

## 1. Назначение

Документ фиксирует baseline переменных окружения для Phase 1 и разделяет:

- обязательные общие переменные;
- optional переменные;
- auth-mode-specific переменные.

Реальные значения, ключи и токены в документации не указываются.

## 2. Обязательные общие переменные

| Переменная | Обязательность | Пример placeholder | Чувствительная | Назначение |
|---|---|---|---|---|
| `APP_ENV` | Required | `development` | Нет | Режим приложения (`development`/`staging`/`production`). |
| `LOG_LEVEL` | Required | `INFO` | Нет | Уровень логирования (`DEBUG`/`INFO`/`WARNING`/`ERROR`). |
| `TELEGRAM_BOT_TOKEN` | Required | `<telegram_bot_token>` | **Да** | Токен Telegram-бота. |
| `GOOGLE_AUTH_MODE` | Required | `oauth_user_mode` | Нет | Выбранный auth mode (`oauth_user_mode` или `service_account_shared_calendar_mode`). |
| `DATABASE_URL` | Required | `sqlite:///./data/smart_life_bot.db` | Нет* | Строка подключения к хранилищу. |
| `DEFAULT_TIMEZONE` | Required | `UTC` | Нет | Таймзона по умолчанию, если пользовательская не задана. |

\* Может считаться чувствительной, если включает credentials (например, future PostgreSQL DSN с паролем).

## 3. Optional переменные

| Переменная | Пример placeholder | Чувствительная | Назначение |
|---|---|---|---|
| `LOG_FORMAT` | `json` | Нет | Формат логов (`json`/`text`). |
| `APP_PORT` | `8080` | Нет | Runtime-порт для web-компонентов (когда появятся). |
| `STATE_TTL_HOURS` | `24` | Нет | Время жизни conversation state (если включено). **Pending в архитектуре.** |

## 4. Переменные только для `oauth_user_mode`

| Переменная | Обязательность в режиме | Пример placeholder | Чувствительная | Назначение |
|---|---|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | Required | `<google_oauth_client_id>` | Умеренно | OAuth client id. |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Required | `<google_oauth_client_secret>` | **Да** | OAuth client secret. |
| `GOOGLE_OAUTH_REDIRECT_URI` | Required | `https://<your-domain>/oauth/google/callback` | Нет | Redirect URI для OAuth callback flow. |

## 5. Переменные только для `service_account_shared_calendar_mode`

| Переменная | Обязательность в режиме | Пример placeholder | Чувствительная | Назначение |
|---|---|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Required | `<json_or_path_placeholder>` | **Да** | Service account credentials (JSON string или безопасный путь). |

## 6. Правила безопасной работы с env

- Секреты (`TELEGRAM_BOT_TOKEN`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_SERVICE_ACCOUNT_JSON`) не коммитятся в Git.
- Для CI/CD и production используются только защищённые secret stores (GitHub Secrets/серверные env).
- В логах секреты маскируются; полные значения не выводятся.

## 7. Pending / Open questions

1. Нужен ли отдельный `ENCRYPTION_KEY` для шифрования `credentials_encrypted` на MVP-этапе runtime. **Open question**.
2. Финальный формат передачи `GOOGLE_SERVICE_ACCOUNT_JSON` (raw JSON vs file path) для production. **Pending**.
