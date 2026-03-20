# State File: hacienda-maker.json

This file is created in the target plugin directory and gitignored. It tracks evaluation state across sessions.

## Full Schema

```json
{
  "platform": "cowork",
  "use_cases": [
    { "id": "uc-001", "description": "...", "expected_behavior": "..." }
  ],
  "evals": {
    "trigger_path": "evals/trigger-eval.json",
    "functional_path": "evals/evals.json"
  },
  "scoring": {
    "weights": { "trigger": 0.4, "functional": 0.6 },
    "threshold": 85,
    "noise_floor": 2.0,
    "runs_per_eval": 3
  },
  "loop": {
    "status": "idle",
    "current_iteration": 0,
    "max_iterations": 30,
    "no_op_streak": 0
  },
  "history": {
    "baseline_score": null,
    "best_score": null,
    "best_commit": null,
    "results_log": "hacienda-maker-results.tsv"
  },
  "convert": {
    "original_platform": null,
    "original_score": null
  }
}
```

## Field Notes

- `platform`: Valid values: `"cowork"`, `"claude-code"`
- `loop.status`: Valid values: `"idle"`, `"running"`, `"complete"`, `"crashed"`
- `loop.no_op_streak`: Count of consecutive iterations with no committed change
- `history.best_commit`: Git SHA of the commit that produced `best_score`
- `convert.original_platform`: Set when /hacienda-maker:convert is invoked; preserves the pre-conversion platform value

## Git Tracking

Add to `.gitignore`:
```
hacienda-maker.json
hacienda-maker-results.tsv
evals/transcripts/
evals/last-run.json
evals/trigger-results.json
evals/transcripts-to-grade.json
evals/analyzer-insight.md
```
