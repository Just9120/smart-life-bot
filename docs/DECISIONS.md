# Журнал начальных решений (ADR-like)

> **Role:** Canonical ADR-style decision log (why, trade-offs, status). Do not duplicate full implementation specs/runbook steps here; reference [Architecture](ARCHITECTURE.md), [Implementation roadmap](IMPLEMENTATION_ROADMAP.md), and operational docs when needed.

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

## D-025: Explicit duration/reminder UX via Telegram inline controls + deterministic default reminders

- **Status:** Accepted
- **Decision:** Do not parse duration or reminder overrides from ordinary free text. Duration can be changed only through explicit UI actions (preview button `⏱ Длительность` and existing explicit edit/admin flows). Reminder overrides can be changed only through explicit preview inline reminder options (`🔔 Уведомления`). If user does not select reminder options, keep deterministic Google Calendar popup overrides (`60` and `30`, no email reminders). If duration is not explicitly selected, keep draft-level `end_at` unset; provider-layer technical fallback for required `end_at` may still apply.
- **Rationale:** Prevents accidental event mutations from incidental wording, keeps draft changes explicit and auditable in preview flow, preserves deterministic reminder behavior by default, and keeps calendar writes strictly confirm-gated.

## D-026: Google Calendar reminders are always explicit popup overrides (no email)

- **Status:** Accepted
- **Decision:** Calendar adapter must always send explicit reminder payload with `useDefault=false` and popup-only `overrides`. Default bot behavior uses popup reminders at 60 and 30 minutes. When user selects a custom reminder via Telegram reminder controls, adapter sends exactly the selected popup minute set (for example `(30,)` or `(10,)`).
- **Rationale:** Prevents accidental fallback to calendar-level defaults, keeps reminder behavior deterministic across environments, and guarantees the bot never creates email reminders.

## D-027: Telegram navigation uses command menu + footer feature menu; custom reminders are OAuth-only

- **Status:** Accepted
- **Decision:** Разделить Telegram-навигацию на два уровня: (1) нативное command menu Telegram (кнопка `Menu` / команды вроде `/start`, `/settings`, future `/help`) для глобальных команд, и (2) persistent footer/reply keyboard после `/start` для продуктовой навигации по функциям (первый пункт: `📅 Календарь`).
- **Decision:** Inline-кнопки под preview остаются только draft-level действиями (`✅ Создать событие`, `⏱ Длительность`, `Edit`, `Cancel`; внутренний callback подтверждения — `draft:confirm`) и не заменяют feature-навигацию.
- **Decision:** Для `📅 Календарь` фиксируется продуктовая модель режимов: `⚡ Быстрый режим` (текущий `service_account_shared_calendar_mode`) и `🔐 Личный Google Calendar` (future `oauth_user_mode`).
- **Decision:** Reminder controls должны быть capability-gated по активному calendar mode: в `⚡ Быстрый режим` не обещаем/не показываем кастомные reminders как рабочую user-visible фичу; в `🔐 Личный Google Calendar` reminders включаются только после реализации и верификации OAuth user-authenticated writes.
- **Decision:** Для future reminder UX в `🔐 Личный Google Calendar` выбор reminder presets должен быть multi-select (один или несколько popup вариантов одновременно, например `10 минут + 1 час`) через checkbox-style inline pattern или эквивалент; email reminders остаются запрещены.
- **Rationale:** Бот масштабируется за пределы одного draft-flow, поэтому нужна явная модель feature-навигации. Live-тесты в service-account режиме показали, что user-visible reminders в Google Calendar не отражают надежно bot-selected overrides: при включенных Google defaults в UI отображались default reminders (например popup 30 мин + email 10 мин), а после удаления defaults новый event с выбранным в боте `30 мин` показывался в UI без reminders. Следовательно, в текущем MVP reminders — future/OAuth capability, а не гарантированная фича service-account режима.

## D-028: Cashback MVP module with deterministic structured parsing

- **Status:** Accepted
- **Decision:** Add separate `💳 Кэшбек` module with isolated SQLite table `cashback_categories` in the same DB, deterministic structured add format `банк, владелец, категория, процент` (+ optional month), and month-safe transition behavior (no silent auto-next-month in day 25+).
- **Rationale:** Keeps calendar flow isolated and stable while enabling quick family cashback lookup; deterministic Python-first behavior reduces ambiguity/cost/risk for MVP.
- **Notes:** Owners whitelist for MVP: `Виктор`, `Владимир`, `Елена`. LLM parsing fallback and XLSX export are explicitly deferred.

## D-029: Calendar missing-date recovery uses inline date picker in MVP; Mini App is deep backlog

