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

**Runtime status (PR #9 foundation):**
- реализован минимальный Telegram transport router поверх application use-cases;
- поддержаны маршруты `/start`, plain text draft-preview, `confirm`, `cancel`, `edit` command (`/edit <field> <value>`);
- real Telegram SDK polling/webhook runtime остаётся pending.

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

### 3.3 Runtime notes для SQLite foundation (PR #5)

- Runtime storage реализован на stdlib `sqlite3` без ORM/миграционного фреймворка.
- `draft_payload` и `parsed_payload` сериализуются в JSON (TEXT).
- Timestamp-поля (`created_at`, `updated_at`) сохраняются в ISO-8601 строках.
- В `provider_credentials.credentials_encrypted` на этом шаге хранится переданная строка-placeholder; реальное шифрование и key management выносятся в отдельный шаг.

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
- `ConfirmEventDraftUseCase` loads pending draft, transitions state to `SAVING`, resolves auth via abstraction, and calls calendar abstraction;
- successful create writes `saved` status with provider event id and resets conversation state to `IDLE` (implemented as state reset);
- cancel action updates the same log entry to `cancelled` before resetting state;
- failed confirm writes `failed` status and restores `WAITING_PREVIEW_CONFIRMATION` with the same draft (retry/cancel remains possible);
- if `draft.metadata.event_log_id` exists but is malformed, confirm is guarded as failed before auth/calendar calls and state is restored to `WAITING_PREVIEW_CONFIRMATION` with draft preserved;
- parser/auth/calendar are currently validated through fake/stub adapters in tests, without Telegram runtime, OAuth callback server, Google Calendar SDK/API runtime, or LLM parsing runtime.

## 7.2 Edit-flow foundation status (PR #8)

Implemented minimal application-layer edit flow on top of persisted `WAITING_PREVIEW_CONFIRMATION` state:

- `EditEventDraftFieldUseCase` now loads current conversation state and fails fast when no pending draft exists, state is not `WAITING_PREVIEW_CONFIRMATION`, or draft payload is missing;
- supported editable fields: `title`, `start_at`, `end_at`, `timezone`, `description`, `location`;
- datetime fields (`start_at`, `end_at`) are validated via `datetime.fromisoformat`; invalid format fails without mutating state;
- empty `title` or empty `timezone` is rejected; empty `description` / `location` clears the field; empty `end_at` clears optional end datetime;
- unsupported fields fail with state unchanged;
- successful edits persist updated draft back into `WAITING_PREVIEW_CONFIRMATION` and preserve draft metadata (including `metadata.event_log_id`);
- edit use case does not call auth provider or calendar service;
- confirm flow after edit uses the latest persisted draft values.

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
