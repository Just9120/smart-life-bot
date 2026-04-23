# Deployment Foundation — Smart Life Ops Bot

## 1. Source of truth

- GitHub repository is the canonical source of code and documentation.
- Main delivery flow is based on branches + pull requests.

## 2. CI/CD baseline

- GitHub Actions is used for CI (and later CD expansion).
- Initial CI validates Python environment setup and test execution.

## 3. Target runtime environment

- Deployment target: VPS on Contabo.
- Runtime packaging: Docker-based deployment.

## 4. Secrets handling

- Secrets must be provided only through GitHub Secrets and/or server environment variables.
- Secrets must not be committed to repository files, examples, or docs.

## 5. Networking and hostname plan

- Planned production hostname: dedicated subdomain on existing domain via Cloudflare.
- Target OAuth architecture requires a proper HTTPS endpoint.

## 6. Auth-mode deployment notes

- Target mode: `oauth_user_mode`, requires secure external callback endpoint.
- Fallback mode: `service_account_shared_calendar_mode`, can work without OAuth and without domain in personal setup (e.g., long polling).

Fallback mode is operationally acceptable for quick personal runs but not target product architecture.

## 7. Current stage limitations

This document is a foundation only. A final production playbook (rollout, rollback, monitoring, backups, incident steps) is intentionally deferred to a later phase.