- **Status:** Accepted
- **Decision:** Для черновиков календарных событий с `missing_start_at` (например, отсутствуют дата/время) MVP-путь восстановления выполняется через inline date picker внутри Telegram-чата (inline keyboard + callbacks), без отдельного frontend.
- **Decision:** Базовый MVP-flow: пользователь видит non-confirmable preview (`start_at: —`) и кнопку `📅 Выбрать дату`; после выбора даты бот запрашивает время текстом в формате `HH:MM`; затем обновляет `start_at` и показывает confirmable preview с `✅ Создать событие` / `⏱ Длительность` / `Edit` / `Cancel` (callback подтверждения остаётся `draft:confirm`).
- **Decision:** Scope MVP picker-а ограничен: выбирается только дата; время вводится текстом после выбора даты; picker не создаёт событие в Google Calendar; picker не заменяет `✅ Создать событие`; full inline time-picker не входит в first pass; Telegram Web App / Mini App не входит в near-term MVP.
- **Decision:** High-level state/callback concept фиксируется так: `missing_start_at` → click `📅 Выбрать дату` → `editing_field=start_date` (или эквивалент) → `calendar_picker:date:YYYY-MM-DD` callback → pending selected date сохраняется в state/metadata → `editing_field=start_time` → пользователь вводит `HH:MM` → `start_at = selected_date + time + user_timezone` → `editing_field` очищается → preview обновляется.
- **Decision:** Допустимая callback naming-схема (рабочий пример): `calendar_picker:open`, `calendar_picker:prev:YYYY-MM`, `calendar_picker:next:YYYY-MM`, `calendar_picker:date:YYYY-MM-DD`.
- **Decision:** Guardrails: picker никогда не пишет в Google Calendar; `✅ Создать событие` (callback `draft:confirm`) остаётся единственным write-path; picker работает только при наличии pending draft; stale callbacks завершаются безопасно без записи; `Cancel` очищает draft и picker-state; прямой `/edit` и прямое текстовое создание черновика продолжают работать.
- **Decision:** Telegram Web App / Mini App calendar UI фиксируется как deep backlog (возможен для richer calendar UI, combined date/time picker, dashboard/расширенного Smart Life UI), но не включается в текущий MVP из-за отдельного frontend, hosting, Telegram init-data validation/security review и отдельного deploy pipeline.
- **Rationale:** Inline picker в Telegram покрывает ближайшую UX-боль `missing_start_at` с минимальной технической сложностью и без расширения runtime/deploy perimeter. Mini App сохраняется как стратегическое направление, но сознательно не смешивается с near-term MVP.

## D-030: Offline-first direction for cashback syncable clients (PWA/Mini App), without blocking Telegram MVP

- **Status:** Accepted
- **Decision:** Зафиксировать offline-first как важное future product direction для cashback-сценариев (особенно для checkout-контекста с нестабильным/подавленным интернетом): будущий клиент (PWA / Telegram Mini App / web client) должен уметь работать с локальным кэшем/БД на устройстве, выполнять lookup офлайн, складывать локальные изменения в очередь (`pending_sync`) и синхронизировать их после восстановления сети.
- **Decision:** Для браузерного офлайн-хранилища целевой практический baseline — IndexedDB (или эквивалентная локальная БД), а не только `localStorage`; PWA app shell caching рассматривается как целевой механизм офлайн-запуска.
- **Decision:** Для будущей sync-модели необходимо планировать стабильный публичный UUID-идентификатор (`record_id`/`public_id`) для syncable сущностей (например, cashback records), сохраняя внутренние DB primary keys при необходимости. Офлайн-клиент должен иметь возможность генерировать UUID локально до первого контакта с сервером.
- **Decision:** Будущая синхронизация должна опираться на UUID + `updated_at`/version metadata, а не на одни лишь server-assigned sequential integer IDs как внешнюю identity-опору.
- **Decision:** В текущем docs PR schema/runtime изменения не вносятся; conflict-resolution policy (LWW vs manual), per-user/per-device sync metadata, delete/soft-delete sync semantics, local data encryption/security и auth model остаются future work.
- **Decision:** Offline-first является сильным аргументом в пользу PWA/Telegram Mini App до native APK; при этом Telegram MVP не блокируется и продолжает развиваться отдельно.
- **Rationale:** Checkout-use-case для cashback критичен к latency/availability. Offline-first снижает зависимость от сети и повышает практическую полезность продукта, не расширяя текущий MVP runtime scope.

## D-031: Cashback XLSX export is a future visual monthly report, not primary checkout UX

