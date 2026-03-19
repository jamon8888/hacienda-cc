# perfect-plugin — Design Spec

**Date:** 2026-03-19
**Status:** Approved (v2 — post spec-review)

---

## Problem

Plugin developers building for Claude Cowork have no automated path from "here is what I want this plugin to do" to "here is a plugin that reliably does it." They write skills by intuition, have no benchmark to measure quality, and no feedback loop to improve trigger precision or functional correctness over time. Existing tools (plugin-forge, autoresearch) solve adjacent pieces but are not wired together.

---

## Goal

A distributable Claude Code plugin — `perfect-plugin` — that:

1. Converts natural-language use cases into structured evals (the benchmark)
2. Scaffolds an initial plugin from those evals
3. Runs an autonomous iteration loop that improves the whole plugin (SKILL.md body, description, agents, references) against the combined eval score until a quality threshold or iteration limit is reached
4. Converts existing Claude Code plugins to Cowork-compatible versions with score verification

---

## Users

Plugin developers who know what a SKILL.md is and want a rigorous, automated quality loop — not a hand-holding wizard. This is a power tool, not a beginner guide.

---

## Architecture

Three intellectual layers from existing codebases — clarifying exactly what is reused vs re-implemented:

| Layer | Source | What is reused (verbatim copy → adapt) | What is re-implemented |
|---|---|---|---|
| Orchestration | superpowers-main | `dispatching-parallel-agents` skill pattern for parallel eval runs; `subagent-driven-development` two-stage review pattern for `:build` scaffolding | Nothing — used as behavioral reference only |
| Iteration engine | autoresearch-master | The 8-phase loop protocol, git-as-memory rules, TSV logging format, guard/noise/crash-recovery rules — all copied into `optimize-loop.md` as the authoritative reference | The loop is re-implemented inside `optimize-loop.md` with plugin-specific Phase 2 ideation heuristics. The autoresearch plugin is NOT called at runtime. |
| Plugin craft | plugin-forge | `agents/grader.md` and `agents/analyzer.md` copied verbatim into `perfect-plugin/skills/perfect-plugin/agents/` and adapted (frontmatter updated, tool list adjusted). `scripts/quick_validate.py` logic replicated in `validate_plugin.py`. Eval file schemas, plugin.json schema, SKILL.md frontmatter rules all reused. | `eval-generator.md` and `cowork-converter.md` agents are new. `run_evals.py` and `score.py` are new scripts. |

**At runtime:** `perfect-plugin` is a self-contained plugin. It does not call autoresearch or plugin-forge at runtime — it embeds the knowledge from both.

---

## Plugin Structure

```
perfect-plugin/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   └── perfect-plugin/
│       ├── SKILL.md                      ← env detection + command routing
│       ├── references/
│       │   ├── collect-workflow.md       ← NL → eval generation dialogue protocol
│       │   ├── build-workflow.md         ← evals → plugin scaffold protocol
│       │   ├── optimize-loop.md          ← 8-phase loop (adapted from autoresearch)
│       │   ├── convert-workflow.md       ← CC → Cowork adaptation checklist
│       │   ├── scoring.md                ← combined score formula + noise handling
│       │   └── state-schema.md           ← perfect-plugin.json full field spec
│       ├── agents/
│       │   ├── eval-generator.md         ← NEW: NL use cases → eval files
│       │   ├── grader.md                 ← ADAPTED from plugin-forge
│       │   ├── analyzer.md               ← ADAPTED from plugin-forge
│       │   └── cowork-converter.md       ← NEW: CC → Cowork adaptation
│       └── scripts/
│           ├── run_evals.py              ← NEW: orchestrates eval execution
│           ├── score.py                  ← NEW: weighted score + noise check
│           └── validate_plugin.py        ← ADAPTED from plugin-forge quick_validate.py
├── commands/
│   ├── perfect-plugin.md
│   └── perfect-plugin/
│       ├── collect.md
│       ├── build.md
│       ├── optimize.md
│       └── convert.md
└── README.md
```

