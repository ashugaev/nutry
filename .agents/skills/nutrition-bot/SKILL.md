---
name: nutrition-bot
description: Work on nutrition-bot Telegram behavior, OpenAI analysis or transcription, SQLite diary, Notion mirroring, environment, tests, and sidecar runtime.
---

# Nutrition Bot

## Ownership

- `bot.py`: Telegram handlers, owner/private-chat guard, user flows.
- `config.py`: environment parsing and defaults.
- `services/analyzer.py`: multimodal nutrition estimates and transcription.
- `services/store.py`: authoritative SQLite persistence and totals.
- `services/notion.py`: optional best-effort mirror.
- `services/dashboard.py`, `web/`: read-only Telegram Mini App and signed access.
- `tests/`: offline boundary and behavior checks.

## Invariants

- Guard before all replies, downloads, provider calls, and state changes.
- Mini App requires signed fresh Telegram initData and the same allowlist before
  diary reads. Public assets must contain no diary data. No bearer URLs in logs.
- Require OWNER_USER_ID or an explicit ALLOWED_USER_IDS member in a private chat.
- Both operator accounts share one diary. Preserve both IDs during runtime changes.
- Replies to saved bot messages update their existing entry; message links persist in SQLite.
- Unidentified food must never create or replace a diary entry.
- Validate model JSON, finite nutrients, and nonempty dish names.
- Fiber is nullable grams per consumed portion. Legacy/unknown is not zero;
  partial daily totals show missing entries. Notion uses a numeric Fiber property.
- Language defaults to English. Only explicit /start buttons or /lang selects
  Russian. SQLite stores preferences per account; analysis uses a request-local
  language, never shared mutable state. Mini App uses the authenticated preference.
- Save locally before Notion. Report local success even if mirroring fails.
- Persist Notion page ids so corrections update and deletes archive mirrored pages.
- Suppress credential-bearing HTTP request logs.

Run `make test` and mandatory DEV flow tests; see `docs/deployment.md`.
Production is `nutrition-bot.service`, running a validated immutable release.
Spur is DEV-only with a different bot, .env.dev, SQLite, Notion database and lock.
Both runtimes may stay active. Environment guards must reject production aliases.
Never send synthetic food to production or change the allowlist for tests.
The reload gate promotes only the snapshot that passed both-language DEV tests.
Production acceptance is read-only. Stop the timer during planned maintenance.
