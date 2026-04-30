# PRD — Smart Life Ops Bot MVP

## 1. Продукт

- **Название проекта:** Smart Life Ops Bot.
- **Основной канал ввода:** Telegram-бот.
- **Целевой результат MVP:** надежное создание событий Google Calendar из естественных сообщений пользователя с обязательным подтверждением перед записью.

## 2. Базовый пользовательский сценарий

`message → parsing → preview → explicit edit controls → confirm / cancel → create event`

Событие в Google Calendar создается только после явного **Confirm**.

## 3. Текущий UX MVP (Telegram draft flow + navigation direction)

1. Пользователь отправляет текст.
2. Парсер извлекает базовые сущности (например, title/start time), формирует draft и preview.
3. В preview доступны явные inline-действия редактирования.
4. Пользователь подтверждает (Confirm) или отменяет (Cancel).
5. Только после Confirm выполняется запись в Google Calendar.

Важно:
- обычный free-text не должен тихо менять duration/reminders;
- управление длительностью выполняется через `⏱ Длительность`;
- в текущем runtime (`⚡ Быстрый режим`, technical: `service_account_shared_calendar_mode`) кастомные reminders не считаются надежно поддерживаемой user-visible фичей;
- reminders должны быть capability-gated по calendar mode и включаться как user-visible feature только в будущем `🔐 Личный Google Calendar` (technical: `oauth_user_mode`) после реализации и проверки.

### 3.1 Telegram navigation model (target UX direction)

Telegram UX фиксируется как двухуровневая навигация:

1. **Native Telegram command menu** (кнопка `Menu`) для глобальных команд: `/start`, `/settings`, future `/help`.
2. **Footer feature menu** (persistent reply keyboard после `/start`) для продуктовых разделов, начиная с `📅 Календарь`.

Inline preview buttons остаются только для действий с текущим draft (Confirm / `⏱ Длительность` / Edit / Cancel + future reminder controls только при поддерживаемом режиме календаря).



### 3.3 Missing-date recovery (MVP near-term)

Если draft сформирован без даты/времени (`start_at: —`), в preview показывается явный recovery path:

- preview остаётся non-confirmable;
- доступны кнопки `📅 Выбрать дату`, `✏️ Edit`, `❌ Cancel`;
- по `📅 Выбрать дату` бот показывает inline month grid;
- после выбора даты бот запрашивает время текстом в формате `HH:MM`;
- после валидного времени draft получает `start_at` и preview снова показывается уже в confirmable состоянии (`Confirm` / `⏱ Длительность` / `Edit` / `Cancel`).

Ограничения этого MVP-шага:
- inline picker выбирает только дату;
- full inline time-picker не входит в first pass;
- picker не создаёт событие в календаре и не заменяет `Confirm`;
- Telegram Web App / Mini App календарный UI — deep backlog, не near-term MVP.

### 3.2 Calendar menu split (planned)

В разделе `📅 Календарь` планируется выбор режима:

- `⚡ Быстрый режим` — текущий рабочий путь в shared calendar через service account.
- `🔐 Личный Google Calendar` — будущий OAuth 2.0 user-authenticated путь.
- Для будущего OAuth reminder UX используется multi-select popup presets (один или несколько одновременно, например `10 минут + 1 час`) через checkbox-style pattern с действием `Применить`; email reminders не используются.

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
