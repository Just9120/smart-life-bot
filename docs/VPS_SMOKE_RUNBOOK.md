# VPS Smoke Runbook (Manual First Test)

Этот runbook описывает **первый ручной smoke-проход на VPS** для сценария:

`Telegram message → preview → confirm → Google Calendar event`

Scope intentionally narrow:
- только ручной запуск;
- без systemd/Docker/CD;
- без webhook;
- без OAuth callback/server;
- без production automation.

## 1. Prerequisites

- VPS с Linux shell-доступом.
- Установлен Python 3.11+.
- Git установлен.
- Создан Telegram bot token (placeholder only в `.env`).
- Подготовлен Google service account для режима `service_account_shared_calendar_mode`.
- Включен Google Calendar API в проекте service account.

## 2. Repository checkout/update

```bash
cd /opt
# первый клон
git clone <your_repo_url> smart-life-bot
cd smart-life-bot

# последующие обновления
git fetch --all --prune
git checkout <target_branch>
git pull --ff-only
```

## 3. Python venv setup

```bash
cd /opt/smart-life-bot
python -m venv .venv
source .venv/bin/activate
```

## 4. Install package

```bash
pip install --upgrade pip
pip install -e .[dev]
```

## 5. Prepare `.env` safely

1. Создайте `.env` из шаблона:

```bash
cp .env.example .env
```

2. Заполните placeholders реальными значениями **только на VPS**.
3. Никогда не коммитьте `.env`.
4. Экспортируйте env перед запуском:

```bash
set -a
source .env
set +a
```

## 6. Prepare service account JSON file safely

Рекомендуемый путь — **файл на VPS**, а не raw JSON в переменной окружения.

- Храните JSON вне репозитория или в отдельной secrets-директории.
- Не коммитьте JSON-файл.
- Ограничьте права доступа:

```bash
mkdir -p /opt/smart-life-bot/secrets
chmod 700 /opt/smart-life-bot/secrets
chmod 600 /opt/smart-life-bot/secrets/service-account.json
```

Безопасность:
- не вставляйте raw private key в shell history, если можно избежать;
- используйте `GOOGLE_SERVICE_ACCOUNT_JSON` как filesystem path;
- в `.env` храните только путь, например `/opt/smart-life-bot/secrets/service-account.json`.

## 7. Share Google Calendar with service account email

1. Откройте целевой Google Calendar в браузере.
2. В настройках доступа расшарьте календарь на email service account.
3. Дайте права минимум на создание/редактирование событий.
4. Укажите соответствующий calendar id в `GOOGLE_SHARED_CALENDAR_ID`.

## 8. Run preflight

```bash
python -m smart_life_bot.runtime.preflight
```

Ожидание:
- preflight завершился успешно;
- проверены settings/timezone/SQLite/runtime composition;
- polling не стартует;
- Telegram/Google network calls не выполняются;
- секреты не печатаются в output.

## 9. Run Telegram polling manually

```bash
python -m smart_life_bot.bot.telegram_polling
```

Важно:
- это ручной smoke-run;
- держите сессию открытой на время теста;
- после smoke polling нужно остановить вручную.

## 10. Execute Telegram smoke scenario

В Telegram диалоге с ботом:

1. Отправьте `/start`.
2. Отправьте сообщение события (пример):
   - `завтра в 15:00 тестовый созвон на 30 минут`
3. Проверьте preview:
   - корректно распознан `title`;
   - корректно распознан `start_at`;
   - корректно распознан `end_at`;
   - корректная `timezone`;
   - присутствуют кнопки confirm/edit/cancel.
4. Нажмите **Confirm**.
5. Проверьте ответ бота:
   - есть `Event created successfully`;
   - присутствует ссылка на событие Google Calendar.

## 11. Verify Google Calendar event creation

- Откройте Google Calendar.
- Убедитесь, что событие появилось в правильной дате/времени.
- Проверьте title и длительность.
- При необходимости откройте ссылку из Telegram-ответа и сверьте карточку события.

## 12. Stop polling

Остановите процесс вручную (обычно `Ctrl+C` в активной shell-сессии).

## 13. Troubleshooting

- **Missing `TELEGRAM_BOT_TOKEN`**  
  Проверьте `.env`, затем заново `set -a; source .env; set +a`.

- **Invalid `GOOGLE_AUTH_MODE`**  
  Для первого VPS smoke используйте только `service_account_shared_calendar_mode`.

- **Missing `GOOGLE_SERVICE_ACCOUNT_JSON`**  
  Укажите путь к JSON-файлу в `.env`.

- **Service account JSON path does not exist**  
  Проверьте путь и права доступа (`chmod 600`).

- **Calendar not shared with service account email**  
  Расшарьте календарь в Google Calendar settings и повторите confirm.

- **Google Calendar API not enabled**  
  Включите API в Google Cloud project service account.

- **SQLite directory does not exist or is not writable**  
  Создайте директорию `data/` и проверьте права на запись для текущего пользователя.

- **Timezone invalid**  
  Установите корректный IANA timezone (например, `Europe/Amsterdam` или `UTC`).

- **Telegram polling already running somewhere else**  
  Остановите параллельный polling-инстанс; одновременно должен работать только один consumer.

- **Confirm returns `Event creation failed`**  
  Проверьте preflight output, calendar sharing, `GOOGLE_SHARED_CALENDAR_ID`, доступность Google API и путь к service account JSON.

## 14. Cleanup / safety notes

- После smoke удалите тестовое событие из календаря (optional cleanup).
- Остановите polling вручную.
- Деактивируйте venv при завершении:

```bash
deactivate
```

- Не храните secrets в git-tracked файлах.
- Не публикуйте token/json в issue tracker, PR comments или logs.
