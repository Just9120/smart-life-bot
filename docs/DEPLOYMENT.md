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
- Runtime `.env` является статическим host-owned файлом на VPS: CD **не** генерирует, **не** загружает, **не** синхронизирует и **не** перезаписывает `/opt/smart-life-bot/.env`.
- Runtime секреты приложения (`TELEGRAM_BOT_TOKEN`, Anthropic key, Google service-account JSON и calendar runtime values) остаются на VPS и не переносятся в GitHub Actions Secrets.
- CD может проверять существование `.env`, но не должен печатать содержимое `.env` или resolved значения окружения из Docker Compose.
- Если приложению нужны новые env-переменные, PR обновляет `.env.example` и документацию; реальный `/opt/smart-life-bot/.env` оператор обновляет вручную.

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

## 8. Manual CD workflow (hardened guardrails)

Workflow: `Deploy VPS` (`.github/workflows/deploy.yml`)

- Trigger: только manual `workflow_dispatch` (без auto-deploy на `push`/`pull_request`).
- Permissions: минимальные, только `contents: read`.
- Concurrency guard: `smart-life-bot-vps-deploy`, `cancel-in-progress: false`.
- Job timeout: `timeout-minutes: 20`.
- Required GitHub Secrets:
  - `DEPLOY_HOST` (VPS host/IP, текущий: `167.86.68.98`)
  - `DEPLOY_USER` (deploy user, текущий: `root`)
  - `DEPLOY_SSH_KEY` (private SSH deploy key)
  - `DEPLOY_KNOWN_HOSTS` (SSH known_hosts entry для проверки хоста)
