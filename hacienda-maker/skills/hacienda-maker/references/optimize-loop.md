# Optimize Loop (8 Phases)

Run autonomously. Never call AskUserQuestion during phases 1–8.

**IMPORTANT**: All evaluation happens INLINE within this session. Do NOT spawn external processes.

## Phase 0: Initialize

1. Run validation:
```
git rev-parse HEAD          # record starting commit
git status                  # confirm clean working tree
```
2. Read `references/inline-evaluation.md` for evaluation protocol
3. Run inline trigger evaluation (read trigger-eval.json, match against SKILL.md)
4. Run inline functional evaluation (read evals.json, execute prompts, check expectations)
5. Compute combined score and set baseline

Set `loop.status = "running"`, `loop.current_iteration = 0`.

## Phase 1: Read Context

Read these files:
- `git log --oneline -5` — recent history
- `git diff HEAD~1` — last change if any
- `hm-results.tsv` — recent scores (last 5 lines)
- `hm.json` — current state
- `evals/analyzer-insight.md` — last insight if exists

## Phase 2: Plan Improvement

Prioritize (in order):
1. Evals with lowest pass rate (fix functional failures first)
2. Trigger queries that miss (fix trigger description)
3. Description wording (if trigger_score < 70)
4. Skill body structure (if functional_score < 60)
5. Reference file content (if evals reference missing protocols)
6. Agent instructions (if expectations fail)

## Phase 3: Make One Atomic Change

- ONE change per iteration (one file, one logical edit)
- Validate the plugin still loads correctly
- Never change tests or scoring logic

## Phase 4: Commit

```
git add <changed files>
git diff --cached           # verify only intended changes staged
git commit -m "optimize: <brief description of change>"
```

If a hook blocks the commit: discard the change (git restore), increment no_op_streak.

## Phase 5: Evaluate (Inline)

**Run evaluation directly in this session:**

1. **Trigger Eval**: For each query in `evals/trigger-eval.json`:
   - Read SKILL.md description
   - Determine if query matches skill purpose
   - Check if result matches `should_trigger`
   - Compute pass rate

2. **Functional Eval**: For each eval in `evals/evals.json`:
   - Execute the prompt (respond as the skill would)
   - Check each expectation:
     - "contains": verify text appears in output
     - "semantic": judge if expectation is met
   - Compute pass rate per eval

3. **Score**: 
   ```
   combined = trigger_score * 0.4 + functional_score * 0.6
   delta = combined - history.best_score
   is_improvement = delta >= noise_floor
   ```

### Phase 5.1: Analyze (if is_improvement = true)

Read `git diff HEAD~1` and analyze what changed. Write insight to `evals/analyzer-insight.md`:
- What was changed
- Why it improved the score
- What to try next if score plateaus

## Phase 6: KEEP or DISCARD

Decision tree:
- `is_improvement = true` → KEEP: update `history.best_score`, `history.best_commit`, reset `loop.no_op_streak = 0`
- `is_improvement = false` → DISCARD: `git reset --hard HEAD~1`, increment `loop.no_op_streak`
- Score crashed (combined_score < baseline - 10) → DISCARD + log crash event
- No change committed → no_op: increment `loop.no_op_streak` without git reset

**No-op streak rule**: If `loop.no_op_streak >= 5`, set `loop.status = "complete"` and stop.

## Phase 7: Log Progress

Append to `hm-results.tsv`:
```
{iteration}\t{combined_score}\t{trigger_score}\t{functional_score}\t{delta}\t{is_improvement}\t{commit_sha}\t{timestamp}
```

Update `hm.json` with current scores.

## Phase 8: Stop Condition

Stop if:
- `combined_score >= scoring.threshold` → set `loop.status = "complete"`
- `loop.current_iteration >= loop.max_iterations` → set `loop.status = "complete"`
- `loop.no_op_streak >= 5` → set `loop.status = "complete"`

Otherwise: increment `loop.current_iteration`, go to Phase 1.
