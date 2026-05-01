# VPS Smoke Runbook (Manual First Test)

> **Role:** Canonical source for manual operator smoke checks after deploy. Automated regression strategy and CI test levels are maintained in [Testing](TESTING.md).

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

## 5) Stop/remove service container before rebuild (stale-runtime guard)

```bash
cd /opt/smart-life-bot
docker compose stop smart-life-bot || true
docker compose rm -f smart-life-bot || true
```

Этот шаг затрагивает только сервис `smart-life-bot` текущего compose-проекта и не останавливает/не удаляет чужие контейнеры.

## 6) Build image (fresh code marker)

```bash
cd /opt/smart-life-bot
host_commit="$(git rev-parse --short HEAD)"
docker compose build --no-cache --pull --build-arg APP_GIT_SHA="$host_commit" smart-life-bot
```

Compose service uses explicit local image tag `smart-life-bot:local`. Build embeds safe marker `SMART_LIFE_BOT_BUILD_SHA=$host_commit` inside image so runtime verification can prove container code matches current `main` commit.

## 7) Preflight (обязательный шаг перед polling)

```bash
docker compose run --rm -T --no-deps smart-life-bot python -m smart_life_bot.runtime.preflight < /dev/null
```

Ожидаемое поведение preflight:
- запускается с `-T` и detached stdin (`< /dev/null`), чтобы команда не могла поглотить stdin при запуске из SSH heredoc (как в GitHub Actions deploy workflow);
- валидирует settings, timezone, SQLite и runtime composition;
- **не** запускает polling;
- **не** делает вызовы Telegram API / Google API;
- **не** печатает secrets.

## 8) Start polling runtime

```bash
docker compose up -d --force-recreate --no-deps --no-build smart-life-bot
```

Одновременно должен работать только один polling consumer.

## 9) Logs

```bash
docker compose logs -f smart-life-bot
```

## 10) Stop runtime

```bash
docker compose stop smart-life-bot
# или

docker compose down  # только из /opt/smart-life-bot: затрагивает только compose-проект этого репозитория
```

## 11) Telegram smoke scenarios

### 10.0 Deploy freshness / runtime identity (обязательно перед Telegram checks)
1. Убедитесь, что деплой выполнен из актуального `main` (`git rev-parse --short HEAD`).
2. Сравните previous/new container ID и previous/new running image ID в deploy logs.
3. Убедитесь, что контейнер пересоздан (`docker compose ps smart-life-bot`) и запущен после последнего rebuild.
4. Проверьте build marker внутри runtime (`SMART_LIFE_BOT_BUILD_SHA`) и его равенство текущему host commit.
5. Проверьте, что runtime импортирует актуальные cashback callback markers (`cashback:list:month:`, `cashback:delete:request:`, `cashback:delete:confirm:`, `cashback:delete:cancel:`, `cashback:list:owner:`, `cashback:list:owner-current:`, `cashback:transition:select:`, `cashback:transition:cancel`).
6. Только после этих проверок переходите к Telegram smoke-сценариям.

### 10.1 Happy path (минимум)
1. Отправьте `/start`.
2. Отправьте `Тест завтра в 15:00`.
3. В preview ожидайте `end_at: —` и кнопки draft-level действий (`⏱ Длительность`, Confirm/Edit/Cancel). Если reminder controls скрыты в текущем service-account режиме — это корректно.
4. Отправьте `Тест завтра в 15:00 длительность 20 минут` и проверьте, что `end_at` не заполнился из free-text.
5. Нажмите `⏱ Длительность` и задайте `20` → `end_at` должен стать `start_at + 20 минут`.
6. Нажмите **Confirm**.
7. Проверьте success-ответ и появление события в Google Calendar.
8. Не используйте текущий service-account smoke как проверку user-visible custom reminders: по продуктовой политике это future OAuth-only capability.

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

