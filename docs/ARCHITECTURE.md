# Архитектура Phase 1 — Smart Life Ops Bot

## 1. Цель технической архитектуры Phase 1

Цель этого этапа — зафиксировать рабочую техническую архитектуру для реализации MVP-сценария:

`message → parsing → preview → confirm / edit / cancel → create event`

Этот документ не вводит production-реализацию интеграций, а задает:

- границы модулей;
- правила зависимостей;
- единый application flow;
- baseline по хранению состояния, авторизации и логированию.

## 2. Границы реализации

В рамках Phase 1 (design-only technical architecture pass):

- фиксируются архитектурные контракты и ответственность слоев;
- фиксируется рекомендуемая storage/FSM/config-модель;
- фиксируется единая схема event creation flow.

Явно вне реализации этого шага:

- runtime Google API calls для `oauth_user_mode`;
- OAuth callback implementation;
- aiogram handlers и FSM runtime;
- ORM, migrations и реальная DB-логика;
- production-ready deployment hardening.

## 3. Общий flow системы

1. Пользователь отправляет текстовое сообщение в Telegram.
2. Bot transport layer передает текст в application layer.
3. Parsing pipeline строит `event draft` и оценку уверенности.
4. Application layer формирует preview и переводит диалог в состояние ожидания решения.
5. Пользователь выбирает: `confirm`, `cancel` или `edit`.
6. При `edit` изменяется draft и повторно показывается preview.
7. При `confirm` запускается сохранение события через calendar integration layer.
8. Результат пишется в `events_log`, пользователь получает success/error ответ.



## 3.1 Missing `start_at` recovery UX boundary (MVP)

Для случая, когда parser вернул draft с `missing_start_at`, фиксируется near-term UX-подход:

- recovery выполняется в Telegram inline flow (`📅 Выбрать дату`) без отдельного frontend;
- inline calendar callbacks управляют только выбором даты;
- после даты время вводится отдельным текстовым сообщением `HH:MM`;
- итоговый `start_at` собирается как `selected_date + HH:MM + user_timezone`;
- до этого шага preview остаётся non-confirmable.

Guardrails архитектуры:
- inline picker не вызывает calendar provider;
- единственный write-path в Google Calendar остаётся `Confirm` use-case;
- picker доступен только при наличии pending draft;
- stale callbacks fail-safe (без записи и без неявной мутации чужого/устаревшего state);
- `Cancel` очищает как draft state, так и picker-related state;
- существующие direct flows (`/edit`, обычное текстовое создание draft) сохраняются.

Допустимая callback naming-схема (концептуально):
- `calendar_picker:open`
- `calendar_picker:prev:YYYY-MM`
- `calendar_picker:next:YYYY-MM`
- `calendar_picker:date:YYYY-MM-DD`

Telegram Web App / Mini App календарный UI зафиксирован как deep backlog и не входит в near-term MVP scope (отдельный frontend/hosting/security/deploy contour).

## 4. Слои системы

### 4.0 Transport strategy boundary (current + future)

- Current runtime remains Telegram-first: Telegram transport is the only active runtime adapter in MVP.
- Telegram layer must stay an adapter over application use-cases, not the owner of business/domain logic.
- Domain/application/storage contracts should remain transport-agnostic and JSON-friendly where practical, so future FastAPI REST adapter can reuse the same use-cases.
- Future client path remains backlog: PWA / Telegram Mini App first, while APK/native wrapper stays deeper backlog due to extra mobile release overhead.
- Offline-first client direction for cashback is captured separately in D-030 and does not change current MVP runtime scope.

### 4.1 Bot transport layer

Отвечает за входящие/исходящие сообщения Telegram и трансляцию transport-событий в application-команды.

На текущем runtime-этапе реализован минимальный transport router (`/start`, plain text, `confirm`, `cancel`, `edit` command routing в application use-cases) и добавлен тонкий SDK adapter foundation на `python-telegram-bot`, который маппит Telegram updates в `TelegramBotRuntime` без переноса бизнес-логики в SDK handlers.

Навигационная модель Telegram фиксируется как разные уровни transport UX:
- native command menu (`/start`, `/settings`, future `/help`) — глобальные команды;
- footer reply keyboard после `/start` — feature-навигация (первый раздел: `📅 Календарь`);
- inline preview buttons — только draft-level действия (confirm/edit/cancel/duration; reminder controls только при поддерживаемом capability).

Не содержит:

