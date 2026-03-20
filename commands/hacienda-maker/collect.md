---
description: >
  Use when the user runs /hacienda-maker:collect. Captures use cases through dialogue
  and generates eval files.
---

# /hacienda-maker:collect

Read `references/collect-workflow.md` for the full protocol.

Summary:
1. Ask the user for use cases one at a time (description + expected_behavior per case).
   Continue until user says they are done.
2. Dispatch `eval-generator` agent with all collected use cases.
3. Write `hacienda-maker.json` with `use_cases` and `evals` fields (create if missing).
