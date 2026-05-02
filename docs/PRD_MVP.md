# PRD — Smart Life Ops Bot MVP

> **Role:** Canonical source for user-facing product behavior and MVP UX. Architecture/deploy internals are summarized here and detailed in [Architecture](ARCHITECTURE.md) and runbook/config docs.

## 1. Продукт

- **Название проекта:** Smart Life Ops Bot.
- **Основной канал ввода:** Telegram-бот.
- **Целевой результат MVP:** надежное создание событий Google Calendar из естественных сообщений пользователя с обязательным подтверждением перед записью.

## 2. Базовый пользовательский сценарий

`message → parsing → preview → explicit edit controls → confirm / cancel → create event`

Событие в Google Calendar создается только после явного нажатия **✅ Создать событие**.

## 3. Текущий UX MVP (Telegram draft flow + navigation direction)

1. Пользователь отправляет текст.
2. Парсер извлекает базовые сущности (например, title/start time), формирует draft и preview.
3. В preview доступны явные inline-действия редактирования.
4. Пользователь подтверждает (`✅ Создать событие`) или отменяет (Cancel).
5. Только после нажатия `✅ Создать событие` выполняется запись в Google Calendar.

Важно:
- обычный free-text не должен тихо менять duration/reminders;
- управление длительностью выполняется через `⏱ Длительность`;
- в текущем runtime (`⚡ Быстрый режим`, technical: `service_account_shared_calendar_mode`) кастомные reminders не считаются надежно поддерживаемой user-visible фичей;
- reminders должны быть capability-gated по calendar mode и включаться как user-visible feature только в будущем `🔐 Личный Google Calendar` (technical: `oauth_user_mode`) после реализации и проверки.

### 3.1 Telegram navigation model (target UX direction)

Telegram UX фиксируется как двухуровневая навигация:

1. **Native Telegram command menu** (кнопка `Menu`) для глобальных команд: `/start`, `/settings`, future `/help`.
2. **Footer feature menu** (persistent reply keyboard после `/start`) для продуктовых разделов, начиная с `📅 Календарь`.

Inline preview buttons остаются только для действий с текущим draft (`✅ Создать событие` / `⏱ Длительность` / Edit / Cancel + future reminder controls только при поддерживаемом режиме календаря).

Текущее поведение mode routing в Telegram:
- `/start` явно просит выбрать режим: `Выбери режим: 📅 Календарь или 💳 Кэшбек.`
- При выборе `📅 Календарь` бот фиксирует активный режим `calendar` и показывает `Текущий режим: 📅 Календарь`.
- При выборе `💳 Кэшбек` бот фиксирует активный режим `cashback` и показывает `Текущий режим: 💳 Кэшбек`.
- Если активный режим не выбран, неоднозначный plain-text (например, `Аптеки`, `Созвон`, `Купить хлеб`) не маршрутизируется автоматически и бот снова просит выбрать режим.
- Исключение: явный структурный cashback add (например, `Альфа, Владимир, Аптеки, 5%` или `Альфа, Владимир, 2026-05, Супермаркеты, 5%`) остаётся глобально допустимым command-like вводом даже без активного режима.



### 3.2 Calendar menu split (planned)

В разделе `📅 Календарь` планируется выбор режима:

- `⚡ Быстрый режим` — текущий рабочий путь в shared calendar через service account.
- `🔐 Личный Google Calendar` — будущий OAuth 2.0 user-authenticated путь.
- Для будущего OAuth reminder UX используется multi-select popup presets (один или несколько одновременно, например `10 минут + 1 час`) через checkbox-style pattern с действием `Применить`; email reminders не используются.

### 3.3 Missing-date recovery (MVP near-term)

Если draft сформирован без даты/времени (`start_at: —`), в preview показывается явный recovery path:

- preview остаётся non-confirmable;
- доступны кнопки `📅 Выбрать дату`, `✏️ Edit`, `❌ Cancel`;
- по `📅 Выбрать дату` бот показывает inline month grid;
- после выбора даты бот запрашивает время текстом в формате `HH:MM`;
- после валидного времени draft получает `start_at` и preview снова показывается уже в confirmable состоянии (`✅ Создать событие` / `⏱ Длительность` / `Edit` / `Cancel`).

Ограничения этого MVP-шага:
- inline picker выбирает только дату;
- full inline time-picker не входит в first pass;
- picker не создаёт событие в календаре и не заменяет `Confirm`;
- Telegram Web App / Mini App календарный UI — deep backlog, не near-term MVP.

## 4. Scope MVP

- Telegram message → draft preview → confirm/cancel flow.
- Confirm-gated Google Calendar create.
- Явное редактирование duration через inline UI.
- Базовая продуктовая навигационная модель: command menu + footer feature menu (`📅 Календарь` как первый раздел).
- Capability-gating reminder controls по calendar mode (в current service-account path reminders не заявляются как поддержанная user-visible фича).
- Базовое логирование ключевых действий и ошибок.

## 5. Out of scope MVP

- Автономное создание событий без подтверждения.
- Свободный текст как канал управления duration/reminders (`длительность ...`, `уведомить за ...`).
- OAuth runtime flow (`oauth_user_mode`) — pending.

## 6. Google Calendar auth/runtime status

- Текущий рабочий runtime path: `service_account_shared_calendar_mode`.
- `oauth_user_mode` остается целевым, но pending для runtime.

