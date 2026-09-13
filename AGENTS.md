# AGENTS.md

MANDATORY: every repo task starts with the `manager` skill. Manager scopes, routes, validates, and closes locally. Read matched skill and agent descriptions before use.

## Mirror

- Keep `AGENTS.md` and `CLAUDE.md` content-synced; only tree paths differ.
- Keep `.agents/` and `.claude/` behavior-synced in the same change.
- Keep project details in the `nutrition-bot` skill. Keep root rules compact.

## Agents

| Agent | Use when |
|---|---|
| [`architect`](.agents/agents/architect.md) | Plan non-trivial implementation |
| [`developer`](.agents/agents/developer.md) | Implement or fix code |
| [`reviewer`](.agents/agents/reviewer.md) | Review a diff and requirements |
| [`tester`](.agents/agents/tester.md) | Run offline validation |
| [`operator`](.agents/agents/operator.md) | Review env, runtime, sidecar, or deployment safety |

## Skills

| Skill | Use when |
|---|---|
| [`manager`](.agents/skills/manager/SKILL.md) | Mandatory repo-task orchestrator |
| [`nutrition-bot`](.agents/skills/nutrition-bot/SKILL.md) | Product behavior, config, services, storage, tests, or runtime |
| [`shallow-scoring`](.agents/skills/shallow-scoring/SKILL.md) | Score task complexity before manager routing |
| [`self-verify`](.agents/skills/self-verify/SKILL.md) | Final evidence check |
| [`flow-testing`](.agents/skills/flow-testing/SKILL.md) | Mandatory offline and live acceptance for every update |

## Always-on rules

- Keep changes narrow. Preserve existing behavior outside task scope.
- Write code, comments, identifiers, docs, tests, and user-facing defaults in English. Runtime settings may select another response language.
- Keep secrets in `.env`. Never read, print, edit, commit, or copy `.env` or live credentials.
- Keep tests offline. Mock Telegram, OpenAI, Notion, filesystem state, and sleeps at the changed boundary.
- Preserve owner access fail-closed before media downloads, OpenAI calls, Notion calls, or other provider work.
- SQLite is authoritative. A Notion failure must not lose a local entry.
- Parse env settings in `config.py`; update `.env.example`, README, and tests when the public config contract changes.
- Run targeted tests first when useful. Run `make test` before sign-off for code changes.
- Production runs as `nutrition-bot.service` from an immutable release. The Spur sidecar uses a separate DEV bot, `.env.dev`, SQLite, Notion database and lock; both may run concurrently. Never test synthetic meals in production. See `docs/deployment.md`.
- Do not require a remote repository, commit, push, PR, or merge. Local verified work completes the task unless the user explicitly requests remote delivery.
