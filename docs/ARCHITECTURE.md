# Architecture Baseline — Smart Life Ops Bot

## 1. Обзор

Smart Life Ops Bot проектируется как modular monolith с четкими внутренними границами и единой продуктовой логикой для сценариев фиксации событий и записи в календарь.

## 2. Архитектурные принципы

- Надежность важнее широты функционала.
- Явное подтверждение перед внешними side effects.
- Единый бизнес-поток, независимый от конкретной реализации auth-mode.
- Поддерживать простоту bootstrap-этапа; низкоуровневые выборы откладывать до необходимости.
- Дисциплина documentation-first.

## 3. Подход modular monolith

Для MVP система остается одним разворачиваемым приложением, где модули разделены по зонам ответственности и контрактам. Это снижает операционную сложность и одновременно сохраняет путь эволюции для возможного выделения сервисов в будущем.

## 4. Планируемые модули

- `bot_entry` — Telegram ingress и адаптер исходящих сообщений.
- `orchestration` — управление потоком между шагами parse/preview/confirm/create.
- `parsing` — извлечение и нормализация полей события.
- `confirmation` — рендер preview и обработка решений confirm/edit/cancel.
- `calendar` — абстракция провайдера и конкретный адаптер Google Calendar.
- `auth` — auth-абстракция для поддерживаемых режимов Google auth.
- `storage` — интерфейс персистентности состояния и авторизационных данных.
- `logging_observability` — основа для структурных логов и отчетности об ошибках.

> Pending: финальное разбиение на пакеты/модули и интерфейсы будет формализовано на этапах реализации.

## 5. Auth abstraction

Единая auth-абстракция скрывает детали конкретного auth-mode от продуктового потока:

- `oauth_user_mode` (target design)
- `service_account_shared_calendar_mode` (fallback quick personal mode)

Дублирование логики пользовательского потока по auth-mode не допускается.

> Pending: детали жизненного цикла токенов, обработка обновления credentials и taxonomy ошибок.

## 6. Storage layer

Storage layer отвечает за:

- состояние conversation/session,
- переходы состояния подтверждения,
- метаданные, связанные с auth.

На bootstrap-этапе storage остается на уровне проектирования интерфейса; выбор конкретного backend пока pending.

> Pending: выбор backend, схема, стратегия миграций, политика retention.

## 7. Bot/FSM layer

Bot-layer и поведение state machine планируются как отдельные зоны ответственности:

- transport adapter бота (Telegram),
- логика state orchestration.

На bootstrap-этапе handlers и внутренности FSM не реализуются.

> Pending: модель FSM, политика команд, поведение retry и idempotency.

## 8. Parsing layer

Parsing преобразует входящий текст в нормализованный draft события для preview и последующего подтверждения.

Bootstrap фиксирует только роль parsing-слоя.

> Pending: стратегия parsing, модель confidence, работа с locale/timezone, политика разрешения неоднозначностей.

## 9. Layer интеграции с календарем

Модуль calendar предоставляет стабильный внутренний интерфейс для создания событий.

Google Calendar — первая целевая интеграция.

На этапе bootstrap низкоуровневая реализация API намеренно исключена.

> Pending: выбор API-клиента, mapping ошибок, обработка quota, семантика idempotent create.

## 10. Обзор деплоя

Deployment baseline:

- source of truth в GitHub,
- CI/CD через GitHub Actions,
- runtime на базе Docker,
- целевой хост: VPS (Contabo),
- production hostname через Cloudflare-managed subdomain.

Подробные процедуры намеренно отложены до последующего этапа hardening деплоя.

## 11. Технические решения, которые пока pending

- Конкретная технология storage.
- Стиль и границы реализации FSM.
- Детальный алгоритм и инструменты parsing.
- Паттерн callback для Google OAuth и безопасного хранения токенов.
- Модель runtime-процессов и глубина observability-стека.