---

## State File: `perfect-plugin.json`

Lives at the root of the **target plugin** directory (the plugin being built/optimized, not perfect-plugin itself). All relative paths resolve from this directory. Persists across session interruptions.

```json
{
  "plugin_path": "./",
  "platform": "cowork | claude-code",
  "use_cases": [
    { "id": "uc-001", "description": "string", "expected_behavior": "string" }
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
    "status": "idle | running | complete | crashed"
  },
  "history": {
    "baseline_score": null,
    "best_score": null,
    "best_commit": null,
    "results_log": "perfect-plugin-results.tsv"
  },
  "convert": {
    "original_score": null,
    "original_platform": null
  }
}
```

**Notes:**
- `platform` is `"cowork"` or `"claude-code"` only. Multi-platform is out of scope.
- `convert.original_score` stores the pre-conversion combined score, used by `:convert` to verify the 5-point acceptance criterion.
- `loop.status = "crashed"` records that the last run terminated abnormally, enabling deterministic resumption.
- All paths in `evals.trigger_path` and `evals.functional_path` are relative to `plugin_path`.

---

## Eval File Schemas

### `evals/trigger-eval.json`

```json
[
  {
    "query": "string — realistic user phrasing, not skill jargon",
    "should_trigger": true
  },
  {
    "query": "string — adjacent query, genuinely ambiguous about whether skill applies",
    "should_trigger": false
  }
]
```

Rules: 10–20 entries total. 60% `should_trigger: true`, 40% false. No trivially in/out-of-scope queries.

### `evals/evals.json`

```json
[
  {
    "id": "eval-001",
    "use_case_id": "uc-001",
    "prompt": "string — the exact prompt to run against the skill",
    "input_files": ["optional/path/to/sample.txt"],
    "expectations": [
      "string — verifiable assertion (structural, content-presence, accuracy, or process)"
    ],
    "notes": "string — optional context for the grader"
  }
]
```

Good expectations: "Output contains exactly 3 sections: Summary, Risks, Recommendations."
Bad expectations: "Output looks reasonable", "Claude used the skill", "Output is helpful."

---

## `run_evals.py` Output Schema

```json
{
  "trigger_score": 74.0,
  "functional_score": 81.0,
  "combined_score": 78.2,
  "runs": 3,
  "trigger_detail": {
    "passed": 11,
    "failed": 4,
    "total": 15,
    "failures": ["query text that failed"]
  },
  "functional_detail": {
    "passed": 13,
    "failed": 3,
    "total": 16,
    "grading_path": "evals/grading.json"
  }
}
```

`run_evals.py` orchestrates: it runs trigger queries via `claude -p`, collects results, then dispatches the `grader` agent for functional evals. It reads `grading.json` to count passes/failures. Score computation is delegated to `score.py`.

---

## `grading.json` Schema (output of `grader` agent)

```json
{
  "eval_id": "eval-001",
  "run_id": "run-1",
  "transcript_path": "evals/transcripts/eval-001-run-1.md",
  "expectations": [
    {
      "text": "Output contains exactly 3 sections: Summary, Risks, Recommendations",
      "passed": true,
      "evidence": "Found in transcript: '## Summary ... ## Risks ... ## Recommendations'"
    }
  ],
  "summary": {
    "passed": 3,
    "failed": 1,
    "total": 4,
    "pass_rate": 0.75
  }
}
```

`run_evals.py` reads all `grading.json` files (one per eval run) and aggregates `pass_rate` values to compute `functional_score`.

---

## `validate_plugin.py` Validation Rules

Exits non-zero if any rule fails:

1. `.claude-plugin/plugin.json` exists and contains `"name"` field (kebab-case)
2. Every `skills/*/SKILL.md` file has frontmatter with `name:` matching its directory name
3. Every `description:` field is under 1024 characters and contains no `<` or `>` characters
4. Every agent `tools:` field is a JSON array (not a comma-separated string)
5. No hardcoded absolute paths anywhere in plugin files (no `/Users/`, no `C:\`, no `/home/`)
6. All plugin-relative paths use `${CLAUDE_PLUGIN_ROOT}`

---

## TSV Log Schema

File: `perfect-plugin-results.tsv` (gitignored, lives at plugin root)

```tsv
# metric_direction: higher_is_better
iteration	commit	trigger	functional	combined	delta	guard	status	description
0	a1b2c3d	62.0	71.0	67.4	0.0	pass	baseline	initial state
1	b2c3d4e	71.0	78.0	75.2	+7.8	pass	keep	add 4 trigger examples for edge case phrasing
2	-	68.0	74.0	71.6	-3.6	-	discard	rewrite body as numbered steps (hurt trigger)
3	-	-	-	-	-	-	crash	add MCP config (syntax error in plugin.json)
```

Columns: `iteration` (int), `commit` (short hash or `-`), `trigger` (float or `-`), `functional` (float or `-`), `combined` (float or `-`), `delta` (signed float or `-`), `guard` (`pass` | `fail` | `-`), `status` (`baseline` | `keep` | `discard` | `crash` | `no-op` | `hook-blocked`), `description` (string).

---

## Commands

### `/perfect-plugin` — Master Orchestrator

Runs: collect → build → optimize in sequence for new plugins. Reads `perfect-plugin.json` if it exists (resume mid-pipeline). Entry point for first-time use.

### `/perfect-plugin:collect`

1. Dialogue: captures NL use cases one at a time (open-ended description + expected behavior per case)
2. Dispatches `eval-generator` agent with the collected use cases
3. Agent produces `evals/trigger-eval.json` and `evals/evals.json` conforming to schemas above
4. Writes `perfect-plugin.json` with `use_cases` and `evals` fields populated

### `/perfect-plugin:build`

1. Reads `perfect-plugin.json` — platform, use cases, evals
2. Determines required components using YAGNI (only what use cases actually require)
3. Scaffolds plugin using plugin-forge schemas (see Plugin Structure above)
4. Runs `validate_plugin.py` — structural gate, fails fast if invalid
5. Runs `run_evals.py --baseline` → writes `history.baseline_score` and `best_score` to state
6. Initializes `perfect-plugin-results.tsv` with baseline row

### `/perfect-plugin:optimize`

Executes the 8-phase loop from `optimize-loop.md`. Reads stopping config from `perfect-plugin.json`. Stops when `combined_score >= scoring.threshold` OR `loop.current_iteration >= loop.max_iterations`, whichever first.

Can be re-run after `:collect` adds new use cases.

### `/perfect-plugin:convert`

1. Reads the existing CC plugin
2. Runs `run_evals.py` on current state → stores as `convert.original_score` in state file
3. Dispatches `cowork-converter` agent to apply conversion checklist (see below)
4. Runs `validate_plugin.py` on result
5. Runs `run_evals.py` again → compares to `convert.original_score`
6. If score dropped more than 5 points: reports per-component delta and which components need attention. Does NOT auto-revert — reports to developer.
7. If score within 5 points: reports success

---

## Optimize Loop (8 Phases)

Full protocol in `references/optimize-loop.md`. Summary:

**Phase 0 — Preconditions:**
```bash
git rev-parse --git-dir          # fail fast if not a git repo
git status --porcelain           # fail if dirty working tree
python validate_plugin.py ./     # structural gate
python run_evals.py --baseline   # establish baseline, write to state + TSV
```

**Phase 1 — Review (every iteration, mandatory):**
```bash
git log --oneline -20
git diff HEAD~1
tail -20 perfect-plugin-results.tsv
cat perfect-plugin.json
```
Read ALL plugin files. Dispatcher also reads the `analyzer` agent's output from the previous iteration (if any) to inform ideation. See Phase 5.1 below for when analyzer runs.

**Phase 2 — Ideate (priority order):**
1. Fix crashes / validation failures
2. Exploit successes (read `git diff HEAD~1`, try variants of what worked)
3. If trigger score is weak leg → target description/frontmatter
4. If functional score is weak leg → target body, references, agents
5. If both weak → structural change
6. 5+ consecutive discards → radical change (rewrite description, restructure SKILL.md)

Incorporates `analyzer` output from Phase 5.1 of the previous iteration as additional signal.

**Phase 3 — Modify (one atomic change):**

One-sentence test: if you need "and" to describe the change, split it.

| Atomic ✓ | Split ✗ |
|---|---|
| Add 3 trigger examples to description | Add examples AND rewrite body |
| Extract section to references/ | Extract AND add new agent |
| Rewrite agent instructions | Rewrite agent AND add hook |

**Note on transitional states:** All Phase 3 changes must leave the plugin in a structurally valid state (passing `validate_plugin.py`). Refactors that span multiple files must be completed atomically in a single phase. Mid-refactor commits that fail validation are not allowed — if a refactor cannot be completed in one Phase 3, break it into smaller atomic steps across multiple iterations.

**Phase 4 — Commit:**
```bash
git add skills/ agents/ references/   # never git add -A
git diff --cached --quiet             # verify something staged
git commit -m "experiment(skill): <one-sentence description>"
```
`validate_plugin.py` runs as guard before `run_evals.py`. If validation fails: log `hook-blocked`, revert staged changes, move to Phase 1.

**Phase 5 — Verify:**
```bash
python run_evals.py   # trigger + functional in parallel (dispatching-parallel-agents pattern)
python score.py       # weighted combined score, noise_floor check
```

**Phase 5.1 — Analyzer (only on "keep" decisions):**
After Phase 6 confirms a keep, dispatch `analyzer` agent with:
- The kept commit diff (`git diff HEAD~1`)
- The TSV delta
- The previous iteration's TSV row

Analyzer produces a brief insight: "trigger score +8.2 — adding 'I want to build' phrase matched developer intent vocabulary." This output is read during Phase 2 of the next iteration.

**Phase 6 — Decide:**
```
improved AND delta > noise_floor AND validation passes → KEEP
improved BUT validation fails → rework (max 2 attempts), then discard
same/worse → git revert HEAD --no-edit
crashed → fix if fixable (max 3 tries), else git revert HEAD --no-edit
```
Always prefer `git revert` over `git reset --hard` — preserves failed experiment in history.

**Phase 7 — Log:**
Append to TSV. Print summary every 10 iterations.

**Phase 8 — Repeat:**
Stop on `combined_score >= threshold` OR `current_iteration >= max_iterations`. Never ask user.

---

## Scoring

```
trigger_score    = (correct_trigger_queries / total_trigger_queries) × 100
functional_score = (assertions_passed / total_assertions) × 100
combined_score   = (trigger_score × 0.4) + (functional_score × 0.6)
```

`score.py` reads `run_evals.py` output JSON, applies weights from `perfect-plugin.json`, returns a single float. It also checks `noise_floor`: if `|combined - previous_best| < noise_floor`, returns `delta = 0` so Phase 6 treats it as "same."

Noise handling: `run_evals.py` runs evals `runs_per_eval` times (default 3), takes median score per eval. Reduces false keep/discard decisions from LLM eval variance.

Parallel execution: `run_evals.py` dispatches trigger and functional eval runners as independent subprocesses, merges results. Reduces wall-clock time per iteration.

---

## CC → Cowork Conversion Checklist

Owned by `cowork-converter` agent. Applied item by item:

| # | CC artifact | Cowork adaptation |
|---|---|---|
| 1 | `claude -p` CLI calls in scripts | Replace with inline eval logic or static JSON output |
| 2 | Browser display / live server in scripts | Use `--static` flag for HTML output |
| 3 | Interactive terminal prompts (stdin) | Replace with `AskUserQuestion` tool calls |
| 4 | Hardcoded absolute paths | Replace with `${CLAUDE_PLUGIN_ROOT}` |
| 5 | CLI-dependent hook commands | Rewrite as `prompt` type hooks |
| 6 | `commands/*.md` legacy format | Migrate to `skills/*/SKILL.md` format |
| 7 | `allowed-tools` lists missing Cowork tools | Audit and update tool lists |
| 8 | Browser-only MCP servers | Flag as incompatible, suggest alternatives |

After applying: run `validate_plugin.py`, then `run_evals.py` and compare to `convert.original_score`.

---

## Agents

### `eval-generator` (NEW)

Input: list of `{ id, description, expected_behavior }` from collect dialogue.
Output: `evals/trigger-eval.json` and `evals/evals.json` conforming to schemas above.

Knows good/bad assertion rules. Enforces 10–20 trigger queries, 60/40 positive/negative split.

### `grader` (ADAPTED from plugin-forge)

Input: eval prompt, expected_behavior, transcript path, output directory path.
Output: `grading.json` conforming to schema above.

Grades each expectation with pass/fail, evidence quote, and improvement suggestion.

### `analyzer` (ADAPTED from plugin-forge)

Input: git diff of kept commit, previous TSV row, current TSV row.
Output: one-paragraph insight on what specifically drove the score improvement.

Runs only after Phase 6 confirms a keep. Output is read at the start of the next iteration's Phase 2. Does not modify any files.

### `cowork-converter` (NEW)

Input: existing CC plugin directory.
Output: modified plugin files (applies conversion checklist in-place).

Works through checklist items sequentially, reports each change made, flags any items it cannot automatically resolve.

---

## Scripts

### `run_evals.py`

1. Reads `perfect-plugin.json` for eval paths, runs_per_eval
2. Spawns trigger eval runner (via `claude -p`) and functional eval runner (grader agent) in parallel
3. Runs each `runs_per_eval` times, takes median pass_rate
4. Aggregates into output JSON (schema above)
5. Writes grading.json files to `evals/transcripts/`

### `score.py`

Input: `run_evals.py` output JSON, previous best score, weights, noise_floor (all from `perfect-plugin.json`).
Output: `{ "combined": float, "delta": float, "is_improvement": bool }`.

### `validate_plugin.py`

Runs the 6 validation rules defined above. Exits 0 on pass, non-zero on any failure. Prints which rule failed. Adapted from plugin-forge `quick_validate.py`.

---

## Success Criteria

1. A developer can run `/perfect-plugin:collect` → `/perfect-plugin:build` → `/perfect-plugin:optimize` (with `Iterations: 10` for a bounded first run) and end with a git-tracked plugin with a TSV log showing score progression. Measurable: git log shows baseline commit + experiment commits; TSV exists with ≥1 keep.
2. The optimize loop runs without prompting the user between iterations until `combined_score >= threshold` OR `max_iterations` reached. Measurable: no `AskUserQuestion` calls in loop phases 1–8.
3. A converted CC plugin passes `validate_plugin.py` and `run_evals.py` scores within 5 points of `convert.original_score`. Measurable: `|post_convert_score - convert.original_score| ≤ 5`.
4. The TSV log has one row per iteration with all columns populated. Measurable: `wc -l perfect-plugin-results.tsv` equals `loop.current_iteration + 1` (baseline + iterations).

---

## Out of Scope

- Calling the `autoresearch` or `plugin-forge` plugins at runtime (knowledge is embedded, not delegated)
- Multi-platform builds (`platform: "both"`) — `"cowork"` or `"claude-code"` only
- Publishing to marketplace
- Claude.ai web support (requires `claude -p` for trigger evals)
- Multi-plugin optimization in one loop run
- Automatic marketplace submission after loop completes
