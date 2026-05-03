# Implementation Roadmap / Sprint Milestones

> **Role:** Canonical source for adjustable implementation sequencing (sprints/milestones). Keep product behavior in [PRD](PRD_MVP.md), architecture in [Architecture](ARCHITECTURE.md), and test policy in [Testing](TESTING.md).

Эти этапы фиксируют **implementation milestones/sprints**, а не жесткие Scrum-коммитменты.

> Scope может корректироваться по мере продуктовых находок, результатов live smoke-проверок и появления новых рисков.

## Принципы roadmap

- Roadmap описывает приоритетную последовательность, а не «контракт без изменений».
- Каждый следующий этап стартует после базовой проверки предыдущего на реальном runtime (VPS smoke + CI).
- Фичи deep backlog (PWA/Mini App/offline-first/API/native wrapper) не смешиваются с ближайшим MVP-delivery.

---

## Sprint 0 — Stabilization & deploy baseline

**Goal**
- Подтвердить, что текущий `main` стабильно работает на VPS после последних merge.
- Проверить, что deploy действительно rebuild/recreate текущий контейнер.
- Пройти базовые smoke-сценарии календаря и кэшбека.

**Scope**
- Deploy текущего `main`.
- Smoke `/start`.
- Smoke footer menu `📅 Календарь` / `💳 Кэшбек`.
- Smoke cashback add/query.
- Smoke calendar direct text preview.
- Smoke conflict clarification.
- Обновление runbook, если фактическое runtime-поведение отличается от документации.

**Out of scope**
- Новые продуктовые фичи.
- Изменение auth-архитектуры.

---

## Sprint 1 — Cashback MVP usability

**Goal**
- Сделать cashback-поток удобным для ежедневного использования.

**Кандидаты в объём работ**
- Полировка structured add/query ответов.
- Улучшение сообщений об ошибках: invalid owner / invalid month / transition period.
- Добавление или доработка `📋 Активные категории` (если текущее поведение недостаточно).
- Решение по UX конца месяца: нужно ли кнопочное month selection вместо повторного текстового запроса с явным месяцем.

**Explicitly not now**
- XLSX export.
- LLM-based cashback parsing.
- Offline-first/PWA work.

---

## Sprint 2 — Cashback month and management flows

**Goal**
- Расширить управление и поддержку жизненного цикла cashback-записей.

**Кандидаты в объём работ**
- Списки категорий по выбранному месяцу. _(first slice delivered: Telegram inline month navigation for `📋 Активные категории`)_
- Soft-delete/deactivation slice delivered: удаление активной cashback-записи через Telegram только с явным confirm/cancel, без физического удаления строки.
- Owner-filtered slice delivered: `📋 Активные категории` поддерживает inline owner filter + reset `Все` c сохранением выбранного месяца.
- Списки/фильтрация по bank/category (если подтверждена продуктовая ценность).
- Edit записей.
- Transition-period explicit month buttons delivered: валидный 4-part cashback add в конце месяца показывает inline current/next month и завершается без повторного ввода.
- Сохранение transport-agnostic structured use-case результатов.

---

## Sprint 3 — Calendar missing date picker MVP

**Goal**
- Реализовать уже зафиксированный inline date picker для recovery при `missing_start_at`.

**Scope**
- Draft без `start_at` показывает `📅 Выбрать дату`.
- Inline month grid.
- Date selection callback.
- Запрос времени текстом `HH:MM`.
- Обновление draft `start_at`.
- Повторный confirmable preview.
- `✅ Создать событие` (внутренний callback `draft:confirm`) остаётся единственным calendar write-path.
- Stale callbacks завершаются fail-safe.

**Out of scope**
- Mini App.
- Полноценный inline time picker.
- Отдельный frontend.
- Recurring events.

---

## Sprint 4 — Cashback XLSX export

**Goal**
- Дать визуальный monthly-report по cashback.

