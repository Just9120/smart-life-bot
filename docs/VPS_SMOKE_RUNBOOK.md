# VPS Smoke Runbook (Manual First Test)

Этот runbook фиксирует **первый ручной smoke-проход на VPS** через Docker Compose runtime.

## 1) Purpose и scope

Цель: вручную проверить целевой MVP flow:

`Telegram message → parsing → preview → confirm / edit / cancel → create Google Calendar event`

Границы runbook:
- только manual smoke на VPS;
- runtime через Docker Compose;
- VPS может параллельно запускать другие Docker workload;
- команды выполняются только из директории этого репозитория (`/opt/smart-life-bot` или ваш выбранный путь);
- без webhook;
- без OAuth callback/server flow;
- без полного production automation platform;
- без systemd unit.

## 2) Host prerequisites

На VPS должны быть установлены:
- Docker Engine;
- Docker Compose plugin (`docker compose`);
- Git.

Рабочий путь репозитория (пример): `/opt/smart-life-bot`.

## 3) Checkout / update repository

```bash
cd /opt/smart-life-bot
git fetch --all --prune
git checkout main
git pull --ff-only
```

## 4) Required env и secrets checklist

### 4.1 Создайте `.env`

```bash
cd /opt/smart-life-bot
cp .env.example .env
# заполните .env реальными значениями на VPS
```

Минимум для first smoke:

```env
TELEGRAM_BOT_TOKEN=<telegram_bot_token>
GOOGLE_AUTH_MODE=service_account_shared_calendar_mode
DATABASE_URL=sqlite:///./data/smart_life_bot.db
DEFAULT_TIMEZONE=Europe/Amsterdam
GOOGLE_SERVICE_ACCOUNT_JSON=/opt/smart-life-bot/secrets/service-account.json
GOOGLE_SHARED_CALENDAR_ID=<shared_calendar_id>
```

Важно:
- `.env` не коммитится;
- first smoke **не требует** LLM переменных;
- optional LLM переменные можно добавить позже при необходимости.

### 4.2 Host permissions для non-root container user

Контейнер запускается от UID/GID `10001:10001`. Для bind mounts подготовьте хост-пути под этот UID/GID:

```bash
mkdir -p /opt/smart-life-bot/data /opt/smart-life-bot/secrets
chown -R 10001:10001 /opt/smart-life-bot/data
chmod 700 /opt/smart-life-bot/secrets
```

### 4.3 Service account secret placement

1. Поместите JSON ключ на хосте по пути:

`/opt/smart-life-bot/secrets/service-account.json`

2. Выставьте владельца/права для чтения контейнером и без world-read:

```bash
chown 10001:10001 /opt/smart-life-bot/secrets/service-account.json
chmod 600 /opt/smart-life-bot/secrets/service-account.json
```

3. Проверьте, что календарь расшарен на service-account email.

Compose использует bind mount:
- host: `./secrets/service-account.json`
- container: `/opt/smart-life-bot/secrets/service-account.json` (read-only, `:ro`).

Это container-visible path convention для переменной `GOOGLE_SERVICE_ACCOUNT_JSON`; хостовый путь задаётся через bind mount в `compose.yaml`.

## 5) Build image

```bash
cd /opt/smart-life-bot
docker compose build smart-life-bot
```

## 6) Preflight (обязательный шаг перед polling)

```bash
docker compose run --rm smart-life-bot python -m smart_life_bot.runtime.preflight
```

Ожидаемое поведение preflight:
- валидирует settings, timezone, SQLite и runtime composition;
- **не** запускает polling;
- **не** делает вызовы Telegram API / Google API;
- **не** печатает secrets.

## 7) Start polling runtime

```bash
docker compose up -d smart-life-bot
```

Одновременно должен работать только один polling consumer.

## 8) Logs

```bash
docker compose logs -f smart-life-bot
```

## 9) Stop runtime

```bash
docker compose stop smart-life-bot
# или

docker compose down  # только из /opt/smart-life-bot: затрагивает только compose-проект этого репозитория
```

## 10) Telegram smoke scenarios

### 10.1 Happy path (минимум)
1. Отправьте `/start`.
2. Отправьте простой текст события с явной датой/временем.
3. Проверьте preview, parser diagnostics и кнопки Confirm/Edit/Cancel.
4. Нажмите **Confirm**.
5. Проверьте success-ответ и появление события в Google Calendar.

### 10.2 Edit path
1. Создайте preview.
2. Выполните `/edit title ...` или `/edit start_at ...`.
3. Проверьте обновлённый preview и Confirm.

### 10.3 Cancel path
1. Создайте preview.
2. Нажмите **Cancel**.
3. Убедитесь, что событие не создано.

### 10.4 Validation / non-confirmable draft
Проверьте кейсы, где Confirm скрыт:
- draft без `start_at`;
- invalid timezone;
- invalid time range.

### 10.5 Parser settings checks (`/settings`)
Проверьте parser modes (python/auto/llm) и безопасный fallback без LLM-конфига.

## 11) Docker isolation notes

- Не выполняйте глобальные Docker cleanup-команды (`docker system prune`, `docker rm` без фильтра и т.п.) в рамках этого smoke-runbook.
- Используйте только service-scoped команды (`smart-life-bot`) из директории `/opt/smart-life-bot`.
- `docker compose down` допустим только в директории этого репозитория и влияет только на compose-проект Smart Life Ops Bot.

## 12) Troubleshooting

- Docker не установлен / сервис не запущен.
- Compose plugin отсутствует (`docker compose version`).
- Контейнер завершается сразу: смотрите `docker compose logs smart-life-bot`.
- `.env` не загружен: проверьте наличие файла и переменных.
- Mismatch пути `GOOGLE_SERVICE_ACCOUNT_JSON` и mounted file.
- Нет прав на `./data` для SQLite.
- Polling уже запущен в другом контейнере/сессии.
- `Event creation failed` после Confirm: проверьте sharing calendar, calendar ID и service account key.

## 13) Smoke result checklist

- [ ] image build passed
- [ ] preflight passed
- [ ] polling started
- [ ] `/start` works
- [ ] preview works
- [ ] Confirm creates Google Calendar event
- [ ] Edit path works
- [ ] Cancel path creates no event
- [ ] non-confirmable draft hides Confirm
- [ ] polling stopped

## 14) Связь с manual GitHub Actions deploy

После успешного ручного smoke на VPS деплой можно запускать и через GitHub Actions workflow `Deploy VPS` (manual `workflow_dispatch`).

Важно:
- workflow использует только SSH-доступ к VPS и не хранит runtime secrets приложения в GitHub Actions;
- runtime secrets остаются на VPS (`/opt/smart-life-bot/.env`, `/opt/smart-life-bot/secrets/service-account.json`);
- команды деплоя остаются service-scoped к `smart-life-bot` и не должны затрагивать другие Docker workload на хосте.

