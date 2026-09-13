---
name: manager
description: Orchestrate nutrition-bot repository work. Mandatory for every task; route implementation, review, runtime, tests, and close-out.
---

# Manager

1. Convert the request into acceptance criteria and score complexity with `shallow-scoring`.
2. Load `nutrition-bot` for product, configuration, test, or runtime work.
3. Route code changes through developer, reviewer, tester, and self-verify. Add operator for env, persistence, sidecar, or runtime changes.
4. Keep unit tests offline. Run targeted checks and `make test`, then follow the
   mandatory `flow-testing` skill for real Telegram acceptance of every update.
5. Fix one failed gate and rerun it. Report evidence and remaining risks.

Never expose secrets, touch DiaryBot, create a remote, or claim sidecar health without a stable bot child process.
