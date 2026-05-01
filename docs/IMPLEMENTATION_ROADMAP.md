# Implementation Roadmap / Sprint Milestones

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

**Scope candidates**
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

**Scope candidates**
- Списки категорий по выбранному месяцу.
- Списки/фильтрация по owner/bank/category (если подтверждена продуктовая ценность).
- Soft-delete / edit записей.
- Опциональные explicit month buttons в transition period.
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
- `Confirm` остаётся единственным calendar write-path.
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
- `📤 Выгрузить таблицу`.
- Выбор месяца.
- Форматированный `.xlsx` отчёт.
- Read-only `ExportCashbackCategoriesUseCase`.
- Форматирование: title, bold headers, frozen header, autofilter, readable widths, сортировка/группировка категорий.
- Отправка файла через Telegram document.

---

## Sprint 5 — Smarter cashback search

**Goal**
- Улучшить matching категорий при сохранении предсказуемого поведения.

**Scope candidates**
- Алиасы/синонимы (`продукты → супермаркеты`, `лекарства → аптеки`, `бензин → АЗС`).
- Fuzzy matching в детерминированных границах.
- LLM fallback только если deterministic matching реально недостаточен.
- При LLM-подходе передавать минимально необходимый набор опций, а не полные семейные/банковские данные без необходимости.

---

## Sprint 6 — OAuth calendar mode

**Goal**
- Начать реализацию `🔐 Личный Google Calendar`.

**Scope candidates**
- OAuth flow design.
- Token storage policy.
- Connect/disconnect account UX.
- User-authenticated calendar write-path.
- Capability-based reminder controls.
- Future multi-select popup reminder UI.

---

## Sprint 7+ — App/API/PWA/offline-first discovery

**Goal**
- Сначала discovery/design, затем потенциальная реализация.

**Scope candidates**
- FastAPI adapter концепт.
- API contracts/DTO.
- PWA/Mini App UX prototype.
- IndexedDB/offline cache model.
- Public UUID/public_id migration plan.
- Sync/conflict strategy.
- APK/native wrapper — deep backlog.

---

## Re-planning cadence

- Корректировка milestone scope допускается после:
  - результатов Sprint 0 smoke;
  - выявленных регрессий в CI;
  - изменения продуктовых приоритетов.
- Корректировки должны фиксироваться в документации (roadmap/testing/runbook) вместе с PR.
