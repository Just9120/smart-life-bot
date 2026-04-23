# Initial Decisions Log (ADR-like)

## Status legend

- **Accepted** — active baseline decision.
- **Pending** — not decided yet.

---

## D-001: Telegram bot is the primary input channel

- **Status:** Accepted
- **Decision:** Use Telegram bot as the main entry point for MVP.
- **Rationale:** Fast user interaction loop and clear message-driven workflow.

## D-002: “Saved Messages / Избранное” is not the primary integration path

- **Status:** Accepted
- **Decision:** Do not rely on Telegram Saved Messages as core product integration path.
- **Rationale:** Product should work as explicit bot-based assistant, not as a side workflow.

## D-003: Modular monolith for MVP

- **Status:** Accepted
- **Decision:** Build MVP as modular monolith.
- **Rationale:** Minimize ops complexity and keep feature iteration speed high.

## D-004: Google Calendar is the first integration

- **Status:** Accepted
- **Decision:** Prioritize Google Calendar event creation in MVP.
- **Rationale:** Direct alignment with target user value and initial scope.

## D-005: OAuth is target auth design

- **Status:** Accepted
- **Decision:** `oauth_user_mode` is the intended long-term auth path.
- **Rationale:** Proper user-level authorization model for scalable product behavior.

## D-006: Service Account + shared calendar is fallback only

- **Status:** Accepted
- **Decision:** `service_account_shared_calendar_mode` is allowed only as fallback / quick personal mode.
- **Rationale:** Useful for early practicality, but not target architecture.

## D-007: CI/CD readiness from day one

- **Status:** Accepted
- **Decision:** Prepare CI/CD foundation from project start.
- **Rationale:** Preserve engineering discipline and reduce integration risks.

## D-008: Documentation and code evolve together

- **Status:** Accepted
- **Decision:** Any architecture/config/workflow/deployment/behavior change must include documentation update.
- **Rationale:** Keep project understandable and maintainable during fast iteration.
