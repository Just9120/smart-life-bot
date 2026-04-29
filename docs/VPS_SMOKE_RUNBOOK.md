# VPS Smoke Runbook (Manual First Test)

Этот runbook фиксирует **первый ручной smoke-проход на VPS** после baseline-изменений валидации draft и pre-smoke hardening.

## 1) Purpose и scope

Цель: вручную проверить целевой MVP flow:

`Telegram message → parsing → preview → confirm / edit / cancel → create Google Calendar event`

Границы runbook:
- только manual smoke на VPS;
- без systemd/service manager;
- без Docker;
- без webhook;
- без OAuth callback/server flow;
- без CD/production automation;
- без изменения runtime-поведения.

## 2) Required env и secrets checklist

Используйте только placeholders (без реальных ключей в документах/коммитах).

### 2.1 Обязательный baseline для первого smoke

```env
TELEGRAM_BOT_TOKEN=<telegram_bot_token>
GOOGLE_AUTH_MODE=service_account_shared_calendar_mode
DATABASE_URL=sqlite:///./data/smart_life_bot.db
DEFAULT_TIMEZONE=Europe/Amsterdam
GOOGLE_SERVICE_ACCOUNT_JSON=/opt/smart-life-bot/secrets/service-account.json
GOOGLE_SHARED_CALENDAR_ID=<shared_calendar_id>
```

Поддерживаемые SQLite URL для runtime: `sqlite:///./data/smart_life_bot.db` (основной smoke-вариант) и `sqlite:///:memory:` (обычно для тестовых/временных запусков).

