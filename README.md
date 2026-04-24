# Smart Life Ops Bot

Smart Life Ops Bot — это Telegram-ассистент, сфокусированный на быстром и надежном добавлении событий в Google Calendar с обязательным подтверждением перед записью каждого события.

**Текущий статус:** runtime foundation phase 1 (зафиксированы модульный каркас и контракты).

## Назначение продукта (MVP)

- Канал ввода: Telegram-бот.
- Основной поток: message → parsing → preview → confirm / edit / cancel → create Google Calendar event.
- Приоритеты: надежность, прозрачность, управляемость, быстрый выход к полезному результату.

## Структура репозитория

- `docs/PRD_MVP.md` — краткие продуктовые требования MVP.
- `docs/ARCHITECTURE.md` — детальная архитектура Phase 1 (слои, зависимости, flow, границы).
- `docs/DEPLOYMENT.md` — базовые принципы деплоя и ограничения окружения.
- `docs/DECISIONS.md` — журнал архитектурных и технических решений в формате ADR-like.
- `docs/PHASE1_TECHNICAL_SPEC.md` — рабочая техническая спецификация Phase 1 для следующих PR.
- `docs/CONFIGURATION.md` — модель конфигурации и переменных окружения.
- `src/smart_life_bot/` — каркас Python-пакета с runtime foundation layer (config/domain/application/storage/auth/calendar/parsing/observability contracts).
- `tests/` — smoke-уровень тестов для foundation-слоя.
- `.github/workflows/ci.yml` — минимальный CI pipeline.

## Локальный запуск заглушки

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Важно: .env не загружается автоматически на текущем этапе.
# Экспортируйте переменные в shell перед запуском.
set -a; source .env; set +a
python -m smart_life_bot.main
python -m pytest
```

Текущая точка входа приложения намеренно оставлена как placeholder и пока не реализует Telegram handlers, интеграцию с Google Calendar, OAuth flow и FSM-логику.
