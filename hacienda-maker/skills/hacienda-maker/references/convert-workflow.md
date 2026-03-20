# Convert Workflow

## Purpose

Convert a Claude Code plugin to Cowork-compatible format, verifying score is preserved.

## Precondition

`evals/trigger-eval.json` and `evals/evals.json` must exist. If missing, abort:
"Run /hacienda-maker:collect first to generate evals before converting."

## Steps

1. Write `convert.original_platform = hacienda-maker.json["platform"]` to state.
2. Run pre-conversion evals → store result as `convert.original_score`.
3. Dispatch `cowork-converter` agent:
   ```
   plugin_path: ./
   checklist: [all 8 items]
   report_path: evals/convert-report.md
   ```
4. Run structural gate: `python skills/hacienda-maker/scripts/validate_plugin.py .`
   - If fails: abort with "Conversion introduced structural errors. Fix manually before re-running."
5. Run post-conversion evals → compare combined_score to `convert.original_score`.
6. Evaluate result:
   - Drop <= 5 points: **success**. Print: "Conversion complete. Score: {pre} → {post}"
   - Drop > 5 points: **advisory failure**. Print per-component report:
     ```
     Trigger score: {pre_trigger} → {post_trigger}
     Functional score: {pre_functional} → {post_functional}
     Unresolved items: [list from cowork-converter report]
     ```
     Do NOT revert automatically — user decides whether to accept or discard.
