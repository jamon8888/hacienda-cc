---
description: >
  Use when the user runs /hacienda-maker:build. Scaffolds plugin skeleton from evals,
  runs baseline evaluation, initializes TSV log.
---

# /hacienda-maker:build

Read `references/build-workflow.md` for the full protocol.

Summary:
1. Read `hacienda-maker.json` — platform, use cases, evals.
2. Scaffold minimal skeleton: plugin.json, SKILL.md, evals/ (already written by :collect).
3. Run `validate_plugin.py` — fail fast if structural issues.
4. Run `run_evals.py --generate-transcripts` then dispatch graders then `run_evals.py --score --baseline`.
5. Initialize `hacienda-maker-results.tsv` with baseline row.