- доменную валидацию;
- работу с credentials;
- прямой вызов провайдера календаря.
- orchestration бизнес-flow вне runtime transport boundary.

### 4.2 Application / use case layer

Оркестрация сценариев: parse, preview, explicit duration controls, confirm/edit/cancel, save event; а также capability-gating UI-элементов по активному calendar mode.

Confirm-gate обязателен: запись в календарь допускается только после явного `confirm`.

Содержит use-case уровень и координацию между domain/auth/calendar/storage.

### 4.3 Domain layer

Содержит доменные модели и инварианты event draft, validation и transition-правил.

Не зависит от Telegram SDK, Google SDK и storage-деталей.

### 4.4 Auth / provider layer

Предоставляет единый интерфейс получения credentials/client для выбранного `auth_mode`.

### 4.5 Calendar integration layer

Единая абстракция записи события в календарь.

Google Calendar — первая реальная реализация провайдера для `service_account_shared_calendar_mode` (текущий рабочий runtime path).
OAuth runtime-адаптер остается pending и пока не реализуется (`oauth_user_mode`).

Reminder controls — capability-gated behavior: в `service_account_shared_calendar_mode` нельзя считать custom reminders надежным user-visible capability; в будущем `oauth_user_mode` можно включать reminders после отдельной верификации.

### 4.6 Storage layer

Персистентность:

- пользователя;
- credentials провайдера;
- состояния диалога (FSM snapshot);
- операционного журнала событий.

### 4.7 Observability / logging layer

Структурные логи, error-категории, correlation identifiers, операционные статусы.

### 4.8 Runtime composition layer

Отвечает за явную сборку runtime graph из `Settings` без глобального состояния:

- инициализация SQLite connection + schema;
- создание repository-реализаций;
- подключение детерминированного rule-based parsing адаптера и локальных fake/dev адаптеров auth/calendar;
- wiring application use-cases;
- wiring `TelegramTransportRouter` и `TelegramBotRuntime`.
- wiring SDK adapter builder (`telegram.ext.Application`) для явного polling-entrypoint.

Не содержит в bootstrap-режиме (`main.py`):

- auto-start long polling/webhook lifecycle;
- сетевые вызовы Telegram/Google API.

## 5. Границы модулей

Базовые модули в modular monolith:

- `smart_life_bot.bot`
- `smart_life_bot.application`
- `smart_life_bot.domain`
- `smart_life_bot.parsing`
- `smart_life_bot.calendar`
- `smart_life_bot.auth`
- `smart_life_bot.storage`
- `smart_life_bot.config`
- `smart_life_bot.observability`

Детальные границы модулей зафиксированы в `docs/PHASE1_TECHNICAL_SPEC.md`.

## 6. Правило зависимости между слоями

Dependency rule:

- внешние слои могут зависеть от внутренних контрактов;
- внутренние слои не зависят от внешних реализаций.

Практически:

- `bot` зависит от `application`;
- `application` зависит от контрактов `domain/parsing/auth/calendar/storage/observability`;
- `domain` не зависит от `bot`, SDK и инфраструктурных адаптеров;
- адаптеры (`calendar`, `storage`, `auth`) реализуют интерфейсы, используемые application layer.
- `runtime` зависит от `config`, `storage`, `application`, `bot`, `observability` и только собирает граф зависимостей.

## 7. Единый event creation flow без дублирования под разные auth-mode

Ключевое архитектурное правило: application flow один и тот же для любого `GOOGLE_AUTH_MODE`.

`auth_mode` влияет только на этап получения действующего calendar client / credentials.

Недопустимо:

- дублировать use-case ветки `confirm/save` под каждый auth-mode;
- переносить auth-specific if/else в доменные модели.

## 8. Auth abstraction

Поддерживаются два режима:

1. `oauth_user_mode` (target design)
2. `service_account_shared_calendar_mode` (fallback / quick personal)

Auth abstraction должна предоставлять единый контракт уровня application:

- получить auth context для пользователя;
- вернуть ошибку класса `missing_auth` или `provider_auth_failure`;
- отдать provider-ready credentials/client handle.

**Pending:** конкретный lifecycle refresh token и secure key management policy.

## 9. Storage architecture

Recommended baseline для MVP:

- SQLite как стартовый storage backend;
- схема проектируется с учетом дальнейшей миграции на PostgreSQL без переделки domain contract.

Основные сущности хранения:

- `users`
- `provider_credentials`
- `conversation_state`
- `events_log`

Детальная модель и rationale — в `docs/PHASE1_TECHNICAL_SPEC.md`.

