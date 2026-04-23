# Smart Life Ops Bot

Smart Life Ops Bot — это Telegram-ассистент, сфокусированный на быстром и надежном добавлении событий в Google Calendar с обязательным подтверждением перед записью каждого события.

**Текущий статус:** bootstrap репозитория / foundation phase 1.

## Назначение продукта (MVP)

- Канал ввода: Telegram-бот.
- Основной поток: message → parsing → preview → confirm / edit / cancel → create Google Calendar event.
- Приоритеты: надежность, прозрачность, управляемость, быстрый выход к полезному результату.

## Структура репозитория

- `docs/PRD_MVP.md` — краткие продуктовые требования MVP.
- `docs/ARCHITECTURE.md` — архитектурный baseline для modular monolith.
- `docs/DEPLOYMENT.md` — базовые принципы деплоя и ограничения окружения.
- `docs/DECISIONS.md` — начальный журнал решений в формате ADR-like.
- `src/smart_life_bot/` — каркас Python-пакета.
- `tests/` — smoke-уровень тестов для foundation-слоя.
- `.github/workflows/ci.yml` — минимальный CI pipeline.

## Локальный запуск заглушки

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m smart_life_bot.main
python -m pytest
```

Текущая точка входа приложения намеренно оставлена как placeholder и пока не реализует Telegram handlers, интеграцию с Google Calendar, OAuth flow и FSM-логику.
