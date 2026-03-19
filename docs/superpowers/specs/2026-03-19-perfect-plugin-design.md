# perfect-plugin — Design Spec

**Date:** 2026-03-19
**Status:** Approved

---

## Problem

Plugin developers building for Claude Cowork have no automated path from "here is what I want this plugin to do" to "here is a plugin that reliably does it." They write skills by intuition, have no benchmark to measure quality, and no feedback loop to improve trigger precision or functional correctness over time. Existing tools (plugin-forge, autoresearch) solve adjacent pieces but are not wired together.

---

## Goal

A distributable Claude Code plugin — `perfect-plugin` — that:

1. Converts natural-language use cases into structured evals (the benchmark)
2. Scaffolds an initial plugin from those evals
3. Runs an autonomous autoresearch loop that iteratively improves the whole plugin (SKILL.md body, description, agents, references) against the combined eval score until a quality threshold or iteration limit is reached
4. Converts existing Claude Code plugins to Cowork-compatible versions with score verification

---

## Users

Plugin developers who know what a SKILL.md is and want a rigorous, automated quality loop — not a hand-holding wizard. This is a power tool, not a beginner guide.

---

## Architecture

Three intellectual layers, each borrowed from a codebase in the workspace:

| Layer | Source | Contribution |
|---|---|---|
| Orchestration | superpowers-main | Skill triggering, subagent-per-task, two-stage review, parallel dispatch |
| Iteration engine | autoresearch-master | 8-phase loop, git-as-memory, TSV logging, guard, noise handling, crash recovery |
| Plugin craft | plugin-forge | Eval types, grader/analyzer agents, description optimization, Cowork platform constraints |

---

## Plugin Structure

```
perfect-plugin/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   └── perfect-plugin/
│       ├── SKILL.md                      ← env detection + phase routing
│       ├── references/
│       │   ├── collect-workflow.md       ← NL → structured eval generation rules
│       │   ├── build-workflow.md         ← plugin scaffold using plugin-forge patterns
│       │   ├── optimize-loop.md          ← 8-phase autoresearch loop adapted for plugins
│       │   ├── convert-workflow.md       ← CC → Cowork platform adaptation rules
│       │   ├── scoring.md                ← combined score formula + noise handling
│       │   └── state-schema.md           ← perfect-plugin.json full spec
│       ├── agents/
│       │   ├── eval-generator.md         ← NL use cases → trigger-eval.json + evals.json
│       │   ├── grader.md                 ← grades assertions against transcripts
│       │   ├── analyzer.md               ← post-hoc: why did iteration N beat N-1?
│       │   └── cowork-converter.md       ← CC platform → Cowork platform adaptation
│       └── scripts/
│           ├── run_evals.py              ← trigger + functional evals → combined score JSON
│           ├── score.py                  ← weighted score + noise median
│           └── validate_plugin.py        ← structural validation
├── commands/
│   ├── perfect-plugin.md                 ← master orchestrator
│   └── perfect-plugin/
│       ├── collect.md
│       ├── build.md
│       ├── optimize.md
│       └── convert.md
└── README.md
```

---

## State File: `perfect-plugin.json`

Lives at the root of the target plugin directory. Persists across session interruptions. Every command reads it before acting and writes it after.

```json
{
  "plugin_path": "./",
  "platform": "cowork | claude-code | both",
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
    "max_iterations": 30,
    "current_iteration": 0,
    "status": "idle | running | complete"
  },
  "history": {
    "baseline_score": null,
    "best_score": null,
    "best_commit": null,
    "results_log": "perfect-plugin-results.tsv"
  }
}
```

---

## Commands

### `/perfect-plugin` — Master Orchestrator

Runs the full pipeline for new plugins: collect → build → optimize. Entry point for first-time use.

### `/perfect-plugin:collect` — Use Cases → Evals

Dialogue to capture natural-language use cases one at a time. Dispatches `eval-generator` agent which produces:

- `evals/trigger-eval.json` — 10–20 queries, 60% should_trigger=true, 40% false. Positive queries use realistic developer phrasing, not skill jargon. Negative queries are genuinely adjacent (ambiguous, not trivially out-of-scope).
- `evals/evals.json` — one functional eval per use case, with verifiable `expectations` (structural, content-presence, accuracy — never "looks good" or "seems correct").

Writes use cases and eval paths to `perfect-plugin.json`. Creates the file if it doesn't exist.

### `/perfect-plugin:build` — Evals → Plugin Scaffold

Reads `perfect-plugin.json` (platform, use cases, evals). Determines required components using YAGNI — only what the use cases actually require. Applies plugin-forge's exact schemas:

- SKILL.md with valid frontmatter (name, description under 1024 chars, no `<` or `>`)
- Agent `tools` fields as JSON arrays (never comma-separated strings)
- All paths using `${CLAUDE_PLUGIN_ROOT}`
- `plugin.json` manifest with semver version

Runs `validate_plugin.py` as a structural gate. Records baseline score via `run_evals.py`. Initializes `perfect-plugin-results.tsv` with the baseline row.

### `/perfect-plugin:optimize` — Autoresearch Loop

Runs the 8-phase loop (see Optimize Loop section below). Reads stopping config from `perfect-plugin.json`:
- Stops when `combined_score >= scoring.threshold` OR `loop.current_iteration >= loop.max_iterations`
- Whichever comes first

Can be re-run after adding new use cases (via `:collect`) to continue improving against an expanded benchmark.

### `/perfect-plugin:convert` — CC Plugin → Cowork

Takes an existing Claude Code plugin and applies the Cowork platform adaptation checklist (see Convert Workflow section). After conversion, runs `run_evals.py` to verify behavior is preserved. If score drops vs original, reports the delta and which components need attention.

---

## Optimize Loop (8 Phases)

Autoresearch's protocol adapted for plugin iteration. The "codebase" being optimized is the plugin itself.

### Phase 0 — Preconditions (before loop starts)

```bash
git rev-parse --git-dir          # must be a git repo — fail fast if not
git status --porcelain           # must be clean — never proceed with uncommitted user work
python validate_plugin.py ./     # structural integrity gate
python run_evals.py --baseline   # establish baseline score
```

Writes baseline row to TSV:
```tsv
iteration  commit   trigger  functional  combined  delta  guard  status    description
0          a1b2c3d  62.0     71.0        67.4      0.0    pass   baseline  initial state
```

### Phase 1 — Review (every iteration, mandatory)

```bash
git log --oneline -20                    # what was tried, what was kept vs reverted
git diff HEAD~1                          # what specifically improved the score last time
tail -20 perfect-plugin-results.tsv      # pattern recognition across iterations
cat perfect-plugin.json                  # current best score, iteration count
```

Read ALL plugin files. Identify: did trigger score drive the delta? Functional? Both? Which component correlates with kept commits?

### Phase 2 — Ideate (plugin-specific priority order)

1. Fix crashes / validation failures first
2. Exploit successes — if last kept commit touched description and trigger score jumped, try another description variant. Read `git diff HEAD~1` to see exactly what changed.
3. If trigger score is the weak leg → target `SKILL.md` description/frontmatter
4. If functional score is the weak leg → target skill body, references, or agents
5. If both weak → structural change: add a reference file, add an agent, reorganize sections
6. Stuck (5+ consecutive discards) → radical: rewrite description from scratch, try completely different SKILL.md structure

### Phase 3 — Modify (one atomic plugin change)

The one-sentence test applied to plugins:

| One atomic change ✓ | Two changes — split ✗ |
|---|---|
| Add 3 trigger examples to description | Add examples AND rewrite body |
| Extract a large section to `references/` | Extract AND add new agent |
| Rewrite agent instructions | Rewrite agent AND add hook |
| Add error handling section to body | Add section AND fix description |

