# Smart Life Ops Bot

## Что это

Smart Life Ops Bot — Telegram-first ассистент для бытовых операционных задач.
Текущий MVP покрывает два продуктовых направления:
- `📅 Календарь` (создание событий Google Calendar через preview + явное подтверждение);
- `💳 Кэшбек` (ведение и поиск категорий по месяцам).

## Текущий статус

- **Calendar MVP работает** через `service_account_shared_calendar_mode`.
- **Cashback MVP работает**: add/list/search/edit/delete активных категорий, owner-first multi-add, навигация по месяцам, read-only XLSX export.
- **OAuth Slice 6.1 — только foundation/stubs**: есть UX-каркас `🔐 Личный Google Calendar` и callback routing (`oauth:connect` / `oauth:disconnect` / `oauth:status`), но нет callback-сервера, code/token exchange и personal-calendar writes.

## Основные возможности

### Календарь
- Поток: Telegram text → parser → draft preview → `✅ Создать событие` → запись в Google Calendar.
- Internal confirm callback: `draft:confirm`.
- Recovery для missing date/time: `📅 Выбрать дату` → inline date grid → ввод `HH:MM` → обновлённый confirmable preview.
- Рабочий write path: `service_account_shared_calendar_mode`.
- Custom reminders capability-gated: в service-account режиме нельзя переобещать user-visible поведение кастомных напоминаний.

### Кэшбек
- Режим `💳 Кэшбек` с явными действиями add/list/search/edit/delete.
- Owner-first multi-add (до 5 категорий за сообщение).
- Просмотр и управление по выбранному месяцу.
- `📤 Экспорт XLSX` (read-only) с picker месяца.
- Детерминированные query/search-only aliases/variants:
  - `продукты` / `еда` → `Супермаркеты`
  - `лекарства` / `медицина` → `Аптеки`
  - `бензин` / `топливо` → `АЗС`
  - `супермаркет` / `магазины продуктов` → `Супермаркеты`
  - `аптека` → `Аптеки`
  - `заправка` / `заправки` / `а-з-с` → `АЗС`
- Ограничения: нет broad fuzzy matching, нет LLM fallback для cashback search; alias/variant matching применяется только в query/search path.

### Парсер и настройки
- Поддерживаются parser modes: `python`, `auto`, `llm` (через `/settings`).
- `python` — детерминированный baseline.
- `auto`/`llm` используют LLM только при настроенных ключах; иначе остаётся безопасный fallback.

### Runtime / хранение / деплой
- SQLite — persisted runtime storage.
- Docker/VPS runtime + GitHub Actions CI/CD baseline.
- Deploy в VPS: на `push` в `main` и вручную через `workflow_dispatch`.
- Runtime verification markers после деплоя:
  - `post_deploy_runtime_verification=ok`
  - `deploy_phase=runtime_verification_ok`

## Критичные инварианты

- Calendar write разрешён только после явного `✅ Создать событие` (`draft:confirm`).
- Режим `💳 Кэшбек` не должен «проваливаться» в Calendar parser path.
- Production SQLite — постоянное состояние: в CD/smoke запрещены reseed/truncate/delete/recreate production DB.
- Текущая schema-init политика — idempotent/non-destructive (`CREATE TABLE IF NOT EXISTS`); будущие schema changes требуют явного migration-плана + backup/restore-подхода.
- OAuth personal calendar stubs нельзя описывать как full OAuth implementation.

## Карта документации

README — только входная точка. Канонические детали — в профильных документах:

- [docs/PRD_MVP.md](docs/PRD_MVP.md) — продуктовый scope, UX и инварианты.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — слои, границы, runtime composition.
- [docs/DECISIONS.md](docs/DECISIONS.md) — ADR-журнал принятых/ожидающих решений.
- [docs/IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) — актуальный roadmap и статус срезов.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — CI/CD и deploy guardrails.
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — переменные окружения и конфигурация.
- [docs/TESTING.md](docs/TESTING.md) — стратегия тестирования и regression policy.
- [docs/VPS_SMOKE_RUNBOOK.md](docs/VPS_SMOKE_RUNBOOK.md) — пошаговый post-deploy smoke.
- [docs/PHASE1_TECHNICAL_SPEC.md](docs/PHASE1_TECHNICAL_SPEC.md) — технические детали модулей/контрактов.

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
set -a; source .env; set +a
python -m smart_life_bot.main
```

Для явного Telegram long-polling runtime:

```bash
python -m smart_life_bot.bot.telegram_polling
```

Preflight без запуска polling/webhook:

```bash
python -m smart_life_bot.runtime.preflight
```

## Docker / VPS smoke

Короткий контур для VPS: `build → preflight → up`.
Полный операционный сценарий и checklist: [docs/VPS_SMOKE_RUNBOOK.md](docs/VPS_SMOKE_RUNBOOK.md).

## Тесты

Базовый запуск:

```bash
pytest -q
```

Детали по уровням тестов, regression и smoke-политике — в [docs/TESTING.md](docs/TESTING.md).

## Что ещё не реализовано

- Полный OAuth runtime: callback server, Google code/token exchange, personal-calendar writes.
- Voice input (STT flow).
- Отдельный app-контур (PWA/Mini App/API/offline-first) как реализованный runtime.
- Broad fuzzy matching и LLM fallback для cashback search.
- Автоматизация schema migrations и backup/restore orchestration.
