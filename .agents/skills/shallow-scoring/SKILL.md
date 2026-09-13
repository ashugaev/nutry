---
name: shallow-scoring
description: Score nutrition-bot task complexity from 1 to 5 before manager routing.
---

# Shallow Scoring

- 1: one obvious file; no external boundary.
- 2: small code and tests.
- 3: multiple modules or one integration.
- 4: cross-cutting behavior or runtime risk.
- 5: architecture or high uncertainty.

Return the score and one-sentence reason.