**Scope**
- `📤 Экспорт XLSX` (implemented).
- Выбор месяца (implemented): picker + month navigation + `✅ Выгрузить этот месяц`.
- Форматированный `.xlsx` отчёт (implemented).
- Read-only `ExportCashbackCategoriesUseCase`.
- Форматирование (implemented): title, bold headers, frozen header, autofilter, readable widths, deterministic sorting `category -> owner -> bank`.
- Отправка файла через Telegram document.

---

## Sprint 5 — Smarter cashback search

**Goal**
- Улучшить matching категорий при сохранении предсказуемого поведения.

**Кандидаты в объём работ**
- Алиасы/синонимы (`продукты/еда → супермаркеты`, `лекарства/медицина → аптеки`, `бензин/топливо → АЗС`) — first deterministic slice implemented.
- Fuzzy matching в детерминированных границах.
- Sprint 5 slice 2 delivered: controlled deterministic search variants + separator normalization (query-only, no broad fuzzy).
- LLM fallback только если deterministic matching реально недостаточен.
- При LLM-подходе передавать минимально необходимый набор опций, а не полные семейные/банковские данные без необходимости.

---

## Sprint 6 — OAuth calendar mode (discovery → incremental implementation)

**Goal**
- Подготовить и безопасно внедрить `🔐 Личный Google Calendar` без регресса текущего `service_account_shared_calendar_mode`.
- Сохранить единый confirm-gated calendar flow: запись в Google Calendar только после `✅ Создать событие` (callback `draft:confirm`).

**Current status (as of this roadmap update)**
- Реально работает `service_account_shared_calendar_mode` (calendar writes after explicit confirm).
- Slice 6.1 delivered foundation for `oauth_user_mode`: persisted OAuth connection-state model + Telegram personal calendar UX stubs (`Подключить` / `Отключить` / `Статус`) + strict adapter callback routing for `oauth:connect` / `oauth:disconnect` / `oauth:status`.
- `oauth_user_mode` runtime write-path remains pending: no callback endpoint runtime, no Google code→token exchange, no personal-calendar writes yet.

### Slice 6.0 — Discovery/spec freeze (docs-only)

**Scope**
- Зафиксировать target UX `🔐 Личный Google Calendar`: connect/disconnect/status/missing-auth guidance.
- Зафиксировать архитектурные границы OAuth callback/auth state/token storage.
- Зафиксировать deploy/domain/env prerequisites (HTTPS + stable redirect URI).
- Зафиксировать будущую тест-стратегию и open decisions.

**Out of scope**
- OAuth callback server.
- Google OAuth token exchange.
- Runtime behavior changes.

### Slice 6.1 — OAuth state model + UX stubs (no token exchange)

**Status:** Implemented (foundation only).

**Scope**
- Добавить application/storage model для user OAuth connection state (`not_connected`/`pending`/`connected`/`error`) и безопасных state tokens.
- Добавить transport-level UX команды/кнопки для `Подключить` / `Отключить` / `Статус` с текстами-заглушками.
- Missing-auth response для calendar confirms в personal mode: pending next slice.

**Guardrails**
- Без реального обмена code→token.
- Без callback endpoint runtime.
- Без изменений confirm invariant.

### Slice 6.2 — Callback adapter boundary skeleton

**Status:** Implemented (application/storage boundary only, no callback server).

**Scope**
- Ввести отдельную adapter boundary для OAuth callback handling (transport-independent контракт).
- Определить input/output контракт callback handler (state validation, error mapping, success mapping).
- Подготовить integration points для будущего web adapter (FastAPI/другой), без включения в default polling runtime.

**Guardrails**
- Callback HTTP server не включается в рабочий runtime.
- Google token exchange остается mock/stub.
- Raw OAuth code/token material не сохраняется; state validation опирается на hashed state token lookup.

### Slice 6.3 — Google OAuth exchange + token persistence behind interface

**Scope**
- Реализовать provider adapter для code exchange/refresh behind auth interfaces.
- Сохранение token material в persistence layer по согласованной policy (без утечек в логи).
- Error mapping на `missing_auth` / `provider_auth_failure`.

