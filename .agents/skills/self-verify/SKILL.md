---
name: self-verify
description: Verify nutrition-bot scope, routing, tests, runtime evidence, mirror parity, and secret safety at close-out.
---

# Self Verify

Confirm changed files match the request, required gates ran, `make test` is fresh, secrets stayed untracked and unlogged, AGENTS/CLAUDE and agent trees remain aligned, and any claimed sidecar has a stable Python child. Return PASS, MISSING, or RERUN with concise evidence.
