# Smart Life Ops Bot

Smart Life Ops Bot — это Telegram-ассистент, сфокусированный на быстром и надежном добавлении событий в Google Calendar с обязательным подтверждением перед записью каждого события.

**Текущий статус:** runtime foundation phase 1 (включая SQLite storage foundation, minimal Telegram transport foundation для `/start`, text, confirm/edit/cancel mapping, explicit runtime composition foundation, foundation-адаптер `python-telegram-bot` для маппинга real Telegram updates в существующий runtime, детерминированный rule-based parser baseline без LLM и foundation-адаптер реальной записи в Google Calendar для `service_account_shared_calendar_mode`).

## Назначение продукта (MVP)

- Канал ввода: Telegram-бот.
- Основной поток: message → parsing → preview → confirm / edit / cancel → create Google Calendar event.
- Приоритеты: надежность, прозрачность, управляемость, быстрый выход к полезному результату.

## Documentation map

- [`docs/PRD_MVP.md`](docs/PRD_MVP.md) — canonical source for user-facing behavior and MVP UX.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — canonical source for system layers, boundaries, runtime architecture, and transport strategy.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — canonical ADR-style log of accepted/pending decisions and trade-offs.
- [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md) — canonical source for adjustable sprint/milestone implementation plan.
- [`docs/TESTING.md`](docs/TESTING.md) — canonical source for automated testing and regression strategy.
- [`docs/VPS_SMOKE_RUNBOOK.md`](docs/VPS_SMOKE_RUNBOOK.md) — canonical source for manual post-deploy VPS smoke checks.
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — canonical source for env/configuration model.
- [`docs/PHASE1_TECHNICAL_SPEC.md`](docs/PHASE1_TECHNICAL_SPEC.md) — Phase 1 implementation spec details; if overlap appears, keep product behavior in PRD and architecture boundaries in Architecture.

## Documentation maintenance rule

- Put the canonical explanation in the correct source document.
- In other documents, keep only a short summary and a link to the canonical source instead of full repeated detail.
- When changing product behavior, update `docs/PRD_MVP.md` and also update testing/runbook docs if user behavior or smoke checks are affected.
- When changing architecture, update `docs/ARCHITECTURE.md` and `docs/DECISIONS.md` when a durable decision is made.
- When changing deployment/operations, update runbook/config docs.
- When changing test expectations, update `docs/TESTING.md` and relevant automated tests.

## Структура репозитория

- [`docs/PRD_MVP.md`](docs/PRD_MVP.md) — краткие продуктовые требования MVP.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — детальная архитектура Phase 1 (слои, зависимости, flow, границы).
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — базовые принципы деплоя, ограничения окружения и deploy workflow через GitHub Actions (`push` в `main` + `workflow_dispatch`).
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — журнал архитектурных и технических решений в формате ADR-like.
- [`docs/PHASE1_TECHNICAL_SPEC.md`](docs/PHASE1_TECHNICAL_SPEC.md) — рабочая техническая спецификация Phase 1 для следующих PR.
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — модель конфигурации и переменных окружения.
- [`docs/VPS_SMOKE_RUNBOOK.md`](docs/VPS_SMOKE_RUNBOOK.md) — пошаговый ручной smoke runbook для первого запуска на VPS.
- [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md) — адаптивный sprint-style roadmap по текущим и будущим milestone этапам.
- [`docs/TESTING.md`](docs/TESTING.md) — стратегия automated testing/regression в CI (manual smoke steps описаны в [`docs/VPS_SMOKE_RUNBOOK.md`](docs/VPS_SMOKE_RUNBOOK.md)).
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
Если draft не готов к безопасному подтверждению (например, отсутствует `start_at`, некорректный `timezone`, некорректный диапазон времени или смешаны timezone-aware/timezone-naive datetime), в preview скрывается кнопка `✅ Создать событие` (остаются Edit/Cancel) и показывается явная подсказка, как исправить draft через `/edit`.

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


## Cashback XLSX export (Sprint 4 slice)

В разделе `💳 Кэшбек` доступна кнопка `📤 Экспорт XLSX` для read-only выгрузки активных категорий за текущий месяц из persisted SQLite данных. Если данных нет, бот отправляет дружелюбное сообщение без пустого файла.
