# Журнал начальных решений (ADR-like)

## Легенда статусов

- **Accepted** — активное базовое решение.
- **Pending** — пока не принято.

---

## D-001: Telegram-бот — основной канал ввода

- **Status:** Accepted
- **Decision:** Использовать Telegram-бот как основную точку входа для MVP.
- **Rationale:** Быстрый цикл взаимодействия с пользователем и прозрачный workflow на основе сообщений.

## D-002: “Saved Messages / Избранное” не является основным путем интеграции

- **Status:** Accepted
- **Decision:** Не опираться на Telegram Saved Messages как на основной путь продуктовой интеграции.
- **Rationale:** Продукт должен работать как явный bot-based assistant, а не как побочный сценарий.

## D-003: Modular monolith для MVP

- **Status:** Accepted
- **Decision:** Реализовывать MVP как modular monolith.
- **Rationale:** Минимизация ops-сложности и сохранение высокой скорости итераций по функционалу.

## D-004: Google Calendar — первая интеграция

- **Status:** Accepted
- **Decision:** В MVP приоритизировать создание событий в Google Calendar.
- **Rationale:** Прямое соответствие целевой пользовательской ценности и начальному scope.

## D-005: OAuth — целевой auth design

- **Status:** Accepted
- **Decision:** `oauth_user_mode` — предполагаемый долгосрочный путь аутентификации.
- **Rationale:** Корректная модель авторизации на уровне пользователя для масштабируемого поведения продукта.

## D-006: Service Account + shared calendar — только fallback

- **Status:** Accepted
- **Decision:** `service_account_shared_calendar_mode` допустим только как fallback / quick personal mode.
- **Rationale:** Полезно для ранней практичности, но не является целевой архитектурой.

## D-007: Готовность CI/CD с первого дня

- **Status:** Accepted
- **Decision:** Подготовить фундамент CI/CD с самого старта проекта.
- **Rationale:** Сохранение инженерной дисциплины и снижение интеграционных рисков.

## D-008: Документация и код развиваются вместе

- **Status:** Accepted
- **Decision:** Любое изменение архитектуры/конфига/workflow/deployment/поведения должно сопровождаться обновлением документации.
- **Rationale:** Поддерживать понятность и сопровождаемость проекта при быстрых итерациях.

## D-009: SQLite как storage baseline для MVP

- **Status:** Accepted
- **Decision:** Использовать SQLite как стартовый backend хранения в Phase 1 реализации.
- **Rationale:** Минимальная операционная сложность и быстрый запуск, при сохранении пути миграции на PostgreSQL.

## D-010: `provider_credentials` хранить отдельно от `users`

- **Status:** Accepted
- **Decision:** Выделить отдельную сущность `provider_credentials`, связанную с `users` по `user_id`.
- **Rationale:** Разделение ответственности, расширяемость по auth/provider и безопасное управление жизненным циклом credentials.

## D-011: `events_log` как основной операционный журнал

- **Status:** Accepted
- **Decision:** Использовать `events_log` как центральный журнал шагов и исходов event creation flow.
- **Rationale:** Дает трассируемость сценариев, базу для отладки и источник MVP-метрик без отдельной analytics подсистемы.

## D-012: `conversation_state` как явный persisted слой FSM

- **Status:** Accepted
- **Decision:** Персистить состояние диалога в `conversation_state`.
- **Rationale:** Повышает надежность при рестартах и упрощает контроль переходов состояния.

## D-013: Два auth mode за единой абстракцией

- **Status:** Accepted
- **Decision:** Поддерживать `oauth_user_mode` и `service_account_shared_calendar_mode` за единым auth-контрактом.
- **Rationale:** Сохраняет единый application flow и исключает дублирование бизнес-логики по режимам.

## D-014: MVP-метрики извлекаются из логов, без отдельного analytics storage

- **Status:** Accepted
- **Decision:** На этапе MVP не вводить отдельное metrics/analytics хранилище.
- **Rationale:** Снижение объема инфраструктуры при сохранении операционной наблюдаемости через `events_log` и структурные логи.

## D-015: SQLite runtime implementation на stdlib `sqlite3` без ORM/миграций

