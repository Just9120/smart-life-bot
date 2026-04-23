# PRD — Smart Life Ops Bot MVP

## 1. Product

- **Project name:** Smart Life Ops Bot.
- **Primary input channel:** Telegram bot.
- **MVP target outcome:** reliable creation of Google Calendar events from natural user messages.

## 2. Core user scenario

`message → parsing → preview → confirm / edit / cancel → create event`

The event is created only after explicit user confirmation.

## 3. MVP priorities

1. Reliability
2. Transparency
3. Manageability
4. Speed to useful result

## 4. In scope for MVP

- Telegram bot entry point.
- Parsing of basic event entities (title/date/time/basic metadata).
- Event preview before write.
- User actions: confirm / cancel / edit.
- Google Calendar event creation.
- Logging of key actions and errors.
- Basic storage for state and authorization data.

## 5. Out of scope for MVP

- Tasks as a full second product contour.
- Multi-calendar complexity.
- Microservice decomposition.
- Autonomous event creation without confirmation.

## 6. Authentication modes for Google Calendar

Supported in design:

1. `oauth_user_mode` — target architecture and primary product mode.
2. `service_account_shared_calendar_mode` — fallback / quick personal mode.

Fallback mode is not considered the target long-term product architecture.

## 7. Roadmap phases

- **Phase 1 — Reliable Event Capture MVP**
- **Phase 2 — Reliability, Editing, and Trust**
- **Phase 3 — Task Layer**
- **Phase 4 — Smart Routing and Context Layer**

## 8. Non-goals for bootstrap stage

At repository bootstrap stage, business logic and external integrations are intentionally not implemented. This document defines direction and constraints for next implementation steps.
