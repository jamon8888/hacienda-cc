# Optimize Loop (8 Phases)

Run autonomously. Never call AskUserQuestion during phases 1–8.

## Phase 0: Initialize

```bash
git rev-parse HEAD          # record starting commit
git status                  # confirm clean working tree
python skills/hacienda-maker/scripts/validate_plugin.py .
python skills/hacienda-maker/scripts/run_evals.py --generate-transcripts
# dispatch grader agent for each entry in evals/transcripts-to-grade.json
python skills/hacienda-maker/scripts/run_evals.py --score --baseline
```

Set `loop.status = "running"`, `loop.current_iteration = 0`.

## Phase 1: Read Context

```bash
git log --oneline -5        # recent history
git diff HEAD~1             # last change if any
tail -5 hacienda-maker-results.tsv   # recent scores
cat hacienda-maker.json     # current state
cat evals/analyzer-insight.md 2>/dev/null  # last insight if exists
```

## Phase 2: Plan Improvement

Prioritize (in order):
1. Evals with lowest median pass_rate (fix functional failures first)
2. Trigger queries with pass_rate_q = 0.0 (fix complete trigger misses)
3. Description wording (if trigger_score < 70)
4. Skill body structure (if functional_score < 60)
5. Reference file content (if evals reference missing protocols)
6. Agent instructions (if grader flags hallucination or missing evidence)

## Phase 3: Make One Atomic Change

- ONE change per iteration (one file, one logical edit)
- Must pass validate_plugin.py after the change
- Never change tests or scoring scripts

## Phase 4: Commit

```bash
git add <changed files>
git diff --cached           # verify only intended changes staged
python skills/hacienda-maker/scripts/validate_plugin.py .   # gate: exit if fails
git commit -m "optimize: <brief description of change>"
```

If a hook blocks the commit: discard the change (git restore), increment no_op_streak.

## Phase 5: Evaluate

```bash
python skills/hacienda-maker/scripts/run_evals.py --generate-transcripts
# dispatch grader agent for each entry in evals/transcripts-to-grade.json
python skills/hacienda-maker/scripts/run_evals.py --score
```

### Phase 5.1: Analyze (if is_improvement = true)

Dispatch analyzer agent with:
```
git_diff: <git diff HEAD~1>
previous_row: <previous TSV row>
current_row: <current TSV row>
```

The analyzer writes to `evals/analyzer-insight.md`. If the file already exists, it is overwritten.

## Phase 6: KEEP or DISCARD

Decision tree:
- `is_improvement = true` → KEEP: update `history.best_score`, `history.best_commit`, reset `loop.no_op_streak = 0`
- `is_improvement = false` → DISCARD: `git reset --hard HEAD~1`, increment `loop.no_op_streak`
- Score crashed (combined_score < baseline - 10) → DISCARD + log crash event
- No change committed (validate failed or hook blocked) → no_op: increment `loop.no_op_streak` without git reset

**No-op streak rule**: If `loop.no_op_streak >= 5`, set `loop.status = "complete"` and stop.

Note: "no-op streak" counts consecutive iterations where either (a) no commit was made or (b) the commit was discarded. A KEEP resets the streak to 0.

## Phase 7: Log Progress

Append to `hacienda-maker-results.tsv`:
```
{iteration}\t{combined_score}\t{trigger_score}\t{functional_score}\t{delta}\t{is_improvement}\t{commit_sha}\t{timestamp}
```

## Phase 8: Stop Condition

Stop if:
- `combined_score >= scoring.threshold` → set `loop.status = "complete"`
- `loop.current_iteration >= loop.max_iterations` → set `loop.status = "complete"`
- `loop.no_op_streak >= 5` → set `loop.status = "complete"`

Otherwise: increment `loop.current_iteration`, go to Phase 1.
