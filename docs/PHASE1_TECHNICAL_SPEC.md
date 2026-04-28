# PHASE 1 Technical Spec — Smart Life Ops Bot

## 1. Назначение документа

Этот документ фиксирует рабочую техническую спецификацию Phase 1 для поэтапной реализации следующими PR.

Это design-only спецификация. Бизнес-логика и внешние интеграции здесь не реализуются.

## 2. Module boundaries

### 2.1 `smart_life_bot.bot`

**Назначение:** transport-адаптер Telegram.

**Входит внутрь:**
- приём входящих сообщений/команд;
- преобразование transport payload → application command;
- отправка ответов пользователю.

**Не входит:**
- parsing/validation бизнес-смысла;
- auth/provider logic;
- прямой доступ к calendar API.

**Runtime status (PR #11 foundation):**
- реализован минимальный Telegram transport router поверх application use-cases;
- поддержаны маршруты `/start`, plain text draft-preview, `confirm`, `cancel`, `edit` command (`/edit <field> <value>`);
- для очистки optional полей в transport используется детерминированная форма `/edit description --clear` и `/edit location --clear`;
- добавлен `python-telegram-bot` adapter foundation (`build_telegram_application`), который маппит `/start`, plain text (без command payload) и callback (`draft:confirm/edit/cancel`) в `TelegramBotRuntime`;
- добавлен `/settings` flow для parser mode preference foundation с callback `settings:parser:python|auto|llm`;
- `python` можно переключать как active mode (единственная полностью активная parser-реализация), `auto` сохраняется как planned mode с текущим Python fallback, `llm` пока не реализован и defensively fallback-ится в Python parsing path;
- preview сообщения показывают компактные parser diagnostics (`mode/route/source/confidence` + `issues` при наличии) из metadata draft для прозрачности parser path;
- кнопка Confirm не показывается для non-confirmable draft (missing `start_at`, invalid timezone, invalid time range), остаются Edit/Cancel + явные подсказки для исправления через `/edit ...`; backend validation остаётся source of truth;
- long polling вынесен в отдельный явный entrypoint (`python -m smart_life_bot.bot.telegram_polling`) и не запускается из default bootstrap `main.py`.

**Разрешённые зависимости:**
- `smart_life_bot.application`
- `smart_life_bot.config`
- `smart_life_bot.observability`

### 2.2 `smart_life_bot.application`

**Назначение:** orchestration use cases.

**Входит внутрь:**
- flow message → preview → confirm/edit/cancel → save;
- coordination parsing, domain, storage, calendar, auth;
- управление переходами FSM на уровне сценария.

**Не входит:**
- детали transport SDK;
- SQL/ORM детали;
- конкретный Google SDK код.

**Разрешённые зависимости:**
- `smart_life_bot.domain`
- `smart_life_bot.parsing`
- `smart_life_bot.auth` (через контракты)
- `smart_life_bot.calendar` (через контракты)
- `smart_life_bot.storage` (через контракты)
- `smart_life_bot.observability`
- `smart_life_bot.config`

### 2.3 `smart_life_bot.domain`

**Назначение:** доменные модели и инварианты.

**Входит внутрь:**
- event draft/value objects;
- доменная валидация;
- transition-правила уровня сущностей.

**Не входит:**
- Telegram/Google API;
- persistence model и SQL.

**Разрешённые зависимости:**
- только стандартная библиотека и общие utility-модели без инфраструктуры.

### 2.4 `smart_life_bot.parsing`

**Назначение:** преобразование raw текста в структурированный draft.

**Входит внутрь:**
- normalization;
- extraction;
- confidence/ambiguity scoring;
- формирование preview payload.

**Runtime status (PR #12 parser baseline):**
- реализован детерминированный rule-based parser baseline;
- поддержаны шаблоны `YYYY-MM-DD HH:MM`, `DD.MM.YYYY HH:MM`, `сегодня/завтра/послезавтра в HH:MM`, `в HH:MM`;
- default duration = 60 минут, поддержаны `на N минут` и `на N час/часа/часов`;
- при отсутствии start time парсер возвращает ambiguous draft (`start_at=None`, `end_at=None`, issue `missing_start_at`);
- runtime composition использует rule-based parser вместо fixed fake parser output;
- parser mode preference участвует в parsing path через `ParserModeRouter` (за `MessageParser`): `python` → Python parser, `auto` → Python fallback, `llm` → defensive Python fallback (`llm not implemented`);
- routing metadata (`parser_mode`, `parser_router`, optional `llm_fallback_available=false`) добавляется поверх metadata базового Python parser;
- реальный LLM parser и внешние LLM provider calls остаются pending; целевой first provider — Claude (model env-configurable, likely start from Haiku; Sonnet as future higher-quality option).

**Не входит:**
- отправка сообщений пользователю;
- запись в календарь.

**Разрешённые зависимости:**
- `smart_life_bot.domain`
- `smart_life_bot.config`
- `smart_life_bot.observability`

### 2.5 `smart_life_bot.calendar`

**Назначение:** календарный provider abstraction.

**Входит внутрь:**
- интерфейс calendar service;
- маппинг domain event → provider request;
- маппинг provider errors → internal error model.

**Не входит:**
- orchestration бизнес-потока;
- хранение credentials.

**Разрешённые зависимости:**
- `smart_life_bot.domain`
- `smart_life_bot.auth` (контракт credentials)
- `smart_life_bot.observability`

### 2.6 `smart_life_bot.auth`

**Назначение:** единая auth abstraction для разных `auth_mode`.

**Входит внутрь:**
- выбор auth strategy по config;
- выдача auth context/credentials handle;
- классификация ошибок auth.

**Не входит:**
- business-flow logic;
- Telegram interactions.

**Разрешённые зависимости:**
- `smart_life_bot.storage`
- `smart_life_bot.config`
- `smart_life_bot.observability`

### 2.7 `smart_life_bot.storage`

**Назначение:** персистентный слой данных и состояния.

**Входит внутрь:**
- repositories/interfaces для users, credentials, conversation_state, events_log;
- транзакционная граница для согласованного обновления состояния и логов.

**Не входит:**
- доменная оркестрация;
- transport/callback сервер.

**Разрешённые зависимости:**
- `smart_life_bot.domain` (если нужно маппить сущности)
- `smart_life_bot.observability`
- инфраструктурные DB-библиотеки (в runtime-этапе)

### 2.8 `smart_life_bot.config`

**Назначение:** централизованная модель конфигурации и env.

**Входит внутрь:**
- schema/env parsing;
- default policy;
- валидация обязательных параметров.

**Не входит:**
- работа с внешними API;
- runtime бизнес-решения.

**Разрешённые зависимости:**
- минимальные (stdlib/конфиг-библиотека).

### 2.9 `smart_life_bot.observability`

**Назначение:** единый слой логирования и operational telemetry baseline.

**Входит внутрь:**
- структурное логирование;
- correlation id policy;
- error classification helper.

**Не входит:**
- отдельное analytics хранилище на MVP.

**Разрешённые зависимости:**
- `smart_life_bot.config`
- logging/tracing runtime libs.

## 3. Storage model

### 3.1 Рекомендованный baseline

- На MVP стартуем с **SQLite**.
- Схему и интерфейсы проектируем так, чтобы переход на PostgreSQL не требовал полной переделки domain/application слоев.

### 3.2 Сущности хранения

#### `users`
- `id`
- `telegram_user_id`
- `timezone`
- `created_at`
- `updated_at`

#### `provider_credentials`
- `id`
- `user_id`
- `provider`
- `auth_mode`
- `credentials_encrypted`
- `created_at`
- `updated_at`

#### `conversation_state`
- `id`
- `user_id`
- `state`
- `draft_payload`
- `active_field`
- `updated_at`

#### `events_log`
- `id`
- `user_id`
- `raw_text`
- `parsed_payload`
- `status`
- `google_event_id`
- `error_code`
- `error_details`
- `created_at`
- `updated_at`

#### `user_preferences`
- `user_id`
- `parser_mode` (`python` | `auto` | `llm`)
- `created_at`
- `updated_at`

### 3.3 Runtime notes для SQLite foundation (PR #5)

- Runtime storage реализован на stdlib `sqlite3` без ORM/миграционного фреймворка.
- `draft_payload` и `parsed_payload` сериализуются в JSON (TEXT).
- Timestamp-поля (`created_at`, `updated_at`) сохраняются в ISO-8601 строках.
- В `provider_credentials.credentials_encrypted` на этом шаге хранится переданная строка-placeholder; реальное шифрование и key management выносятся в отдельный шаг.
- Для parser mode preference используется отдельная таблица `user_preferences`; default mode при первом обращении — `python`.

### 3.4 Почему `provider_credentials` отдельно от `users`

- разделение зон ответственности: профиль пользователя и provider auth lifecycle;
- поддержка нескольких провайдеров/режимов без изменения базовой user-модели;
- снижение риска несанкционированного доступа: credentials изолируются и обслуживаются отдельным репозиторием/политикой шифрования.

### 3.5 Почему для MVP не нужен отдельный metrics storage

- MVP-фокус на надежном основном потоке, а не на отдельной аналитической подсистеме;
- `events_log` закрывает ключевые операционные потребности (статус, ошибка, источник, тайминг по timestamp);
- отдельное metrics storage увеличивает ops-сложность до подтверждения продуктовой необходимости.

### 3.6 Какие метрики можно получать из `events_log`

- доля успешных `confirm → created`;
- частота `parsing ambiguity`;
- частота `missing_auth` и `provider_auth_failure`;
- доля `calendar write failure`;
- среднее время завершения сценария (по `created_at/updated_at` и статусным обновлениям).

## 4. FSM model

### 4.1 Список состояний

- `IDLE`
- `WAITING_PREVIEW_CONFIRMATION`
- `EDITING_FIELD`
- `SAVING`

`SUCCESS` и `ERROR` считаются outcome transition, не обязательными persisted states.

### 4.2 Состояние `IDLE`

**Вход:** новый пользовательский диалог или reset после завершения/ошибки.

**Допустимые действия:** отправка нового текстового запроса.

**Выходы:**
- в `WAITING_PREVIEW_CONFIRMATION` после успешного parse+preview;
- остаётся `IDLE` при нераспознанном сообщении с запросом уточнения.

**Что хранится в `conversation_state`:**
- `state=IDLE`, `draft_payload=null`, `active_field=null`.

### 4.3 Состояние `WAITING_PREVIEW_CONFIRMATION`

**Вход:** сформирован preview draft.

**Допустимые действия:** `confirm`, `edit`, `cancel`.

**Выходы:**
- `confirm` → `SAVING`;
- `edit` → `EDITING_FIELD`;
- `cancel` → `IDLE`.

**Что хранится:**
- `draft_payload` с текущим событием;
- `active_field=null`.

### 4.4 Состояние `EDITING_FIELD`

**Вход:** пользователь выбрал редактирование.

**Допустимые действия:** изменение конкретного поля (date/time/title/etc), отмена редактирования.

**Выходы:**
- обратно в `WAITING_PREVIEW_CONFIRMATION` после обновления draft;
- в `IDLE` при cancel.

**Что хранится:**
- `draft_payload`;
- `active_field` (какое поле редактируется сейчас).

### 4.5 Состояние `SAVING`

**Вход:** пользователь подтвердил создание события.

**Допустимые действия:** пользовательский ввод обычно игнорируется или получает ответ «выполняется сохранение».

**Выходы:**
- success → `IDLE`;
- error → `IDLE` (с user-facing сообщением и логированием ошибки).

**Что хранится:**
- `draft_payload` на время сохранения;
- `active_field=null`.

## 5. Auth modes

### 5.1 `oauth_user_mode`

- **Target design** для нормального пользовательского сценария.
- Требует HTTPS callback/redirect flow.
- Предпочтителен для multi-user и масштабируемого поведения.

### 5.2 `service_account_shared_calendar_mode`

- Fallback / quick personal mode.
- Подходит для personal use.
- Не является target architecture.
- Требует ручного share календаря на service account.

### 5.3 Архитектурное правило

`auth_mode` влияет только на получение credentials/calendar client.

Основной application flow остаётся одинаковым вне зависимости от режима.

## 6. Parsing pipeline

Recommended pipeline:

1. **raw Telegram message** — исходный текст пользователя.
2. **normalization** — очистка/нормализация текста, дат, времени, локали.
3. **entity extraction** — извлечение title/date/time/metadata.
4. **confidence/ambiguity check** — оценка полноты и неоднозначности.
5. **event draft** — формирование внутреннего черновика.
6. **preview payload** — подготовка структуры для подтверждения пользователем.

Принцип:

- простые случаи обрабатываются максимально предсказуемо;
- сложные допускают более гибкий parsing;
- при низкой уверенности обязательно уточнение, без silent action.

Текущий parser mode runtime-реализации: Python/rule-based (единственный fully active parser).

Поддерживаются compact форматы даты/времени (включая optional comma между датой и временем, `HH:MM` и `HH MM`), а также русские month-name форматы (genitive + common abbreviations).

Для month-name форматов без явного года используется детерминированное правило: берётся текущий год, если дата не раньше `now`; иначе следующий год.

Parser mode выбирается как user-level preference через Telegram `/settings` и хранится в `user_preferences` (это не `.env`-переключатель поведения пользователя).

Текущее routing-поведение `ParserModeRouter`:
- `python` → Python/rule-based parser;
- `auto` → Python fallback (до реализации LLM parser);
- `llm` → not implemented / defensive Python fallback.

Планируемые parser modes (future): Python, LLM, Auto/hybrid (Python first, Claude LLM fallback).

## 6.1 Backlog: Telegram voice input (future)

Voice input не входит в текущий scope Phase 1 runtime и фиксируется как backlog-направление.

Целевой pipeline будущей реализации:

`Telegram voice message → STT transcription → existing text parser flow → preview → confirm/edit/cancel → Google Calendar write`

Требования для будущего этапа:
- STT и parser разделены по ответственности:
  - STT: audio → text;
  - parser: text → `EventDraft`.
- Предпочтительный STT-кандидат: ElevenLabs Scribe.
- Voice pipeline не обходит preview/confirm/edit/cancel.
- Cost/safety notes для будущей реализации:
  - короткие voice-сообщения ожидаемо low-cost;
  - нужны лимиты на max duration/file size;
  - длинные лекции не должны идти через этот bot flow;
  - не логировать API keys/credentials.

## 7. Event creation sequence

1. user sends message;
2. bot receives text;
3. parser returns event draft;
4. draft stored/attached to conversation state;
5. preview shown;
6. user confirms or edits;
7. application layer calls calendar service;
8. event log updated;
9. success or error response shown.

## 7.1 Runtime foundation status (PR #6)

Implemented in runtime foundation with integration-style tests on real SQLite repositories:

- `ProcessIncomingMessageUseCase` persists `WAITING_PREVIEW_CONFIRMATION` with draft payload;
- `events_log` is written as `received` and moved to `preview_ready`;
- `ConfirmEventDraftUseCase` сначала валидирует draft (required `start_at`, valid IANA timezone, `end_at > start_at`), и только после этого переходит в `SAVING`, резолвит auth и вызывает calendar abstraction;
- successful create writes `saved` status with provider event id and resets conversation state to `IDLE` (implemented as state reset);
- cancel action updates the same log entry to `cancelled` before resetting state;
- failed confirm writes `failed` status and restores `WAITING_PREVIEW_CONFIRMATION` with the same draft (retry/cancel remains possible);
- validation failure on confirm writes `failed` + `validation_error`, keeps draft editable in `WAITING_PREVIEW_CONFIRMATION`, and does not call auth/calendar adapters;
- if `draft.metadata.event_log_id` exists but is malformed, confirm is guarded as failed before auth/calendar calls and state is restored to `WAITING_PREVIEW_CONFIRMATION` with draft preserved;
- parser/auth/calendar are currently validated through fake/stub adapters in tests, without Telegram runtime, OAuth callback server, Google Calendar SDK/API runtime, or LLM parsing runtime.

## 7.2 Edit-flow foundation status (PR #8)

Implemented minimal application-layer edit flow on top of persisted `WAITING_PREVIEW_CONFIRMATION` state:

- `EditEventDraftFieldUseCase` now loads current conversation state and fails fast when no pending draft exists, state is not `WAITING_PREVIEW_CONFIRMATION`, or draft payload is missing;
- supported editable fields: `title`, `start_at`, `end_at`, `timezone`, `description`, `location`;
- datetime fields (`start_at`, `end_at`) are validated via `datetime.fromisoformat`; invalid format fails without mutating state;
- empty `title` or empty `timezone` is rejected; timezone edit additionally validates IANA timezone and rejects invalid values without mutating state;
- `start_at`/`end_at` edits are rejected when they would produce invalid range (`end_at <= start_at`), while `end_at` clear remains allowed;
- empty `description` / `location` clears the field; empty `end_at` clears optional end datetime;
- unsupported fields fail with state unchanged;
- successful edits persist updated draft back into `WAITING_PREVIEW_CONFIRMATION` and preserve draft metadata (including `metadata.event_log_id`);
- edit use case does not call auth provider or calendar service;
- confirm flow after edit uses the latest persisted draft values.

## 7.3 Runtime composition foundation status (PR #10)

Implemented minimal runtime composition layer for local/dev execution:

- added explicit `build_runtime(settings)` composition function to wire `Settings` → SQLite connection → schema init → repositories → fake/dev adapters → application use-cases → `TelegramTransportRouter` → `TelegramBotRuntime`;
- composition uses existing `DATABASE_URL` and initializes schema on bootstrap (`CREATE TABLE IF NOT EXISTS` path from storage layer);
- fake/dev adapters for parser/auth/calendar are deterministic and marked dev-only; they do not call Telegram API, Google API, OAuth callback, or LLM parsing runtime;
- composition injects a context-safe logger adapter compatible with application use-cases (`logger.info/error(..., **context)`), avoiding stdlib kwargs incompatibility;
- `main.py` now builds runtime graph and logs safe bootstrap status without starting Telegram polling/webhook;
- added runtime composition tests for wiring, in-memory SQLite, transport callback flow, and no-network behavior.

## 7.4 Telegram SDK adapter foundation status (PR #11)

Implemented minimal real Telegram SDK adapter layer using `python-telegram-bot`:

- added adapter module that builds `telegram.ext.Application` from `settings.telegram_bot_token`;
- registered deterministic handlers for `/start`, plain text (excluding commands), and callback query pattern for `draft:confirm`, `draft:edit`, `draft:cancel`;
- SDK handlers delegate directly to existing runtime contract (`on_start`, `on_text`, `on_callback`) without duplicating application/domain behavior;
- `TelegramTransportResponse` is mapped to Telegram replies, including `InlineKeyboardMarkup` when buttons are present;
- callback queries are answered before sending response message;
- tests validate handler registration and delegation behavior without bot token validation calls, Telegram API calls, or network.

## 7.5 Google Calendar service-account adapter foundation status (PR #13)

Implemented first real Google Calendar write adapter for `service_account_shared_calendar_mode`:

- added `GoogleCalendarService` behind existing `CalendarService` contract;
- adapter validates auth context mode and rejects writes outside service-account mode;
- adapter maps `CalendarEventCreateRequest` to Google Calendar `events.insert` body (`summary`, optional `description/location`, `start/end` datetime + timezone);
- runtime composition now wires real Google adapter when `GOOGLE_AUTH_MODE=service_account_shared_calendar_mode` and required service-account settings are present;
- `oauth_user_mode` remains fake/dev for calendar writes (OAuth callback/user-consent flow remains out of scope);
- confirm success response now surfaces provider event link when calendar adapter returns `html_link` (keeps backward-compatible success text when link is absent), which supports VPS smoke validation;
- tests cover event-body mapping, calendar-id routing, response mapping, error paths, and runtime wiring without real Google network calls.


## 7.6 Safe preflight diagnostics status (PR #15)

Implemented explicit safe preflight entrypoint for VPS/runtime readiness checks:

- added `python -m smart_life_bot.runtime.preflight` command;
- preflight validates env/config safety markers, timezone availability, SQLite schema init, and runtime composition wiring;
- preflight builds runtime graph and closes DB connection without starting Telegram polling;
- no Telegram/Google network calls are performed by preflight checks;
- preflight output is safe: secrets (bot token, raw DATABASE_URL, service account/private key payloads) are not printed.



## 7.7 Parser mode router + Claude foundation status (PR #20+)

Implemented parser mode routing foundation behind existing `MessageParser` contract:

- added `ParserModeRouter`, which reads `user_preferences` via `get_or_create_for_user(..., default_parser_mode=python)` before parsing;
- runtime composition now injects parser as `ParserModeRouter(user_preferences_repo, python_parser)` while keeping `ProcessIncomingMessageUseCase` unchanged;
- current routing behavior is explicit: `python` routes to Python parser only, `llm` routes to Claude parser when configured (else defensive Python fallback), `auto` runs Python first and calls Claude fallback only for ambiguous/low-confidence results when configured;
- router preserves underlying parser metadata (`source`, `raw_text`, `user_id`, etc.) and appends routing metadata for observability in draft/event-log payload;
- invalid/stale parser mode values in DB are handled defensively with Python fallback instead of crashing the message flow.
- LLM integration remains optional at runtime (`LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `LLM_MODEL` etc.); Python mode stays fully functional without LLM configuration.

## 8. Error model

Минимальная классификация:

- `parsing ambiguity`
- `validation error`
- `missing auth`
- `provider auth failure`
- `calendar write failure`
- `state inconsistency`
- `unexpected internal error`

### 8.1 Пользовательские ошибки (user-facing)

- `parsing ambiguity`
- `validation error`
- `missing auth`

Поведение: понятное сообщение пользователю + следующий шаг (уточнить, исправить, пройти auth).

### 8.2 Системные ошибки (system-facing)

- `provider auth failure`
- `calendar write failure`
- `state inconsistency`
- `unexpected internal error`

Поведение: безопасный ответ без деталей секьюрити, обязательное структурное логирование (код, контекст, correlation id).

## 9. Config / env model

Детальная спецификация вынесена в `docs/CONFIGURATION.md`.

## 10. Что не реализуется в этом документе

- SQL миграции;
- ORM mapping;
- aiogram handlers;
- OAuth callback server;
- Google Calendar API client runtime;
- production deployment orchestration.

## 11. Pending / Open questions

1. Формат `draft_payload` (JSON schema vs typed serialization). **Open question**.
2. Минимально обязательные поля для `error_details` в `events_log`. **Pending**.
3. Политика ротации/маскирования логов при ошибках provider. **Pending**.
