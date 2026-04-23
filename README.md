# Smart Life Ops Bot

Smart Life Ops Bot is a Telegram assistant focused on fast and reliable event capture into Google Calendar with mandatory confirmation before writing any event.

**Current status:** repository bootstrap / phase 1 foundation.

## Product intent (MVP)

- Input channel: Telegram bot.
- Core flow: message → parsing → preview → confirm / edit / cancel → create Google Calendar event.
- Priorities: reliability, transparency, controllability, speed to useful outcome.

## Repository structure

- `docs/PRD_MVP.md` — concise MVP product requirements.
- `docs/ARCHITECTURE.md` — architecture baseline for modular monolith.
- `docs/DEPLOYMENT.md` — deployment foundation and environment constraints.
- `docs/DECISIONS.md` — initial ADR-like decision log.
- `src/smart_life_bot/` — Python package scaffold.
- `tests/` — smoke-level tests for foundation.
- `.github/workflows/ci.yml` — minimal CI pipeline.

## Local stub run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m smart_life_bot.main
python -m pytest
```

The current application entry point is intentionally a placeholder and does not yet implement Telegram handlers, Google Calendar integration, OAuth flow, or FSM logic.