- **Status:** Accepted
- **Decision:** XLSX export для cashback фиксируется как future work / nice-to-have reporting feature, не как основной operational checkout UX.
- **Decision:** Основной рабочий cashback UX остаётся внутри Telegram bot в real-time lookup режиме: пользователь отправляет категорию (например, `Супермаркеты`) и сразу получает лучшие варианты карт/банков/% за текущий месяц.
- **Decision:** Назначение future XLSX export: визуальный monthly overview, review/check внесённых категорий, family sharing/manual inspection и lightweight backup/reporting view.
- **Decision:** Future UX path (концептуально): `💳 Кэшбек` → `📤 Выгрузить таблицу` → выбор месяца → bot отправляет форматированный `.xlsx`; при отсутствии данных возвращается явный ответ вида `За май 2026 кэшбек-категорий пока нет.`
- **Decision:** Рекомендуемая структура файла: sheet `Кэшбек — <месяц YYYY>`, колонки `Категория | Владелец | Банк | Кэшбек % | Месяц | Обновлено`, сортировка `Категория → Кэшбек % (desc) → Владелец → Банк`.
- **Decision:** Рекомендуемые formatting requirements: title/header по выбранному месяцу, bold headers, frozen header row, autofilter, readable column widths, numeric/percentage formatting for cashback percent where practical, и базовые визуальные разделители/группировка категорий при простой реализации.
- **Decision:** Архитектурно это future read-only use-case `ExportCashbackCategoriesUseCase` с потоком `SQLite query by target_month → build formatted .xlsx → Telegram sends document`.
- **Decision:** Guardrails: export read-only, не мутирует cashback records, использует существующие structured repositories/use-cases, не требует LLM и не требует внешних spreadsheet сервисов.
- **Rationale:** XLSX полезен как отчет/архив/совместный просмотр, но решение “какой картой платить сейчас” должно оставаться мгновенным и простым внутри Telegram-текста.

## D-032: Smart Life Ops remains Telegram-first now; backend stays transport-agnostic for future FastAPI/PWA/Mini App

- **Status:** Accepted
- **Decision:** Текущая продуктовая стратегия остаётся Telegram-first: Telegram — единственный active runtime transport в MVP.
- **Decision:** Архитектурный guardrail: Telegram остаётся transport adapter, а не владельцем бизнес-логики; domain/application/storage слои сохраняются transport-independent и JSON-friendly где практически применимо.
- **Decision:** Future evolution path фиксируется как: `Telegram bot MVP → FastAPI REST adapter later → PWA / Telegram Mini App frontend later → APK/native wrapper deep backlog`.
- **Decision:** Python backend может оставаться основным продуктовым backend при сохранении чистых слоёв; будущий FastAPI adapter должен вызывать те же use-cases, что и Telegram transport.
- **Decision:** PWA/Telegram Mini App рассматриваются как более рациональный first frontend target относительно APK/native, т.к. один web frontend может работать и в Telegram-контуре, и в обычном mobile browser.
- **Decision:** Native APK/wrapper/React Native/Flutter остаются deep backlog из-за дополнительной Android build/signing/distribution overhead.
- **Decision:** No-code builders (например, Tilda/Webflow и аналоги) допустимы для landing/marketing страниц, но не рассматриваются как платформа для основного динамического приложения (auth, state, cashback data, calendar/OAuth flows, exports, offline sync).
- **Decision:** D-030 задаёт offline-first направление для будущих клиентов; текущий D-032 фиксирует более широкую backend/frontend/transport стратегию и не меняет текущий MVP scope.
- **Rationale:** Такой порядок эволюции снижает delivery/ops-риск, переиспользует существующий Python use-case слой и не блокирует текущую Telegram-ценность продукта.


## D-033: OAuth Sprint 6 open implementation decisions

- **Status:** Pending
- **Decision scope:** Перед runtime-реализацией `oauth_user_mode` нужно зафиксировать набор операционных и security решений.
- **Open items:**
  - token encryption at rest и key-management strategy (host key vs KMS, rotation policy);
  - callback hosting approach (shared process vs separate service/adapter);
  - OAuth state/CSRF strategy (state format, TTL, one-time usage, storage location);
  - final redirect URI/domain choice for production and staging;
  - local development OAuth testing approach (tunnel/staging callback/other);
  - coexistence policy `oauth_user_mode` vs `service_account_shared_calendar_mode` (per deployment only vs per-user mixed operation).
- **Rationale:** Эти решения критичны для безопасного production rollout и должны быть явно приняты, а не подразумеваться по умолчанию.

## D-034: Cashback screenshot parser — Vision LLM vs OCR and privacy policy

- **Status:** Pending
- **Decision scope:** Перед любой runtime-реализацией screenshot parsing для cashback нужно принять архитектурные/продуктовые/security решения.
- **Open items:**
  - Vision LLM vs classic OCR as primary extraction strategy;
  - provider/model selection и fallback strategy;
  - ephemeral processing vs temporary/persistent screenshot storage;
  - retention policy для image/payload-derived artifacts;
  - redaction/logging policy (включая запрет raw screenshot logging);
  - cost/latency budgets и runtime limits;
  - prompt-injection/visual-jailbreak risk handling для untrusted screenshots;
  - extraction-quality evaluation protocol до production rollout.
- **Rationale:** Скриншоты банковских приложений несут privacy и quality risks; без явных решений feature не должен переходить из backlog в implementation.