### Phase 4 — Commit

```bash
git add skills/ agents/ references/   # explicit paths — NEVER git add -A
git diff --cached --quiet             # check something is actually staged
git commit -m "experiment(skill): <one-sentence description>"
```

`validate_plugin.py` runs as a structural guard before scoring. Hook failures logged as `hook-blocked`, never bypassed with `--no-verify`.

### Phase 5 — Verify

```bash
python run_evals.py   # outputs trigger_score, functional_score, combined_score
```

**Noise handling** (LLM eval outputs are inherently variable):
- Default: 3 runs per eval, median score used
- Only treat as improvement if `delta > noise_floor` (default 2.0 points)
- Prevents false keep decisions from lucky single runs

**Parallelism** (from superpowers dispatching-parallel-agents): trigger evals and functional evals are independent — dispatch both in parallel, merge scores. Reduces wall-clock time per iteration.

### Phase 6 — Decide

```
combined_score improved AND delta > noise_floor AND validate_plugin passes
  → KEEP (commit stays, git history records the success)

combined_score improved BUT validate_plugin fails
  → revert, rework implementation (max 2 attempts), retry

combined_score same or worse
  → git revert HEAD --no-edit  (preserves experiment in history for learning)
  → NEVER git reset --hard (destroys history, kills git-as-memory)

Crashed (OOM, syntax error, etc.)
  → fix if fixable (max 3 tries), else revert and move on
```

**Simplicity override** (from autoresearch core principles): if delta < 0.5 points but change adds significant complexity, treat as discard. If delta = 0 but plugin is simpler, treat as keep.

### Phase 7 — Log

Append to `perfect-plugin-results.tsv` (gitignored, local only):

```tsv
iteration  commit   trigger  functional  combined  delta  guard  status   description
1          b2c3d4e  71.0     78.0        75.2      +7.8   pass   keep     add 4 trigger examples for edge case phrasing
2          -        68.0     74.0        71.6      -3.6   -      discard  rewrite body as numbered steps (hurt trigger)
3          -        -        -           -         -      -      crash    add MCP server config (syntax error in json)
```

Every 10 iterations, print a summary:
```
=== perfect-plugin Progress (iteration 10) ===
Baseline: 67.4 → Current best: 78.9 (+11.5)
Keeps: 4 | Discards: 5 | Crashes: 1
Last 5: keep, discard, discard, keep, discard
```

### Phase 8 — Repeat

Stop when: `combined_score >= threshold` OR `current_iteration >= max_iterations`. Never ask "should I keep going?" — the state file has the answer. In bounded mode, print a final summary.

---

## Scoring

```
trigger_score    = (correct_trigger_queries / total_trigger_queries) × 100
functional_score = (assertions_passed / total_assertions) × 100
combined_score   = (trigger_score × 0.4) + (functional_score × 0.6)
```

Functional scoring is handled by the `grader` agent (from plugin-forge): given an eval prompt + execution transcript, it outputs `grading.json` with pass/fail per assertion, evidence quotes, and improvement suggestions.

The `analyzer` agent runs post-hoc after each kept commit: "the description change in iteration 3 improved trigger score by 11 points — the key was adding 'I want to build' which matches developer intent vocabulary." This output is included in Phase 2 ideation for the next iteration.

---

## Agents

### `eval-generator`

Input: list of NL use cases from the collect dialogue.
Output: `evals/trigger-eval.json` + `evals/evals.json`.

Knows the good/bad assertion rules from plugin-forge's eval-guide:
- Good: "Output contains exactly 3 sections: Summary, Risks, Recommendations"
- Bad: "Output looks reasonable", "Claude used the skill", "Output is helpful"

Enforces: 10–20 trigger queries, 60/40 positive/negative split, no trivially in/out-of-scope queries.

### `grader`

Adapted from plugin-forge's `agents/grader.md`. Grades assertions against execution transcripts. Produces `grading.json` with pass/fail per assertion, evidence quotes, and suggestions.

