# Inline Evaluation

Run evaluations directly within Claude Code session without spawning external processes.

## Trigger Evaluation

1. Read `evals/trigger-eval.json` for queries
2. Read `skills/*/SKILL.md` description
3. For each query, determine if the SKILL.md description would trigger:
   - Match query keywords against description keywords
   - Check if query intent matches skill purpose
   - Compare against `should_trigger` field
4. Compute pass rate: `passed / total * 100`

## Functional Evaluation

1. Read `evals/evals.json` for test cases
2. For each eval:
   - Read the prompt and expectations
   - Execute the prompt as if user sent it
   - Check output against expectations:
     - For "contains" type: check if text appears in output
     - For "semantic" type: use LLM judgment on whether expectation is met
   - Record pass/fail for each expectation
3. Compute median pass rate per eval, then average across evals

## Scoring

```
combined_score = trigger_score * weight_trigger + functional_score * weight_functional
```

Weights from `hm.json`: default `{trigger: 0.4, functional: 0.6}`

## Baseline Flow

1. Run trigger evaluation
2. Run functional evaluation
3. Compute combined score
4. Write `evals/last-run.json`
5. Update `hm.json`:
   - `history.baseline_score = combined_score`
   - `history.best_score = combined_score` (if null)
6. Append to `hm-results.tsv`:
   ```
   iteration=0, combined_score, trigger_score, functional_score, delta=0, is_improvement=false
   ```

## Iteration Flow

1. Run trigger + functional evaluation
2. Compute combined score
3. Compare to `history.best_score`:
   - If `delta >= noise_floor`: is_improvement = true
   - Else: is_improvement = false
4. Write `evals/last-run.json`
5. Update `hm.json`:
   - If improvement: `history.best_score = combined_score`
6. Append to `hm-results.tsv`
