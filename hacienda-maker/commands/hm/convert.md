---
description: >
  Use when the user runs /hm:convert. Converts a Claude Code plugin to
  Cowork-compatible format with score verification.
---

# /hm:convert

Read `references/convert-workflow.md` for the full protocol.

**Precondition:** `evals/trigger-eval.json` and `evals/evals.json` must exist.
If either is missing, abort with:
"Run `/hm:collect` first to generate evals before converting."

Summary:
1. Write current `platform` value to `convert.original_platform` in state file.
2. Run pre-conversion evals then store `convert.original_score`.
3. Dispatch `cowork-converter` agent with all 8 checklist items.
4. Run `validate_plugin.py` — if fails, abort with instructions to fix manually.
5. Run post-conversion evals then compare to `convert.original_score`.
6. If drop <= 5 points: success. If drop > 5 points: print per-component report (advisory only).