## 7. Roadmap phases

- **Phase 1 — Reliable Event Capture MVP**
- **Phase 2 — Reliability, Editing, and Trust**
- **Phase 3 — Task Layer**
- **Phase 4 — Smart Routing and Context Layer**

## 8. Cashback MVP module (`💳 Кэшбек`)

- `💳 Кэшбек` — отдельный feature-модуль, изолированный от calendar use-cases.
- Владельцы карт (MVP whitelist): `Виктор`, `Владимир`, `Елена`.
- Форматы структурного добавления:
  - С запятыми: `банк, владелец, категория, процент`.
  - Короткий fallback без запятых: `банк владелец категория процент%`.
  - В переходный период конца месяца для валидного ввода без явного месяца бот показывает inline-кнопки выбора месяца (текущий/следующий) и завершает добавление без повторного ввода всей строки.
  - Явный формат с месяцем продолжает работать в обоих стилях: `банк, владелец, месяц, категория, процент` и `банк владелец месяц категория процент%`.
  - Поддерживаемые month tokens в MVP: русские названия месяцев и `YYYY-MM`.
  - Формат `MM.YYYY` (например, `05.2026`) в MVP не поддерживается.
- Банки в MVP не ограничены whitelist'ом.
- Для предотвращения тривиальных дублей применяется минимальная детерминированная нормализация bank name перед upsert/storage: безопасный cleanup (trim + схлопывание повторных пробелов + нормализация пробелов вокруг дефиса) и каноникализация известных безопасных вариантов `Т-Банк` (`Т-банк`, `Т банк`, `ТБанк` и др.) в единое значение `Т-Банк`.
- Широкий fuzzy/alias matching банков остаётся future work и не входит в MVP.
- Поиск выполняется по текущему месяцу, хранение историчное по `target_month`.
- В режиме `💳 Кэшбек` бот показывает явные действия: `📋 Активные категории`, `➕ Добавить категорию`, `🔎 Найти категорию`.
- По умолчанию plain text в режиме `💳 Кэшбек` трактуется как category query/search (например, `Аптеки`, `Супермаркеты`, `АЗС`), а не как неявный add-flow.
- Добавление категории выполняется явно: либо структурным вводом (например, `Альфа, Владимир, май, Супермаркеты, 5%`), либо через `➕ Добавить категорию` с подсказкой формата и pending add-state до успешного ввода/отмены.
- Для ежедневного использования доступен быстрый просмотр `📋 Активные категории` из раздела `💳 Кэшбек`: по умолчанию текущий месяц + inline-навигация по соседним месяцам (выбор месяца через callback-кнопки).
- В `📋 Активные категории` доступен owner-filter по whitelist-владельцам (`Виктор`, `Владимир`, `Елена`) и сброс на `Все`; фильтр применяется к выбранному месяцу.
- Из `📋 Активные категории` доступна деактивация (soft-delete) конкретной записи через явное подтверждение в Telegram (`подтвердить / отмена`); без подтверждения запись не меняется.
- Из `📋 Активные категории` доступно точечное редактирование только процента у активной записи через отдельную action-кнопку; после успешного ввода нового процента бот обновляет запись и показывает обновлённый список за тот же месяц.
- Старые строки не удаляются физически; актуальность определяется фильтром `target_month` + `is_deleted=0`.
- Повторное добавление той же активной категории (тот же месяц + владелец + банк + категория) с тем же процентом считается no-op: бот отвечает «Такая категория уже есть».
- Повторное добавление той же активной категории с другим процентом обновляет существующую запись (upsert update).
- LLM fallback для cashback parsing и XLSX export — future work, вне текущего scope.
- Границы application/use-case для cashback должны оставаться transport-agnostic (JSON-friendly результаты), Telegram отвечает только за рендер текста.
- Migration в FastAPI/PWA/Telegram Mini App остаётся глубоким backlog, вне scope текущих PR.
- Future XLSX export рассматривается как визуальный monthly-report/backup feature (review/share), а не как основной checkout UX; оперативный ответ по категории должен оставаться мгновенно в Telegram-диалоге.

### 8.1 Cashback offline-first direction (future, non-MVP)

- Для checkout-сценариев фиксируется future-направление offline-first (возможны PWA / Telegram Mini App / web client): локальный кэш/БД на устройстве, офлайн lookup, очередь локальных изменений с последующей синхронизацией.
- Практический browser baseline для структурных данных: IndexedDB (или эквивалент), а не только `localStorage`; PWA app shell caching рассматривается как механизм офлайн-старта.
- Для будущего sync необходимо планировать стабильный UUID-идентификатор (`record_id`/`public_id`) у syncable cashback сущностей; внутренние integer PK могут сохраняться как internal DB detail.
- Offline-first не блокирует текущий Telegram MVP и не расширяет текущий implementation scope.

### 8.2 Full app evolution (future, non-MVP)

- Текущий этап остаётся Telegram-first: Telegram — единственный active runtime transport.
- Будущая эволюция: FastAPI adapter → PWA / Telegram Mini App frontend; APK/native wrapper — deep backlog.
- No-code конструкторы (Tilda/Webflow и аналоги) подходят для landing/marketing, но не для основного продуктового app-runtime с auth/state/sync/export/calendar flows.