### 10.6 Focused Telegram UX smoke (calendar + cashback)
1. Отправьте `/start` и проверьте явный выбор режима: `Выбери режим: 📅 Календарь или 💳 Кэшбек.`
2. Нажмите `📅 Календарь` и проверьте ответ с текущим режимом: `Текущий режим: 📅 Календарь`.
3. Отправьте календарный free-text и проверьте новый preview draft-copy.
4. Для текста без даты/времени проверьте non-confirmable preview + кнопку `📅 Выбрать дату`.
5. Пройдите `📅 Выбрать дату` → введите `HH:MM` → убедитесь, что событие не создаётся до явного Confirm.
6. Нажмите `💳 Кэшбек` и проверьте ответ с текущим режимом: `Текущий режим: 💳 Кэшбек`.
7. Проверьте явные действия в меню cashback: `📋 Активные категории`, `➕ Добавить категорию`, `🔎 Найти категорию`.
8. Нажмите `➕ Добавить категорию` и проверьте, что callback-действие работает в реальном Telegram (не только transport tests).
9. Нажмите `🔎 Найти категорию` и проверьте, что callback-действие работает в реальном Telegram (не только transport tests).
10. В режиме `💳 Кэшбек` отправьте plain text категории и проверьте default query/search routing.
11. Нажмите `📋 Активные категории` и проверьте видимую нумерацию строк `1.`, `2.` (без `#1`, `#2`).
12. Проверьте, что кнопки Edit/Delete применяются к тем же видимым номерам строк.
13. Проверьте owner reset: `Все` / `✅ Все` корректно снимает фильтр владельца.
14. Переключите режимы `📅 Календарь` ↔ `💳 Кэшбек` и проверьте, что несовместимые pending-состояния очищаются.
15. Data caution (production): Telegram smoke в `💳 Кэшбек` пишет в реальную persisted SQLite DB. Используйте реалистичные записи и удаляйте тестовые через UI (Edit/Delete); не выполняйте destructive DB cleanup в рамках smoke.

## 12) Docker isolation notes

- Не выполняйте глобальные Docker cleanup-команды (`docker system prune`, `docker rm` без фильтра и т.п.) в рамках этого smoke-runbook.
- Используйте только service-scoped команды (`smart-life-bot`) из директории `/opt/smart-life-bot`.
- `docker compose down` допустим только в директории этого репозитория и влияет только на compose-проект Smart Life Ops Bot.

## 13) Troubleshooting

- Docker не установлен / сервис не запущен.
- Compose plugin отсутствует (`docker compose version`).
- Контейнер завершается сразу: смотрите `docker compose logs smart-life-bot`.
- `.env` не загружен: проверьте наличие файла и переменных.
- Mismatch пути `GOOGLE_SERVICE_ACCOUNT_JSON` и mounted file.
- Нет прав на `./data` для SQLite.
- Polling уже запущен в другом контейнере/сессии (duplicate consumer).
- `Event creation failed` после Confirm: проверьте sharing calendar, calendar ID и service account key.


### 13.1 Stale runtime diagnostics (manual commands, safe)

```bash
cd /opt/smart-life-bot
git branch --show-current
git rev-parse HEAD
git rev-parse --short HEAD
docker compose version
docker compose ps smart-life-bot
container_id="$(docker compose ps -q smart-life-bot)"
docker inspect --format='{{.Id}} {{.Image}} {{.Created}} {{.State.Status}}' "$container_id"
docker image inspect smart-life-bot:local --format='{{.Id}}'
docker compose exec -T smart-life-bot python - <<'PY'
import os
from smart_life_bot.bot.telegram_transport import (
    CALLBACK_CASHBACK_LIST_MONTH_PREFIX,
    CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX,
    CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX,
    CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX,
    CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX,
    CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX,
    CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX,
    CALLBACK_CASHBACK_TRANSITION_CANCEL,
)
print('SMART_LIFE_BOT_BUILD_SHA=', os.environ.get('SMART_LIFE_BOT_BUILD_SHA', 'unknown'))
print('CALLBACK_CASHBACK_LIST_MONTH_PREFIX=', CALLBACK_CASHBACK_LIST_MONTH_PREFIX)
print('CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX=', CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX)
print('CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX=', CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX)
print('CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX=', CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX)
print('CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX=', CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX)
print('CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX=', CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX)
print('CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX=', CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX)
print('CALLBACK_CASHBACK_TRANSITION_CANCEL=', CALLBACK_CASHBACK_TRANSITION_CANCEL)
PY
```

