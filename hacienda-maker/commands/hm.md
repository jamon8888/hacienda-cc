---
description: >
  Use when the user runs /hm. Reads hm.json to resume mid-pipeline,
  or runs collect then build then optimize in sequence for first-time use.
---

# /hm

1. Check if `hm.json` exists in the current directory.
2. If it exists: read `loop.status`. Route:
   - `status = "idle"` — run `/hm:build` then `/hm:optimize`
   - `status = "running"` or `"crashed"` — resume `/hm:optimize` from current iteration
   - `status = "complete"` — print final score summary and exit
3. If it does not exist: run `/hm:collect` then `/hm:build` then `/hm:optimize` in sequence.

Read `references/state-schema.md` for field definitions.