**Guardrails**
- Сервис-аккаунт путь не меняется и остается доступным fallback.
- Confirm-gated flow остается неизменным.

### Slice 6.4 — Personal calendar writes behind existing confirm flow

**Scope**
- Подключить user-authenticated Google Calendar client resolution для `oauth_user_mode` в confirm-use-case.
- Сохранить общий application flow для обоих auth modes; различие только в credential/client resolution.
- Добавить/обновить smoke и regression coverage для personal-mode write path.

**Guardrails**
- До `✅ Создать событие` никаких calendar writes.
- Existing shared-calendar mode не деградирует.

### Slice 6.5 — Reminder controls capability in OAuth mode

**Scope**
- Включить user-visible reminder controls только для реализованного/проверенного OAuth write path.
- Реализовать multi-select popup presets UX (`10 минут + 1 час` и т.п.) в пределах confirm flow.

**Guardrails**
- Service-account mode продолжает скрывать/не обещать custom reminders.
- Email reminders остаются out of scope.

### Slice 6.6 — Deploy hardening + smoke/runbook updates

**Scope**
- Подготовить production-ready deployment contour для OAuth prerequisites: HTTPS endpoint, stable domain, redirect URI ops.
- Обновить runbook/checklists для connect/disconnect/callback/refresh-failure smoke сценариев.
- Обновить incident/troubleshooting notes для auth failures.

**Guardrails**
- Не смешивать с webhook migration, если это не обязательно для выбранного callback hosting.

## Sprint 7+ — App/API/PWA/offline-first discovery

**Goal**
- Сначала discovery/design, затем потенциальная реализация.

**Кандидаты в объём работ**
- FastAPI adapter концепт.
- API contracts/DTO.
- PWA/Mini App UX prototype.
- IndexedDB/offline cache model.
- Public UUID/public_id migration plan.
- Sync/conflict strategy.
- APK/native wrapper — deep backlog.

## Future candidate — Cashback screenshot parser via Vision LLM

**Status**
- Backlog candidate only (**not implemented**).
- Не входит в текущий MVP и не входит в near-term Sprint 6 OAuth scope.
- Кандидат к старту только после стабилизации text-first Cashback MVP на реальном usage (VPS smoke + production-like usage без частых regressions).

**Product intent (future)**
- Пользователь отправляет screenshot из банковского приложения + короткий caption (например, `Альфа Вова`).
- Бот пытается извлечь кандидаты категорий/процентов кэшбека и формирует только draft preview.
- Сохранение в SQLite допускается только после явного подтверждения пользователя (`Сохранить` / `Отменить`).

**Suggested decomposition (future, phased discovery)**
- Phase A — discovery/spec only (UX, privacy, risk register, acceptance criteria).
- Phase B — image intake UX draft (Telegram-side flow) без внешнего Vision вызова.
- Phase C — Vision adapter за интерфейсом application/provider boundary, c mocked behavior в тестах.
- Phase D — структурный extraction contract (JSON-only output contract).
- Phase E — Python sanity checks + stop-word filtering до preview.
- Phase F — confirm-gated save flow (draft preview → explicit confirm → save).
- Phase G — production hardening: privacy/retention policy, cost/latency limits, observability без raw screenshots в логах.

**Guardrails / non-goals for this candidate**
- No implementation in current scope: без image handlers, OCR, Vision/LLM API calls, dependency changes.
- Screenshot input трактуется как untrusted input.
- Извлекаются только candidate cashback category/percent пары; нерелевантные финансовые блоки (кредиты/вклады/ставки/страховки/реклама) игнорируются.
- Calendar/Google Calendar flows не затрагиваются.
- Auto-import без explicit user confirmation запрещён.

---

## Re-planning cadence

- Корректировка milestone scope допускается после:
  - результатов Sprint 0 smoke;
  - выявленных регрессий в CI;
  - изменения продуктовых приоритетов.
- Корректировки должны фиксироваться в документации (roadmap/testing/runbook) вместе с PR.