- **Status:** Accepted
- **Decision:** Первый runtime storage implementation для Phase 1 реализовать напрямую на `sqlite3` (stdlib), с инициализацией схемы через SQL `CREATE TABLE IF NOT EXISTS`.
- **Rationale:** Минимальная сложность для MVP, быстрый запуск и проверяемый baseline репозиториев; ORM/migrations откладываются до подтвержденной необходимости.

## D-016: Telegram transport foundation без жёсткой привязки к Telegram SDK

- **Status:** Accepted
- **Decision:** На шаге transport foundation реализовать Telegram routing abstraction (handlers mapping в application use-cases) без добавления `python-telegram-bot`/`aiogram` runtime зависимости.
- **Rationale:** Проверка корректности прикладного flow (`/start`, text, confirm/edit/cancel) без сетевого рантайма и без расширения scope до webhook/long-polling инфраструктуры.

## D-017: `python-telegram-bot` как SDK adapter для MVP runtime

- **Status:** Accepted
- **Decision:** Использовать `python-telegram-bot` как Telegram SDK adapter поверх существующего `TelegramBotRuntime`/`TelegramTransportRouter`.
- **Rationale:** Mature async SDK, straightforward handler model, и хорошее соответствие текущей transport-boundary архитектуре без внедрения Telegram SDK в application/domain слои.

## D-018: Deterministic rule-based parser before LLM parser

- **Status:** Accepted
- **Decision:** Use a deterministic rule-based parser as the first real parser baseline before adding LLM parsing.
- **Rationale:** Enables useful Telegram/VPS demo behavior without LLM cost, latency, external dependencies, or non-determinism.

## D-019: Service-account shared calendar adapter before OAuth runtime

- **Status:** Accepted
- **Decision:** Implement service-account shared calendar adapter before OAuth user-mode runtime.
- **Rationale:** Enables the first real VPS/Telegram calendar-write smoke test without introducing OAuth callback, HTTPS redirect URI, or user consent flow complexity.

## D-020: Separate parser strategies behind MessageParser abstraction

- **Status:** Accepted
- **Decision:** Keep parser implementations separated behind the `MessageParser` abstraction: Python/rule-based parser, future LLM parser, and future Auto/hybrid parser.
- **Rationale:** Python parsing is cheap, fast and deterministic for common formats. LLM parsing should be used later for ambiguous or natural-language inputs, not necessarily for every message. This preserves cost control while keeping a path to better UX.

## D-021: Parser mode is a user preference, not an env-only runtime switch

- **Status:** Accepted
- **Decision:** Store parser mode as a user-level preference and expose it through Telegram settings UI instead of requiring `.env` edits.
- **Rationale:** Parser mode is a product behavior choice. Users should be able to change it without redeploying or editing server env variables. Runtime env remains deployment/configuration scope, while per-user parsing behavior belongs in persistent user preferences.

## D-022: ParserModeRouter keeps non-implemented modes safe via Python fallback

- **Status:** Accepted
- **Decision:** Keep `ParserModeRouter` in the real parsing path and route `python` to Python parser, while `auto` and `llm` remain safe Python fallbacks until LLM parser is implemented.
- **Rationale:** Preserves stable UX and deterministic behavior now, avoids dead routes, and keeps a clean extension point for future Claude parser integration without changing application use-cases.

## D-023: Telegram voice input deferred to backlog with STT-first separation

- **Status:** Accepted
- **Decision:** Keep Telegram voice input out of current implementation scope and treat it as backlog; when implemented, flow must be `voice → STT → existing text parser flow → preview/confirm`.
- **Rationale:** Limits current scope, preserves existing safety guarantees (mandatory preview before write), and enforces clear boundary between STT (audio→text) and parser (text→EventDraft). Preferred future STT candidate is ElevenLabs Scribe, with guardrails for max duration/file size and no processing of long lectures.

## D-024: Claude is the first LLM parser provider

- **Status:** Accepted
- **Decision:** Use Anthropic Claude as the first LLM parser provider behind `MessageParser`.
- **Rationale:** Claude provides strong natural-language parsing ability for Russian/English calendar inputs while preserving existing preview/confirm safety. Model choice remains env-configurable so Haiku can be used for cost-efficient parsing and Sonnet can be used later for higher-quality parsing.