### `analyzer`

Adapted from plugin-forge's `agents/analyzer.md`. Post-hoc analysis: reads two consecutive plugin versions (the kept commit diff) and explains which specific change caused the score improvement. Used by the loop's Phase 2 ideation.

### `cowork-converter`

Owns the CC → Cowork conversion checklist:

| CC artifact | Cowork adaptation |
|---|---|
| `claude -p` CLI calls | Replace with inline eval logic |
| Browser display / live server | `--static` HTML output |
| Interactive terminal prompts | `AskUserQuestion` tool |
| Hardcoded absolute paths | `${CLAUDE_PLUGIN_ROOT}` |
| CLI-dependent hooks | Rewrite as `prompt` type hooks |
| `commands/*.md` (legacy format) | Migrate to `skills/*/SKILL.md` |

After conversion: runs `run_evals.py` to verify behavior preserved vs original. Reports score delta per component if quality dropped.

---

## Scripts

### `run_evals.py`

Runs trigger evals and functional evals (in parallel via subprocess). Applies noise handling (3 runs, median). Outputs:

```json
{
  "trigger_score": 74.0,
  "functional_score": 81.0,
  "combined_score": 78.2,
  "runs": 3,
  "trigger_detail": { "passed": 11, "failed": 4, "total": 15 },
  "functional_detail": { "passed": 13, "failed": 3, "total": 16 }
}
```

### `score.py`

Computes weighted combined score from trigger and functional inputs. Applies `noise_floor` check. Reads weights from `perfect-plugin.json`.

### `validate_plugin.py`

Structural validation before any scoring. Checks:
- `.claude-plugin/plugin.json` exists with `name`
- All SKILL.md files have valid frontmatter (`name` matches directory, `description` under 1024 chars, no `<` or `>`)
- Agent `tools` fields are JSON arrays (never comma strings)
- No hardcoded absolute paths (no `/Users/`, no `C:\`)
- `${CLAUDE_PLUGIN_ROOT}` used for all plugin-relative paths

Exits non-zero on any failure (acts as a git hook guard).

---

## Key Design Decisions

**Why re-implement the autoresearch loop rather than calling the autoresearch plugin?**
A plugin-specific loop needs richer semantics for what "one atomic change" means (SKILL.md body vs description vs adding an agent). The generic autoresearch loop treats all file changes as equivalent. Owning the loop lets us apply plugin-specific ideation heuristics in Phase 2.

**Why shared state file rather than agent-per-phase?**
The state file enables resumable sessions (interrupted optimize loop resumes from `best_commit`), a single audit trail across all commands, and consistent stopping-condition logic. Agent-per-phase would require passing large context objects at boundaries and makes debugging failures harder.

**Why 0.4/0.6 trigger/functional weighting?**
Functional correctness is harder to achieve and more valuable — a skill that triggers but produces wrong output is worse than one that misses some triggers. The 0.6 weight rewards getting the behavior right. Weights are configurable in `perfect-plugin.json`.

**Why `noise_floor: 2.0` as default?**
LLM-graded evals have inherent variance of ~1–3 points across runs. A 2-point minimum improvement threshold prevents the loop from keeping changes that only appear better due to random grading variance. The 3-run median further reduces this risk.

---

## Success Criteria

- A developer can go from "here are 5 use cases" to a scored, git-tracked plugin in one session
- The optimize loop runs unattended until threshold or max_iterations — no "should I continue?" prompts
- A converted CC plugin passes structural validation and scores within 5 points of the original
- The TSV log is always readable by a human to understand what the loop tried and why

---

## Out of Scope

- Building the eval infrastructure (reuses plugin-forge's grader agent and scripts)
- Publishing to a marketplace (out of scope — developers do this after the loop completes)
- Support for Claude.ai web (no `claude -p`, no subagents — optimize loop requires Claude Code)
- Multi-plugin optimization in one loop run (one plugin per state file, one loop at a time)
