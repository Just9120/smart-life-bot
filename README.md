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
- `docs/DEPLOYMENT.md` — базовые принципы деплоя, ограничения окружения и initial manual CD workflow через GitHub Actions (`workflow_dispatch`).
- `docs/DECISIONS.md` — журнал архитектурных и технических решений в формате ADR-like.
- `docs/PHASE1_TECHNICAL_SPEC.md` — рабочая техническая спецификация Phase 1 для следующих PR.
- `docs/CONFIGURATION.md` — модель конфигурации и переменных окружения.
- `docs/VPS_SMOKE_RUNBOOK.md` — пошаговый ручной smoke runbook для первого запуска на VPS.
- `docs/IMPLEMENTATION_ROADMAP.md` — адаптивный sprint-style roadmap по текущим и будущим milestone этапам.
- `docs/TESTING.md` — стратегия automated testing/regression в CI и manual VPS smoke после deploy.
- `.env.example` — безопасный шаблон env-переменных (только placeholders, без секретов).
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

Для первого ручного VPS smoke-теста используйте `docs/VPS_SMOKE_RUNBOOK.md`; перед `python -m smart_life_bot.bot.telegram_polling` всегда сначала запускайте `python -m smart_life_bot.runtime.preflight`.


Storage foundation тесты можно запускать общим тестовым набором:

```bash
python -m pytest
```


Парсинг на текущем этапе остаётся MVP-уровня: используется детерминированный Python/rule-based parser baseline (единственная полностью активная parser-реализация) без LLM/NLP SDK и без внешних сетевых вызовов. Rule-based parser поддерживает распространённые компактные RU форматы даты/времени (включая варианты с запятой, `HH:MM` и `HH MM`) и даты с русскими названиями/сокращениями месяцев.

Parser mode хранится как user-level preference в `user_preferences` и настраивается через Telegram `/settings` (а не через `.env`). Сохранённый режим участвует в реальном parsing path через `ParserModeRouter` (за `MessageParser` abstraction):
- `python` → Python/rule-based parser (основной дешёвый и детерминированный путь);
- `auto` → Python first, затем Claude fallback только при ambiguous/low-confidence, если LLM настроен; иначе безопасный Python fallback;
- `llm` → Claude parser только когда LLM настроен; иначе defensive Python fallback.

Telegram preview дополнительно показывает компактную parser diagnostics секцию (`mode/route/source/confidence`, и `issues` когда есть), чтобы пользователь видел, какой parser path был использован.
Если draft не готов к безопасному подтверждению (например, отсутствует `start_at`, некорректный `timezone`, некорректный диапазон времени или смешаны timezone-aware/timezone-naive datetime), в preview скрывается кнопка Confirm (остаются Edit/Cancel) и показывается явная подсказка как исправить draft через `/edit`.

LLM parser foundation реализован через Anthropic Claude (optional runtime capability). Модель остаётся env-configurable через `LLM_MODEL` (без hardcode в runtime routing):
- default / cost-efficient: `claude-haiku-4-5-20251001`;
- higher-quality option: `claude-sonnet-4-6`.


## Docker runtime (VPS smoke foundation)

Минимальный Docker runtime для VPS smoke (выполняйте команды из директории этого репозитория, например `/opt/smart-life-bot`, чтобы не затронуть другие Docker-проекты на VPS):

```bash
host_commit="$(git rev-parse --short HEAD)"
docker compose build --no-cache --build-arg APP_GIT_SHA="$host_commit" smart-life-bot
docker compose run --rm smart-life-bot python -m smart_life_bot.runtime.preflight
docker compose up -d --force-recreate --no-deps smart-life-bot
docker compose logs -f smart-life-bot
```

Остановка runtime:

```bash
docker compose stop smart-life-bot
# или docker compose down (только из директории Smart Life Ops Bot compose-проекта)
```

Подробный runbook: `docs/VPS_SMOKE_RUNBOOK.md`.

## Backlog / Future scope

Telegram voice input добавлен только в backlog и не входит в текущую реализацию.

Целевой будущий поток:

`Telegram voice message → STT transcription → existing text parser flow → preview → confirm/edit/cancel → Google Calendar write`

Ключевые ограничения будущей реализации:
- STT и parsing остаются разделёнными этапами:
  - STT: audio → text;
  - parser: text → `EventDraft`.
- Предпочтительный STT-кандидат для будущего этапа: ElevenLabs Scribe (в проектном контексте уже есть ElevenLabs API key, но в репозитории не хранятся реальные ключи).
- Voice input не должен обходить обязательный preview/confirm flow.
- Cost/safety baseline для будущего этапа:
  - короткие Telegram voice сообщения ожидаемо low-cost относительно длинных лекций;
  - позже должны быть введены ограничения max duration / file size;
  - длинные лекции не должны обрабатываться через bot flow;
  - API keys/credentials не логируются.

Реализован foundation-адаптер записи событий Google Calendar для `service_account_shared_calendar_mode` (через service account + shared calendar). `oauth_user_mode` остаётся pending и в runtime пока использует fake/dev calendar adapter. После успешного confirm бот также показывает ссылку на созданное событие, если календарный провайдер вернул `html_link`. Это позволяет подготовить будущий VPS smoke-сценарий `Telegram message → preview → confirm → Google Calendar create event` без добавления OAuth callback/user-consent flow в текущем PR.
