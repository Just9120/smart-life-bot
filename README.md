# Smart Life Ops Bot

Smart Life Ops Bot — это Telegram-ассистент, сфокусированный на быстром и надежном добавлении событий в Google Calendar с обязательным подтверждением перед записью каждого события.

**Текущий статус:** runtime foundation phase 1 (включая SQLite storage foundation, minimal Telegram transport foundation для `/start`, text, confirm/edit/cancel mapping, explicit runtime composition foundation, foundation-адаптер `python-telegram-bot` для маппинга real Telegram updates в существующий runtime, детерминированный rule-based parser baseline без LLM и foundation-адаптер реальной записи в Google Calendar для `service_account_shared_calendar_mode`).

## Назначение продукта (MVP)

- Канал ввода: Telegram-бот.
- Основной поток: message → parsing → preview → confirm / edit / cancel → create Google Calendar event.
- Приоритеты: надежность, прозрачность, управляемость, быстрый выход к полезному результату.

## Структура репозитория

- `docs/PRD_MVP.md` — краткие продуктовые требования MVP.
- `docs/ARCHITECTURE.md` — детальная архитектура Phase 1 (слои, зависимости, flow, границы).
- `docs/DEPLOYMENT.md` — базовые принципы деплоя и ограничения окружения.
- `docs/DECISIONS.md` — журнал архитектурных и технических решений в формате ADR-like.
- `docs/PHASE1_TECHNICAL_SPEC.md` — рабочая техническая спецификация Phase 1 для следующих PR.
- `docs/CONFIGURATION.md` — модель конфигурации и переменных окружения.
- `src/smart_life_bot/` — Python-пакет с runtime foundation layer (config/domain/application/storage/auth/calendar/parsing/observability + bot transport + runtime composition module).
- `tests/` — smoke-уровень тестов для foundation-слоя.
- `.github/workflows/ci.yml` — минимальный CI pipeline.

## Локальный запуск заглушки

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Важно: .env не загружается автоматически на текущем этапе.
# Экспортируйте переменные в shell перед запуском.
set -a; source .env; set +a
python -m smart_life_bot.main
python -m pytest
```

Текущая точка входа приложения (`python -m smart_life_bot.main`) собирает runtime graph через composition layer (`settings → SQLite → repositories → adapters → use-cases → Telegram transport runtime`), выводит безопасный bootstrap-статус (без печати raw `DATABASE_URL`) и **не** поднимает polling/webhook автоматически.

Foundation интеграция с `python-telegram-bot` доступна отдельным явным runtime-entrypoint:

```bash
python -m smart_life_bot.bot.telegram_polling
```

Этот entrypoint запускает long polling только по явной команде.


Safe VPS/runtime preflight diagnostics are available via explicit entrypoint:

```bash
python -m smart_life_bot.runtime.preflight
```

Preflight validates runtime readiness (settings/timezone/SQLite/runtime composition), **does not** start Telegram polling, **does not** call real Telegram/Google APIs, and prints only safe status markers without secrets.


Storage foundation тесты можно запускать общим тестовым набором:

```bash
python -m pytest
```


Парсинг на текущем этапе остаётся MVP-уровня: используется детерминированный rule-based baseline без LLM/NLP SDK и без внешних сетевых вызовов.

Реализован foundation-адаптер записи событий Google Calendar для `service_account_shared_calendar_mode` (через service account + shared calendar). `oauth_user_mode` остаётся pending и в runtime пока использует fake/dev calendar adapter. После успешного confirm бот также показывает ссылку на созданное событие, если календарный провайдер вернул `html_link`. Это позволяет подготовить будущий VPS smoke-сценарий `Telegram message → preview → confirm → Google Calendar create event` без добавления OAuth callback/user-consent flow в текущем PR.
