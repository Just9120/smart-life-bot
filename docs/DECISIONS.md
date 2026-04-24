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