## 10. FSM / conversation state model

Recommended persisted states:

- `IDLE`
- `WAITING_PREVIEW_CONFIRMATION`
- `EDITING_FIELD`
- `SAVING`

`SUCCESS`/`ERROR` трактуются как outcome transition, а не обязательные долгоживущие persisted states.

## 11. Parsing pipeline and strategy

Recommended pipeline:

1. raw Telegram message
2. normalization
3. entity extraction
4. confidence/ambiguity check
5. event draft
6. preview payload

`MessageParser` — базовая абстракция parsing слоя.

Текущая runtime-реализация: детерминированный Python/rule-based parser (без LLM, без Telegram SDK dependency и без Google Calendar dependency внутри parsing слоя). Это единственная полностью активная parser-реализация в production path. Parser покрывает common compact RU форматы даты/времени и форматы с русскими названиями/сокращениями месяцев.

Планируемая отдельная реализация: LLM parser (pending, не реализован в текущем этапе).

Целевой режим следующих этапов: Auto/hybrid parser mode, где pipeline пробует rule-based parser первым и использует fallback в LLM parser только при низкой уверенности или ambiguity.
Parser mode фиксируется как user-level preference в storage (`user_preferences`) и настраивается через Telegram `/settings`; это поведение transport/application уровня, а не env-only runtime switch.
Runtime parsing маршрутизируется через `ParserModeRouter` (за `MessageParser` abstraction), который читает `user_preferences` и выбирает безопасный маршрут:
- `python` → Python/rule-based parser (без вызовов LLM);
- `llm` → Claude parser только когда LLM configured; иначе defensive Python fallback;
- `auto` → Python first; если результат ambiguous/low-confidence (или `missing_start_at`), router пробует Claude fallback только когда LLM configured; иначе возвращается Python fallback.

Первая LLM-реализация подключена как `ClaudeMessageParser` (Anthropic SDK) за тем же `MessageParser` контрактом, без изменения application use-cases. Model selection остаётся env-configurable (`LLM_MODEL`, без hardcode в router/use-cases): default `claude-haiku-4-5-20251001`, higher-quality option `claude-sonnet-4-6`.

При низкой уверенности система должна запрашивать уточнение, а не выполнять silent action.

Product flow при этом не меняется: preview и явное confirm перед записью события обязательны для всех parser-режимов.

## 11.1 Backlog: Telegram voice input (future, out of current scope)

Telegram voice input относится к будущему scope и не реализован в текущем runtime.

Целевой будущий поток:

`Telegram voice message → STT transcription → existing text parsing flow → preview → confirm/edit/cancel → create event`

Архитектурные требования для backlog-реализации:
- STT и parser остаются разными компонентами и не смешивают ответственность:
  - STT: audio → text;
  - parser: text → `EventDraft`.
- Voice flow не должен обходить обязательный preview/confirm этап.
- Предпочтительный кандидат STT для будущего этапа: ElevenLabs Scribe.
- Нужны cost/safety guardrails на этапе внедрения: ограничения на длительность/размер voice-сообщения и отказ от обработки длинных лекций.

## 12. Configuration / env model

Единая config-модель включает:

- общие переменные runtime;
- auth-mode-specific переменные;
- чувствительные секреты с явной маркировкой.

Подробный перечень — в `docs/CONFIGURATION.md`.

## 13. Ошибки и recovery strategy

Минимальная классификация:

- parsing ambiguity;
- validation error;
- missing auth;
- provider auth failure;
- calendar write failure;
- state inconsistency;
- unexpected internal error.

Recovery baseline:

- пользовательские ошибки → понятный ответ + предложение исправить/повторить;
- системные ошибки → логирование с контекстом, безопасный user-facing ответ, без утечки чувствительных данных;
- сбои состояния (`state inconsistency`) → reset к `IDLE` с информированием пользователя.

## 14. Что остается вне реализации текущего шага

- Реальный OAuth redirect/callback сервер.
- Реализация Telegram handlers/FSM runtime.
- Реальные SQL migrations и ORM-схема.
- Производственный observability stack (dashboards, alerting).

## 15. Open questions

1. Нужна ли отдельная стратегия retention/TTL для `conversation_state` в MVP или достаточно manual reset. **Pending**.
2. Нужен ли отдельный `idempotency_key` в `events_log` уже в Phase 1 runtime-реализации. **Open question**.
3. Какие поля parsing confidence хранить в `events_log` в обязательном минимуме. **Pending**.