### 2.2 Optional LLM (не required для first smoke)

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<anthropic_api_key>
LLM_MODEL=claude-haiku-4-5-20251001
LLM_TIMEOUT_SECONDS=20
LLM_MAX_RETRIES=2
LLM_MAX_TOKENS=1000
```

Важно:
- first VPS smoke **не требует LLM**;
- Python parser mode должен работать без LLM-конфига;
- Auto mode должен оставаться Python-first с безопасным fallback без LLM;
- LLM mode при отсутствии LLM-конфига не должен ломать flow (ожидается безопасный fallback).

## 3) Safe service account setup

1. Создайте отдельную директорию для secrets (рекомендуется):

```bash
mkdir -p /opt/smart-life-bot/secrets
chmod 700 /opt/smart-life-bot/secrets
```

2. Разместите JSON ключ service account по безопасному пути (пример):
   - `/opt/smart-life-bot/secrets/service-account.json`

3. Выдайте минимально безопасные права на файл:

```bash
chmod 600 /opt/smart-life-bot/secrets/service-account.json
```

4. Убедитесь, что:
   - `.env` и service account JSON **не коммитятся** в Git;
   - целевой Google Calendar расшарен на service account email;
   - в GCP включен Google Calendar API;
   - в `.env` указан корректный `GOOGLE_SHARED_CALENDAR_ID` shared-календаря.

## 4) Checkout / update шаги

### 4.1 Если репозиторий отсутствует

```bash
cd /opt
git clone <your_repo_url> smart-life-bot
cd smart-life-bot
```

### 4.2 Если репозиторий уже есть

```bash
cd /opt/smart-life-bot
git fetch --all --prune
git checkout main
git pull --ff-only
```

### 4.3 Python окружение и установка

```bash
cd /opt/smart-life-bot
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]
cp .env.example .env
# заполните .env своими значениями на VPS
set -a
source .env
set +a
```

## 5) Preflight (обязательный шаг перед polling)

Запустите:

```bash
python -m smart_life_bot.runtime.preflight
```

Ожидаемое поведение preflight:
- валидирует settings, timezone, SQLite и runtime composition;
- **не** запускает polling;
- **не** делает вызовы Telegram API / Google API;
- **не** печатает secrets.

Если preflight упал — исправьте конфиг до запуска polling.

## 6) Manual polling step

Запустите polling отдельной командой:

```bash
python -m smart_life_bot.bot.telegram_polling
```

Правила smoke-сессии:
- держите shell-сессию открытой до завершения smoke;
- одновременно должен работать только один polling consumer;
- после smoke остановите процесс вручную (`Ctrl+C`).

## 7) Telegram smoke scenarios

Ниже — компактный manual checklist.

### 7.1 Happy path (минимум)

1. Отправьте `/start`.
2. Отправьте простой текст события с явной датой/временем.
3. Проверьте preview:
   - корректные поля события;
   - виден parser diagnostics блок (`mode/route/source/confidence`, при наличии — issues);
   - доступны кнопки Confirm / Edit / Cancel.
4. Нажмите **Confirm**.
5. Проверьте success-ответ бота.
6. Проверьте, что событие появилось в Google Calendar.
7. Если в ответе есть ссылка на событие — проверьте, что она открывает нужный event.

### 7.2 Edit path

1. Создайте preview обычным сообщением.
2. Выполните редактирование через существующий синтаксис команд, например:
   - `/edit title ...`
   - `/edit start_at ...`
3. Проверьте, что preview обновился.
4. Нажмите **Confirm**.
5. Проверьте, что в календарь записалась финальная (отредактированная) версия.

### 7.3 Cancel path

1. Создайте preview.
2. Нажмите **Cancel**.
3. Проверьте, что событие **не** создано в Google Calendar.
4. Если вручную попробовать stale/replayed Confirm для отменённого draft — действие должно завершаться безопасно (без создания события).

### 7.4 Validation / non-confirmable draft checks

Проверьте кейсы, где Confirm должен быть скрыт, а Edit/Cancel — доступны:
- draft без `start_at`;
- invalid timezone;
- invalid time range (`end_at < start_at` и/или смешанный aware/naive диапазон);
- malformed timezone вроде `/UTC` или `../UTC` не должен крашить preview и должен трактоваться как invalid timezone.

Если конкретный invalid draft сложно получить чисто через обычный Telegram parsing, зафиксируйте его как optional dev/operator check (не блокируйте весь smoke нереалистичным сценарием).

### 7.5 Parser settings checks (`/settings`)

Проверьте через `/settings`:
- отображаются parser modes;
- Python mode работает без LLM-переменных;
- Auto mode работает как Python-first без LLM-конфига;
- LLM mode без LLM-конфига отрабатывает безопасно (fallback), а при валидной LLM-конфигурации использует Claude.

## 8) Google Calendar verification

После Confirm проверьте в shared calendar:
- корректные дата/время;
- корректный заголовок;
- ожидаемая длительность (если есть `end_at`);
- событие создано именно в календаре из `GOOGLE_SHARED_CALENDAR_ID`.

После завершения smoke можно удалить тестовые события (optional cleanup).

## 9) Troubleshooting

- **Missing `TELEGRAM_BOT_TOKEN`**  
  Проверьте `.env` и повторите `set -a; source .env; set +a`.

- **Invalid `GOOGLE_AUTH_MODE`**  
  Для first smoke используйте `service_account_shared_calendar_mode`.

- **Missing `GOOGLE_SERVICE_ACCOUNT_JSON` / неверный путь**  
  Укажите корректный путь до JSON-файла и проверьте существование файла.

- **Некорректные права на service account JSON**  
  Проверьте доступность файла для текущего пользователя и ограничьте права (`chmod 600`).

- **Calendar не расшарен с service account**  
  Добавьте service account email в доступ календаря и повторите Confirm.

- **Missing/incorrect `GOOGLE_SHARED_CALENDAR_ID`**  
  Проверьте, что указан ID нужного shared calendar.

- **Google Calendar API not enabled**  
  Включите API в GCP-проекте service account.

- **SQLite path/permissions issue**  
  Проверьте `DATABASE_URL` и права на директорию `data/`.

- **Invalid timezone / missing tzdata**  
  Используйте валидную IANA timezone и проверьте наличие tzdata в системе.

- **Polling уже запущен в другом месте**  
  Оставьте только один активный polling consumer.

- **`Event creation failed` после Confirm**  
  Повторно проверьте preflight, calendar sharing, `GOOGLE_SHARED_CALENDAR_ID`, service account JSON и доступность Google API.

- **LLM не настроен**  
  Для first smoke это допустимо: используйте Python mode/Auto mode без обязательной LLM-конфигурации.

## 10) Smoke result checklist (копипаст в заметки)

- [ ] preflight passed
- [ ] polling started
- [ ] `/start` works
- [ ] preview works
- [ ] parser diagnostics visible
- [ ] Confirm creates Google Calendar event
- [ ] Edit path works
- [ ] Cancel path creates no event
- [ ] non-confirmable draft hides Confirm
- [ ] service account calendar permissions verified
- [ ] polling stopped
- [ ] test event cleaned up (if needed)
