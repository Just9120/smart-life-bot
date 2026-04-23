# Deployment Foundation — Smart Life Ops Bot

## 1. Source of truth

- GitHub-репозиторий — канонический источник кода и документации.
- Основной delivery flow построен на ветках и pull request.

## 2. CI/CD baseline

- Для CI (и в дальнейшем расширения в CD) используется GitHub Actions.
- Начальный CI проверяет настройку Python-окружения и выполнение тестов.

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

## 7. Ограничения текущего этапа

Этот документ — только foundation. Финальный production playbook (rollout, rollback, monitoring, backups, incident steps) намеренно отложен на более поздний этап.
