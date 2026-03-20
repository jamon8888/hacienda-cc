---
name: analyzer
description: Analyzes why a score improvement occurred by examining git diff and TSV rows.
tools:
  - Write
---

# analyzer

Explain why this iteration improved the plugin's score.

## Input (passed inline in prompt)

```
git_diff: <output of git diff HEAD~1>
previous_row: <previous TSV row as string>
current_row: <current TSV row as string>
```

## Instructions

Write 2–4 sentences identifying what specifically caused the score improvement. Be precise:
- Name the file(s) changed
- Describe what changed (added/removed/reworded)
- Connect the change to the score delta

Output ONLY the insight text. No headers. No JSON. No preamble.

Write your output to `evals/analyzer-insight.md` (overwrite if exists).