Interpretation:
- на хосте может существовать старый образ `smart-life-bot-smart-life-bot:latest`; это не критерий валидности деплоя;
- running container image ID must equal `docker image inspect smart-life-bot:local` ID;
- `SMART_LIFE_BOT_BUILD_SHA` must equal `git rev-parse --short HEAD`;
- cashback callback markers must match expected latest literals;
- if any mismatch exists, Telegram smoke is stale and invalid until redeploy is fixed.

### 13.2 Duplicate polling consumer diagnostics (read-only)

```bash
docker compose ls
docker ps -a --format '{{.ID}}	{{.Image}}	{{.Names}}	{{.Status}}' | awk 'tolower($0) ~ /smart-life|smart_life|telegram|bot/'
ps aux | awk 'tolower($0) ~ /smart_life_bot|telegram_polling|smart-life-bot/'
```

Do not stop/remove unrelated containers or processes during diagnostics.

## 14) Smoke result checklist

- [ ] image build passed
- [ ] preflight passed
- [ ] polling started
- [ ] `/start` works and footer menu shows `📅 Календарь` + `💳 Кэшбек`
- [ ] `/start` показывает явный выбор режима (`📅 Календарь` / `💳 Кэшбек`)
- [ ] `📅 Календарь` устанавливает active mode и показывает `Текущий режим: 📅 Календарь`
- [ ] calendar free-text показывает актуальный draft preview copy
- [ ] missing-date preview non-confirmable и содержит `📅 Выбрать дату`
- [ ] calendar event не создаётся до явного Confirm
- [ ] `💳 Кэшбек` устанавливает active mode и показывает `Текущий режим: 💳 Кэшбек`
- [ ] меню cashback содержит `📋 Активные категории` / `➕ Добавить категорию` / `🔎 Найти категорию`
- [ ] `➕ Добавить категорию` callback работает в реальном Telegram
- [ ] `🔎 Найти категорию` callback работает в реальном Telegram
- [ ] plain text в режиме cashback идёт в query/search path по умолчанию
- [ ] `📋 Активные категории` показывает нумерацию `1.`, `2.` (без `#1`, `#2`)
- [ ] кнопки edit/delete соответствуют видимым номерам строк
- [ ] owner reset `Все` / `✅ Все` снимает фильтр владельца
- [ ] переключение режимов очищает несовместимые pending-состояния
- [ ] тестовые cashback-записи удалены через UI (без destructive DB cleanup)
- [ ] Edit path works
- [ ] Cancel path creates no event
- [ ] non-confirmable draft hides Confirm
- [ ] в service-account режиме reminder controls не обязательны и не проверяются как рабочая user-visible фича
- [ ] polling stopped

## 15) Связь с manual GitHub Actions deploy

После успешного ручного smoke на VPS деплой можно запускать и через GitHub Actions workflow `Deploy VPS` (manual `workflow_dispatch`).

Важно:
- workflow использует только SSH-доступ к VPS и не хранит runtime secrets приложения в GitHub Actions;
- runtime secrets остаются на VPS (`/opt/smart-life-bot/.env`, `/opt/smart-life-bot/secrets/service-account.json`);
- команды деплоя остаются service-scoped к `smart-life-bot` и не должны затрагивать другие Docker workload на хосте;
- для stale-поведения после deploy проверяйте host commit, previous/new container IDs, previous/new running image IDs, built service image ID и маркер `post_deploy_runtime_verification=ok`;
- не используйте `docker compose config` в shared/GitHub Actions логах, чтобы не раскрывать resolved env/secrets.
