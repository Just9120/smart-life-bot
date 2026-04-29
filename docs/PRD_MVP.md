# PRD — Smart Life Ops Bot MVP

## 1. Продукт

- **Название проекта:** Smart Life Ops Bot.
- **Основной канал ввода:** Telegram-бот.
- **Целевой результат MVP:** надежное создание событий Google Calendar из естественных сообщений пользователя с обязательным подтверждением перед записью.

## 2. Базовый пользовательский сценарий

`message → parsing → preview → explicit edit controls → confirm / cancel → create event`

Событие в Google Calendar создается только после явного **Confirm**.

## 3. Текущий UX MVP (Telegram draft flow)

1. Пользователь отправляет текст.
2. Парсер извлекает базовые сущности (например, title/start time), формирует draft и preview.
3. В preview доступны явные inline-действия редактирования.
4. Пользователь подтверждает (Confirm) или отменяет (Cancel).
5. Только после Confirm выполняется запись в Google Calendar.

Важно:
- обычный free-text не должен тихо менять duration/reminders;
- управление длительностью выполняется через `⏱ Длительность`;
- управление напоминаниями выполняется через `🔔 Уведомления`;
- меню напоминаний содержит только кастомные варианты: `10 минут`, `30 минут`, `1 час`, `2 часа`;
- в меню нет кнопки «default reminders»;
- если пользователь не выбрал напоминания, применяются неявные popup overrides на `60` и `30` минут (без email).

## 4. Scope MVP

- Telegram message → draft preview → confirm/cancel flow.
- Confirm-gated Google Calendar create.
- Явное редактирование duration/reminders через inline UI.
- Явная reminder policy: `reminders.useDefault=false`, popup-only overrides, без email reminders.
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
