---
description: >
  Use when the user runs /hacienda-maker. Reads hacienda-maker.json to resume mid-pipeline,
  or runs collect then build then optimize in sequence for first-time use.
---

# /hacienda-maker

1. Check if `hacienda-maker.json` exists in the current directory.
2. If it exists: read `loop.status`. Route:
   - `status = "idle"` — run `/hacienda-maker:build` then `/hacienda-maker:optimize`
   - `status = "running"` or `"crashed"` — resume `/hacienda-maker:optimize` from current iteration
   - `status = "complete"` — print final score summary and exit
3. If it does not exist: run `/hacienda-maker:collect` then `/hacienda-maker:build` then `/hacienda-maker:optimize` in sequence.

Read `references/state-schema.md` for field definitions.
