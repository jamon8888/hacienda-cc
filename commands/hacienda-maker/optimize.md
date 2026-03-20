---
description: >
  Use when the user runs /hacienda-maker:optimize. Executes the 8-phase autonomous
  improvement loop until score threshold or iteration limit.
---

# /hacienda-maker:optimize

Read `references/optimize-loop.md` for the full 8-phase protocol.

Inline configuration (user may append these to the command):
- `Iterations: N` — override max_iterations for this run only
- `Guard: <cmd>` — run this command as a guard after Phase 5; discard if non-zero

Stop conditions:
- `combined_score >= scoring.threshold` — set `loop.status = "complete"`, print final summary
- `loop.current_iteration >= loop.max_iterations` — same

Never call `AskUserQuestion` during phases 1–8.
