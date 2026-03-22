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

**IMPORTANT**: All evaluation happens INLINE within this session. Do NOT spawn external processes.

### 5.1 Trigger Evaluation (Inline)

For each query in `evals/trigger-eval.json`:
1. Read SKILL.md description
2. Use keyword overlap + intent pattern matching
3. Determine if query matches skill purpose
4. Check against `should_trigger` field
5. Compute pass rate

**Intent patterns recognized:**
- creation: build, create, make, generate, design, develop
- fixing: fix, repair, debug, solve, resolve
- analysis: analyze, review, check, audit, inspect
- optimization: optimize, improve, enhance, refactor
- testing: test, validate, verify, ensure

### 5.2 Functional Evaluation (Inline)

For each eval in `evals/evals.json`:
1. Read the prompt and expectations
2. Execute the prompt (respond as the skill would)
3. Check each expectation using inline evaluator:

**Deterministic types (no LLM needed):**
- `contains`: text appears in transcript (case-insensitive)
- `not_contains`: text does NOT appear in transcript
- `regex`: pattern matches transcript
- `json_valid`: valid JSON found (including in markdown code blocks)
- `max_words`: word count within limit

**Semantic type (requires LLM):**
- Batch multiple semantic expectations into one LLM call
- Parse response with `parse_semantic_response`

### 5.3 Score Calculation

```
combined = trigger_score * 0.4 + functional_score * 0.6
delta = combined - history.best_score
is_improvement = delta >= noise_floor
```

### Phase 5.4: Analyze (if is_improvement = true)

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