- SSH порт для текущей схемы фиксирован как default `22` и не требует отдельного GitHub Secret.
- В workflow есть precheck обязательных секретов (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`) с fail-fast до SSH шага.
- Runtime secrets не передаются через GitHub Actions для этого этапа: `TELEGRAM_BOT_TOKEN`, calendar/service account credentials и `.env` остаются на VPS в `/opt/smart-life-bot/.env` и `/opt/smart-life-bot/secrets/service-account.json`.

Сценарий деплоя строго scoped к проекту Smart Life Ops Bot:

1. `cd /opt/smart-life-bot`
2. `git fetch --all --prune`
3. `git checkout main`
4. `git pull --ff-only`
5. Проверка обязательных файлов: `.env`, `compose.yaml`, `Dockerfile`, `secrets/service-account.json`
6. Capture previous runtime identity (`previous_container_id`, `previous_running_image_id`) before deploy for safe comparison.
7. `host_commit="$(git rev-parse --short HEAD)"` + no-cache service-scoped rebuild: `docker compose build --no-cache --pull --build-arg APP_GIT_SHA="$host_commit" smart-life-bot` (compose service uses explicit local tag `smart-life-bot:local`).
8. `built_service_image_id` diagnostics are read from the explicit local tag: `docker image inspect smart-life-bot:local --format='{{.Id}}'` (safe even when previous container references a stale/removed image).
9. `docker compose run --rm -T --no-deps smart-life-bot python -m smart_life_bot.runtime.preflight < /dev/null` (preflight now always runs against freshly rebuilt image and must run with detached stdin because deploy executes through SSH heredoc).
10. Перед запуском сервиса workflow явно останавливает и удаляет только целевой контейнер: `docker compose stop smart-life-bot || true` и `docker compose rm -f smart-life-bot || true` (без затрагивания других контейнеров).
11. Деплой поднимает только целевой сервис без rebuild: `docker compose up -d --force-recreate --no-deps --no-build smart-life-bot`
12. Post-deploy diagnostics (safe): workflow `GITHUB_REF`/`GITHUB_SHA`, remote `pwd`, remote branch, full/short remote HEAD, `docker compose version`, `docker compose ps smart-life-bot`, previous/new container ID, previous/new running image ID, built service image ID, new container created time/status.
13. Stale-runtime guardrails (fail-fast):
   - deploy fails if `docker compose ps -q smart-life-bot` is empty after recreate;
   - deploy fails if `new_container_id == previous_container_id` (when previous exists);
   - deploy fails if `new_running_image_id != built_service_image_id`;
   - deploy fails if container env marker `SMART_LIFE_BOT_BUILD_SHA` does not match remote host commit.
14. Post-deploy runtime verification inside container (`docker compose exec -T smart-life-bot ...`) проверяет build commit marker и ожидаемые кодовые признаки текущей версии, включая cashback month/delete/owner-filter/transition callback markers (`CALLBACK_CASHBACK_LIST_MONTH_PREFIX`, `CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX`, `CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX`, `CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX`, `CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX`, `CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX`, `CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX`, `CALLBACK_CASHBACK_TRANSITION_CANCEL`).
15. Duplicate polling diagnostics (safe, read-only): `docker compose ls`, filtered `docker ps -a`, filtered `ps aux` for `smart_life_bot`/`telegram_polling`/`smart-life-bot`.
16. `docker compose logs --tail=100 smart-life-bot`


Ограничения по логированию deploy workflow:
- `docker compose config` не используется в GitHub Actions deploy-логах, потому что команда может выводить resolved env-значения (включая runtime secrets).
- В deploy-логах запрещено печатать содержимое `.env` и любые resolved runtime secrets.
- Если потребуется валидация новых env-переменных, сначала обновляйте `.env.example` + docs в PR, затем вручную обновляйте реальный `.env` на VPS.

Если после деплоя поведение бота выглядит stale, smoke-проверка НЕ считается валидной, пока не подтверждены runtime identity и feature markers. Проверьте в логах workflow:
- workflow ref/sha (`GITHUB_REF`, `GITHUB_SHA`) и remote repo identity (`remote_git_branch`, `remote_git_head`, `remote_git_head_short`);
- `docker compose ps smart-life-bot` (container state/age) + `new_container_created_at`/`new_container_status`;
- `previous_container_id` / `new_container_id` (должны отличаться при наличии предыдущего контейнера);
- `previous_running_image_id` / `new_running_image_id` / `built_service_image_id` (`new_running_image_id` должен совпадать с built image);
- на хосте может существовать старый образ/тег `smart-life-bot-smart-life-bot:latest`; это не критерий свежести runtime;
- валидный критерий freshness: `new_running_image_id` контейнера должен совпадать с image ID `smart-life-bot:local`;
- `SMART_LIFE_BOT_BUILD_SHA == host_git_commit`;
- `post_deploy_runtime_verification=ok` (включая cashback month/delete/owner-filter/transition callback markers);
- duplicate polling diagnostics: `docker compose ls`, filtered `docker ps -a`, filtered `ps aux`.

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
3. Добавьте приватный ключ (`~/.ssh/smart-life-bot-deploy`) в GitHub Secret `DEPLOY_SSH_KEY`.
4. Никогда не коммитьте и не вставляйте приватный ключ в документацию, логи, issues или chat.

### Known hosts setup (required)

1. С trusted admin-машины снимите host key, например:
   - `ssh-keyscan -p 22 167.86.68.98`
2. Сохраните результат в GitHub Secret `DEPLOY_KNOWN_HOSTS`.
3. Важно: `DEPLOY_KNOWN_HOSTS` — это known_hosts entry для проверки сервера, это **не** приватный SSH ключ.

### First-run checklist (GitHub Actions)

1. Убедитесь, что на VPS существует `/opt/smart-life-bot`.
2. Убедитесь, что на VPS существует `/opt/smart-life-bot/.env`.
3. Убедитесь, что на VPS существует `/opt/smart-life-bot/secrets/service-account.json`.
4. Убедитесь, что Docker Compose runtime уже прошёл ручной smoke.
5. Убедитесь, что в GitHub Secrets заданы:
   - `DEPLOY_HOST`
   - `DEPLOY_USER`
   - `DEPLOY_SSH_KEY`
   - `DEPLOY_KNOWN_HOSTS`
6. Откройте GitHub → **Actions** → workflow **Deploy VPS**.
7. Нажмите **Run workflow** и выберите ветку `main`.
8. Проверьте workflow logs.
9. Проверьте финальный вывод `docker compose ps` и дальнейшее поведение бота после деплоя.

### Failure handling (quick guide)

- Если precheck упал: отсутствует один или несколько обязательных secrets.
- Если SSH шаг упал: проверьте `DEPLOY_HOST`/`DEPLOY_USER`/`DEPLOY_SSH_KEY`, `authorized_keys` и корректность `DEPLOY_KNOWN_HOSTS`.
- Если `git pull --ff-only` упал: проверьте локальные изменения в `/opt/smart-life-bot` на VPS.
- Если Docker build/preflight упал: посмотрите workflow logs и повторите ту же команду вручную на VPS.
- Если бот не работает после деплоя: проверьте `docker compose logs --tail=100 smart-life-bot`.


## 9. Ограничения текущего этапа

Это initial manual CD foundation, а не полный production rollout platform.

По-прежнему out of scope: полноценные rollback playbooks, production monitoring/alerting stack, backups/restore automation, auto-deploy на каждый push и расширенная release orchestration.
