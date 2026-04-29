# Deployment Foundation — Smart Life Ops Bot

## 1. Source of truth

- GitHub-репозиторий — канонический источник кода и документации.
- Основной delivery flow построен на ветках и pull request.

## 2. CI/CD baseline

- Для CI и CD используется GitHub Actions.
- CI workflow (`.github/workflows/ci.yml`) запускает Python-тесты на `push` и `pull_request`.
- Initial CD workflow (`.github/workflows/deploy.yml`) запускается только вручную через `workflow_dispatch` и деплоит `main` на VPS Docker runtime.

## 3. Целевое runtime-окружение

- Целевая среда деплоя: VPS в Contabo.
- Формат поставки в runtime: deployment на базе Docker.

## 4. Работа с секретами

- Secrets должны передаваться только через GitHub Secrets и/или переменные окружения сервера.
- Secrets не должны коммититься в файлы репозитория, примеры или документацию.

## 5. План по сети и hostname

- Планируемый production hostname: выделенный subdomain существующего домена через Cloudflare.
- Целевая OAuth-архитектура требует корректного HTTPS endpoint.

## 6. Примечания по деплою auth-mode

- Целевой режим: `oauth_user_mode`, требует защищенный внешний callback endpoint.
- Fallback-режим: `service_account_shared_calendar_mode`, может работать без OAuth и без домена в персональной конфигурации (например, long polling).

Fallback-режим операционно допустим для быстрого персонального запуска, но не является целевой архитектурой продукта.

## 7. Runtime foundation status

Репозиторий содержит минимальный Docker runtime foundation для VPS smoke:
- `Dockerfile` для runtime-образа бота;
- `compose.yaml` для запуска preflight/polling в контейнере с persistent SQLite и read-only mount service account JSON.

В scope этого foundation не входят webhook/CD/systemd/reverse proxy/TLS/production monitoring.

## 8. Manual CD workflow (initial guardrails)

Workflow: `Deploy VPS` (`.github/workflows/deploy.yml`)

- Trigger: только manual `workflow_dispatch` (без auto-deploy на `push`/`pull_request`).
- Required GitHub Secrets:
  - `VPS_HOST`
  - `VPS_USER`
  - `VPS_PORT` (обязательный; обычно `22`)
  - `VPS_SSH_PRIVATE_KEY`
- В workflow есть precheck обязательных секретов (`VPS_HOST`, `VPS_USER`, `VPS_PORT`, `VPS_SSH_PRIVATE_KEY`) с fail-fast до SSH шага.
- Runtime secrets не передаются через GitHub Actions для этого этапа: `TELEGRAM_BOT_TOKEN`, calendar/service account credentials и `.env` остаются на VPS в `/opt/smart-life-bot/.env` и `/opt/smart-life-bot/secrets/service-account.json`.

Сценарий деплоя строго scoped к проекту Smart Life Ops Bot:

1. `cd /opt/smart-life-bot`
2. `git fetch --all --prune`
3. `git checkout main`
4. `git pull --ff-only`
5. Проверка обязательных файлов: `.env`, `compose.yaml`, `Dockerfile`, `secrets/service-account.json`
6. `docker compose config`
7. `docker compose build smart-life-bot`
8. `docker compose run --rm smart-life-bot python -m smart_life_bot.runtime.preflight`
9. `docker compose up -d smart-life-bot`
10. `docker compose ps`
11. `docker compose logs --tail=100 smart-life-bot`

Ограничения безопасности:
- не выполняются `docker system prune` и другие global cleanup-команды;
- не выполняется остановка всех контейнеров;
- не выполняется удаление чужих images/volumes/networks;
- не используется `docker compose down` как default deploy strategy;
- обновляется только сервис `smart-life-bot`.

### SSH deploy key setup (short)

1. На VPS сгенерируйте отдельный deploy key (ed25519), например:
   - `ssh-keygen -t ed25519 -f ~/.ssh/smart-life-bot-deploy -C "smart-life-bot-deploy"`.
2. Добавьте публичный ключ в `~/.ssh/authorized_keys` пользователя, под которым идет деплой.
3. Добавьте приватный ключ (`~/.ssh/smart-life-bot-deploy`) в GitHub Secret `VPS_SSH_PRIVATE_KEY`.
4. Никогда не коммитьте и не вставляйте приватный ключ в документацию, логи, issues или chat.

### First-run checklist (GitHub Actions)

1. Убедитесь, что в GitHub Secrets заданы `VPS_HOST`, `VPS_USER`, `VPS_PORT` (обычно `22`) и `VPS_SSH_PRIVATE_KEY`.
2. Откройте GitHub → **Actions** → workflow **Deploy VPS**.
3. Нажмите **Run workflow** и выберите ветку `main`.
4. Дождитесь успешного выполнения precheck и deploy шагов.
5. Проверьте финальный вывод `docker compose ps` и `docker compose logs --tail=100 smart-life-bot`.

## 9. Ограничения текущего этапа

Это initial manual CD foundation, а не полный production rollout platform.

По-прежнему out of scope: полноценные rollback playbooks, production monitoring/alerting stack, backups/restore automation, auto-deploy на каждый push и расширенная release orchestration.
