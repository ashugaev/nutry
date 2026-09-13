---
name: flow-testing
description: Mandatory nutrition-bot update acceptance using offline tests, isolated DEV flows and read-only production verification.
---

# Flow Testing

The user authorizes project self-testing through the connected Assistant account.
Use its existing session; never request new login codes automatically.

- Run make test offline, then scripts/reload-if-changed.sh for the full gate.
- Synthetic food belongs only in DEV: separate bot, .env.dev, SQLite and Notion.
  Environment guards must pass before external calls.
- Test English and Russian, explicit picker and /lang selection, English default,
  persistence across DEV restart, and account isolation. Never change allowlists.
- Exercise text/photo/album/voice/audio, no-food rejection, formatted replies,
  fiber, same-ID corrections, SQLite totals and Notion updates/deletes.
- Run one live loop at a time. Clean only its own DEV records; verify cleanup even
  after failure before retrying.
- Verify signed Mini App launch, public HTTPS, denied anonymous access and totals.
  Use Playwright mobile language/day/history/ranges/empty/error/auth/zoom/scroll flows.
- Promote only the exact snapshot that passed all DEV checks. Production runs
  separately from an immutable release; do not stop it for DEV development.
- After promotion run production_smoke.py --run-live and
  live_mini_app_check.py --run-live --production: read-only commands and data.
  Never send synthetic food or modify preferences in production tests.
- Save sanitized evidence under SPUR_SESSION_ARTIFACTS_DIR, or .data/dev/artifacts
  and the reload journal. Failed live acceptance means unverified, not complete.

Read docs/deployment.md for runtime boundaries, retry, recovery and dependencies.
Production cleanup is never a test step and requires explicit authorization.
