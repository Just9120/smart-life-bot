# Testing & Regression Strategy

> **Role:** Canonical source for automated testing and regression strategy. Manual deploy smoke commands/checklists belong in [VPS smoke runbook](VPS_SMOKE_RUNBOOK.md).

Документ описывает **практическую стратегию automated/regression тестирования** для Smart Life Ops Bot.

Пошаговые ручные post-deploy проверки вынесены в [VPS smoke runbook](VPS_SMOKE_RUNBOOK.md), чтобы не дублировать операционные чеклисты.

## 1) Ключевая идея

Regression testing — это не отдельный «магический инструмент», а набор автоматизированных тестов, которые стабильно запускаются в CI на каждом PR.

Текущий baseline:

- **GitHub Actions → `pytest` → тесты на PR**.

---

## 2) Уровни тестирования

## 2.1 Unit tests

Проверяют изолированные правила и преобразования.

Примеры:
- cashback normalization;
- structured parsing;
- explicit month parsing;
- owner validation;
- transition-period logic;
- calendar preview formatting;
- future: callback parsing/date picker helpers.

## 2.2 Application / use-case tests

Проверяют бизнес-сценарии уровня use-case (без привязки к Telegram SDK текстам там, где это не нужно).

Примеры:
- `AddCashbackCategoryUseCase`;
- `QueryCashbackCategoryUseCase`;
- `ListActiveCashbackCategoriesUseCase`;
- future: `ExportCashbackCategoriesUseCase`;
- calendar confirm/cancel/edit use-cases.

Важное правило:
- asserts должны по возможности проверять **structured result fields**, а не только финальный Telegram-текст.

## 2.3 Storage/integration tests (SQLite)

Проверяют реальное поведение репозиториев и SQL-контрактов.

Примеры:
- schema creation;
- insert/upsert;
- duplicate update behavior;
- query by `target_month`;
- old month records не попадают в current month query;
- soft-delete behavior;
- future: export query behavior.

## 2.4 Telegram transport tests

Проверяют transport-routing и целостность UX-контуров.

Примеры:
- `/start` показывает footer menu;
- `/start` просит выбрать активный режим (`📅 Календарь` / `💳 Кэшбек`);
- `📅 Календарь` navigation;
- `💳 Кэшбек` menu/help;
- `💳 Кэшбек` menu содержит явные actions (`📋 Активные категории`, `➕ Добавить категорию`, `🔎 Найти категорию`);
- cashback structured add;
- cashback explicit add-flow (`➕ Добавить категорию` → format hint → pending state) + cancel/clear;
- cashback transition callback safety (tokenized month selection, stale callback rejection);
- cashback edit-percent flow (кнопка из active list, pending state, invalid input retry, cancel);
- cashback query;
- conflict clarification;
- direct calendar text возвращает preview;
- reminder controls скрыты в service-account mode;
- duration button flow работает.
- missing-date recovery flow: `📅 Выбрать дату` → inline month grid → ввод `HH:MM` → confirmable preview.

## 2.5 Regression flow tests

Рекомендуется поддерживать выделенный небольшой regression-набор (например, `tests/test_regression_flows.py`) со сценариями, которые чаще всего ломаются при эволюции продукта.

Фокус regression-сценариев:
- direct calendar text создаёт preview;
- calendar write происходит только после явного Confirm;
- missing `start_at` не допускает Confirm;
- missing-date recovery callbacks/HH:MM validation не создают событие до Confirm (calendar preview Confirm invariant);
- `/start` footer menu содержит `📅 Календарь` и `💳 Кэшбек`;
- без активного режима неоднозначный plain-text не запускает calendar/cashback flow и возвращает выбор режима;
- `📅 Календарь` устанавливает active mode `calendar` и показывает `Текущий режим: 📅 Календарь`;
- `💳 Кэшбек` устанавливает active mode `cashback` и показывает `Текущий режим: 💳 Кэшбек`;
- strict mode routing: в `calendar` mode free text маршрутизируется только в calendar flow (включая missing-date recovery), а в `cashback` mode не попадает в calendar parser path;
- в `cashback` mode category query возвращает `query_found/query_not_found` и не создаёт calendar draft;
- explicit cashback actions: меню содержит `📋 Активные категории` / `➕ Добавить категорию` / `🔎 Найти категорию`;
- pending add flow: `➕ Добавить категорию` открывает format hint и pending-state сценарий с безопасным cancel/clear;
- adapter callback coverage: transport обрабатывает `cashback:add:start` и `cashback:search:hint` в реальном callback-routing;
- в `cashback` mode plain category text по умолчанию уходит в query/search path (без неявного add-flow);
- structured cashback add остаётся глобально допустимым (command-like) без активного режима;
- calendar menu navigation не создаёт событий;
- service-account mode скрывает custom reminder controls;
- cashback add/query не вызывает calendar flow;
- cashback active-list использует видимую нумерацию `1.`, `2.` (без legacy `#1`) и edit/delete actions соответствуют этим номерам;
- cashback edit-percent flow не вызывает calendar flow и не уводит ввод в calendar parser path;
- cashback conflict clarification не мутирует calendar draft/cashback state;
- structured cashback use-case results остаются transport-agnostic.

---

## 3) CI strategy

## 3.1 Current

- GitHub Actions запускает `pytest` на PR.

## 3.2 Near-term principles

- тесты должны оставаться быстрыми и детерминированными;
- в CI используются fake/stub сервисы для Telegram/Google, где применимо;
- in-memory SQLite — baseline для большинства тестов;
- не использовать реальный Telegram Bot API в CI;
- не выполнять реальные Google Calendar writes в CI;
- Playwright/PWA/Android tests пока не вводятся.

## 3.3 Future CI backlog (не current scope)

- lint/type checks (если будут введены);
- API contract tests после появления FastAPI adapter;
- frontend tests после появления PWA/Mini App;
- migration tests, если появится migration tooling.

---

## 4) Manual VPS smoke после deploy

Автотесты не заменяют ручной smoke после реального deploy.

После deploy на VPS должны проверяться минимум:
- контейнер пересобран и запущен из актуального кода;
- `/start` показывает footer menu;
- `📅 Календарь` mode selection работает;
- `💳 Кэшбек` menu/help работает;
- add cashback category с явным месяцем работает;
- cashback query работает;
- conflict text возвращает clarification;
- direct calendar text даёт preview;
- missing-date recovery (`📅 Выбрать дату` + `HH:MM`) возвращает confirmable preview только после валидного времени;
- Confirm создаёт calendar event только при явном нажатии.

Детальный операционный чеклист: `docs/VPS_SMOKE_RUNBOOK.md`.

---

## 5) Что **не** делаем сейчас

За пределами текущего testing scope:
- real Telegram E2E tests в CI;
- real Google Calendar integration tests на каждый PR;
- browser/UI tests;
- Android/PWA tests;
- тяжёлое test environment до появления app/API слоя.

---

## 6) Scope guardrails для этого этапа

- Текущая стратегия документирует и стабилизирует процесс.
- В рамках docs-этапа не требуется менять runtime-поведение.
- В рамках docs-этапа не требуется добавлять новые тесты/CI workflow.
