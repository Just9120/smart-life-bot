# Architecture Baseline — Smart Life Ops Bot

## 1. Overview

Smart Life Ops Bot is designed as a modular monolith with clear internal boundaries and unified product logic for event capture and calendar write flows.

## 2. Architectural principles

- Reliability before feature breadth.
- Explicit confirmation before external side effects.
- Single business flow independent from concrete auth-mode implementation.
- Keep bootstrap simple; defer low-level choices until required.
- Documentation-first change discipline.

## 3. Modular monolith approach

The system remains one deployable application for MVP, with modules separated by responsibilities and contracts. This reduces operational complexity while preserving evolution path for future extraction if needed.

## 4. Planned modules

- `bot_entry` — Telegram ingress and outbound messaging adapter.
- `orchestration` — flow control across parse/preview/confirm/create steps.
- `parsing` — extraction and normalization of event fields.
- `confirmation` — preview rendering and confirm/edit/cancel decision handling.
- `calendar` — provider abstraction and concrete Google Calendar adapter.
- `auth` — auth abstraction for supported Google auth modes.
- `storage` — state and authorization persistence interface.
- `logging_observability` — structured logs and error reporting foundation.

> Pending: final package/module split and interfaces will be formalized during implementation phases.

## 5. Auth abstraction

A unified auth abstraction will hide auth-mode specifics from product flow:

- `oauth_user_mode` (target design)
- `service_account_shared_calendar_mode` (fallback quick personal mode)

No duplicated user-flow logic is allowed per auth mode.

> Pending: token lifecycle details, credential refresh handling, and error taxonomy.

## 6. Storage layer

Storage layer is responsible for:

- conversation/session state,
- confirmation state transitions,
- auth-related metadata.

Bootstrap keeps storage as interface-level design; concrete backend choice is pending.

> Pending: backend selection, schema, migration strategy, retention policy.

## 7. Bot/FSM layer

Bot layer and state-machine behavior are planned as separate concerns:

- bot transport adapter (Telegram),
- state orchestration logic.

Bootstrap does not implement handlers or FSM internals.

> Pending: FSM model, command policy, retry and idempotency behavior.

## 8. Parsing layer

Parsing transforms incoming text into a normalized event draft for preview and later confirmation.

Bootstrap defines the parsing role only.

> Pending: parsing strategy, confidence model, locale/timezone handling, ambiguity resolution policy.

## 9. Calendar integration layer

Calendar module provides a stable internal interface for event creation.

Google Calendar is the first integration target.

Bootstrap intentionally excludes low-level API implementation.

> Pending: API client choice, error mapping, quota handling, idempotent create semantics.

## 10. Deployment overview

Deployment baseline:

- source of truth in GitHub,
- CI/CD via GitHub Actions,
- Docker-based runtime,
- target host: VPS (Contabo),
- production hostname via Cloudflare-managed subdomain.

Detailed procedures are intentionally deferred to later deployment hardening.

## 11. Technical decisions still pending

- Concrete storage technology.
- FSM implementation style and boundaries.
- Detailed parsing algorithm and tooling.
- Google OAuth callback and secure token storage pattern.
- Runtime process model and observability stack depth.
