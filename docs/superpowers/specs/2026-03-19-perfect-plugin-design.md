# perfect-plugin — Design Spec

**Date:** 2026-03-19
**Status:** Approved (v3 — post second spec-review)

---

## Problem

Plugin developers building for Claude Cowork have no automated path from "here is what I want this plugin to do" to "here is a plugin that reliably does it." They write skills by intuition, have no benchmark to measure quality, and no feedback loop to improve trigger precision or functional correctness. Existing tools (plugin-forge, autoresearch) solve adjacent pieces but are not wired together.

---

## Goal

A distributable Claude Code plugin — `perfect-plugin` — that:

1. Converts natural-language use cases into structured evals (the benchmark)
2. Scaffolds an initial plugin skeleton from those evals
3. Runs an autonomous iteration loop improving the plugin against a combined eval score until a threshold or iteration limit is reached
4. Converts existing Claude Code plugins to Cowork-compatible versions with score verification

---

## Users

Plugin developers who know what a SKILL.md is. Power tool, not a beginner guide.

---

## Architecture — Reuse vs Re-implement

| Layer | Source | What is reused | What is re-implemented |
|---|---|---|---|
| Orchestration | superpowers-main | `dispatching-parallel-agents` pattern (behavioral reference only for parallel eval runs) | Nothing called at runtime |
| Iteration engine | autoresearch-master | 8-phase protocol, git-as-memory rules, TSV format, guard/noise/crash-recovery rules — copied verbatim into `optimize-loop.md` as the reference | Loop re-implemented inside `optimize-loop.md` with plugin-specific Phase 2 heuristics. Autoresearch plugin NOT called at runtime. |
| Plugin craft | plugin-forge | `grader.md` copied then trimmed to the schema defined below. `quick_validate.py` logic replicated in `validate_plugin.py` for rules 1–3. Eval file schemas and plugin.json schema reused. | `eval-generator.md`, `analyzer.md`, and `cowork-converter.md` are new agents (not adapted from plugin-forge — plugin-forge's analyzer is an A/B comparator with incompatible inputs). `run_evals.py`, `score.py`, `validate_plugin.py` rules 4–6 are new. |

**At runtime:** `perfect-plugin` is self-contained. It does not call autoresearch or plugin-forge at runtime.

---

## Plugin Structure

```
perfect-plugin/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   └── perfect-plugin/
│       ├── SKILL.md                       ← env detection + command routing
│       ├── references/                    ← 6 files total:
│       │   ├── collect-workflow.md        ← (1) NL → eval generation dialogue protocol
│       │   ├── build-workflow.md          ← (2) evals → plugin scaffold spec
│       │   ├── optimize-loop.md           ← (3) 8-phase loop (adapted from autoresearch)
│       │   ├── convert-workflow.md        ← (4) CC → Cowork adaptation checklist
│       │   ├── scoring.md                 ← (5) combined score formula + noise handling
│       │   └── state-schema.md            ← (6) perfect-plugin.json full field spec
│       ├── agents/
│       │   ├── eval-generator.md          ← NEW: NL use cases → eval files
│       │   ├── grader.md                  ← TRIMMED from plugin-forge (schema below)
│       │   ├── analyzer.md                ← NEW: git diff + TSV rows → insight file
│       │   └── cowork-converter.md        ← NEW: CC → Cowork adaptation
│       └── scripts/
│           ├── run_evals.py               ← NEW: orchestrates all eval execution
│           ├── score.py                   ← NEW: weighted score + noise check
│           └── validate_plugin.py         ← PARTIAL: rules 1–3 from plugin-forge quick_validate.py; rules 4–6 new
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

Lives at the root of the **target plugin** directory. All relative paths resolve from `plugin_path`. Persists across session interruptions.

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

**Field notes:**
- `platform`: `"cowork"` or `"claude-code"` only. Multi-platform out of scope.
- `loop.status = "crashed"`: set when the last run terminated abnormally, enabling deterministic resumption.
- `history.best_commit`: written at Phase 6 whenever a new best score is achieved (`git rev-parse --short HEAD`). Read during crash recovery to restore best known state.
- `convert.original_score`: stores pre-conversion combined score for the 5-point acceptance criterion.
- `use_cases[].id`: human-traceability only. Not consumed by scripts or agents.

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
    "query": "string — adjacent, genuinely ambiguous query",
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
    "prompt": "string — exact prompt to run against the skill",
    "input_files": ["optional/relative/path/to/sample.txt"],
    "expectations": [
      "string — verifiable assertion (structural, content-presence, accuracy)"
    ],
    "notes": "string — optional context for the grader"
  }
]
```

Good expectations: "Output contains exactly 3 sections: Summary, Risks, Recommendations."
Bad expectations: "Output looks reasonable", "Claude used the skill", "Output is helpful."

`input_files`: paths relative to `plugin_path`. `run_evals.py` passes these as context to the `claude -p` invocation for the eval prompt.

---

## `run_evals.py` — Full Execution Path

**Invocation convention:** `run_evals.py` must always be invoked with the target plugin root as the
current working directory. It reads `./perfect-plugin.json` (always relative to cwd). All paths
in `perfect-plugin.json` are relative to that same cwd. The loop commands (Phase 0, 4, 5) must
`cd` to the plugin root before calling any script.

`run_evals.py` is the central orchestrator. Full flow:

```
1. Read ./perfect-plugin.json → get eval paths, runs_per_eval, plugin_path, scoring config
   Read history.best_score from perfect-plugin.json → this is previous_best for score.py
   Null-coercion: if history.best_score is null (state file freshly created), treat previous_best = 0

2. Run trigger and functional branches IN PARALLEL (two subprocesses)

TRIGGER BRANCH — how trigger detection works:
  skill_name is read from the target plugin's SKILL.md frontmatter `name:` field before the loop starts.

  Detection mechanism: each trigger query is augmented with a meta-instruction appended after
  the query text (via a system prompt flag, NOT visible in the query content):
    System addition: "After completing your response, on a new line write exactly:
    SKILL_USED: <skill-name-you-used> or SKILL_USED: none"

  run_evals.py reads `skill_name` from SKILL.md and appends this system instruction.
  After receiving Claude's response, it searches the final line for "SKILL_USED: {skill_name}"
  (case-insensitive). This mechanism works regardless of whether superpowers is installed.

  For each run in 1..runs_per_eval:
    For each entry in trigger-eval.json:
      Run: claude -p "<query>" --plugin <plugin_path> \
           --system "After completing your response, on a new line write: SKILL_USED: <skill-name> or SKILL_USED: none"
      Capture full stdout transcript
      Detect trigger: search last 3 lines for "SKILL_USED: {skill_name}" (case-insensitive)
        If found → triggered = true
        If not found → triggered = false
      did_trigger_correctly = (triggered == entry.should_trigger)
  Per query: compute pass_rate = count(did_trigger_correctly) / runs_per_eval
  trigger_score = (queries where pass_rate >= 0.5) / total_queries × 100

FUNCTIONAL BRANCH — evals are transcript-only (no output file artefacts):
  input_files in evals.json provide INPUT context to the eval prompt; they are not output artefacts.
  Functional evals also run runs_per_eval times (same value as trigger evals).

  run_evals.py handles transcript generation only. Grader dispatch is handled by Claude
  (the main session), NOT by the Python script, because Claude agents cannot be spawned
  from Python subprocesses. The split is:

  run_evals.py Step 2 (functional — transcript generation):
    For each run in 1..runs_per_eval:
      For each eval in evals.json:
        context_flags = ["--context " + f for f in eval.input_files]  # may be empty
        Run: claude -p "<eval.prompt>" --plugin <plugin_path> <context_flags>
        Save transcript to: evals/transcripts/eval-{id}-run-{n}.md
    Write evals/transcripts-to-grade.json: list of {eval_id, expectations, transcript_path, output_path}

  Write trigger results to evals/trigger-results.json (survives between process invocations):
  ```json
  {
    "skill_name": "target-plugin-name",
    "runs_per_eval": 3,
    "queries": [
      {
        "query": "string",
        "should_trigger": true,
        "results": [true, false, true],
        "pass_rate_q": 0.67
      }
    ],
    "total_queries": 15
  }
  ```
  Exit (both files written; Claude will dispatch graders then call --score)

  Idempotency: `--generate-transcripts` always overwrites existing transcripts and re-writes
  both evals/transcripts-to-grade.json and evals/trigger-results.json. This makes it safe to
  re-run on crash recovery (crash between --generate-transcripts and --score → simply re-run
  --generate-transcripts, re-dispatch graders, then --score).

  Claude (main session) Step 2b — grader dispatch:
    Read evals/transcripts-to-grade.json
    For each entry: dispatch grader agent with {eval_id, expectations, transcript_path, output_path}
    Wait for all graders to complete (all grading.json files exist)

  run_evals.py Step 3 — score computation (called again by Claude after graders complete):
    Re-read evals/transcripts-to-grade.json to get the list of output_path values
    Re-read evals/trigger-results.json to get trigger query results
    For each eval: read grading.json at the output_path listed in transcripts-to-grade.json
    Compute per-eval median: median(grading.summary.pass_rate across all N runs for that eval)
    functional_score = average(per-eval medians) × 100
    (i.e., average the per-eval medians across all evals, not a flat average across all runs)
    Call score.py (step 3 below)

3. Call score.py (subprocess):
   echo '{"trigger_score": X, "functional_score": Y, "previous_best": Z,
          "weights": {"trigger": 0.4, "functional": 0.6}, "noise_floor": 2.0}' | python score.py
   Receives JSON on stdout: {combined, delta, is_improvement}
   previous_best = history.best_score read from perfect-plugin.json in step 1
   weights and noise_floor read from perfect-plugin.json scoring config

4. Output JSON written to evals/last-run.json (schema below)

**run_evals.py supports two modes plus one modifier:**
- `--generate-transcripts`: runs claude -p for trigger queries + eval prompts, writes
  evals/transcripts-to-grade.json and evals/trigger-results.json. Each entry in
  transcripts-to-grade.json includes the exact `output_path` where the grader MUST write
  its grading.json. This `output_path` is the canonical write destination and overrides
  any path convention from the source grader.md. Exits after writing both files.
- `--score`: reads grading.json files (paths from evals/transcripts-to-grade.json output_path
  fields) and evals/trigger-results.json, calls score.py via subprocess (stdin JSON → stdout
  JSON), outputs evals/last-run.json.
- `--baseline` (modifier for `--score` only): used as `python run_evals.py --score --baseline`.
  Behavior difference from plain `--score`:
    - Passes previous_best = 0 to score.py (ignores history.best_score)
    - score.py runs normally and returns {combined, delta, is_improvement}
    - run_evals.py then OVERRIDES delta and is_improvement before writing last-run.json:
        delta = 0.0, is_improvement = false (baseline has no prior score to beat)
    - Writes combined_score to BOTH history.baseline_score AND history.best_score in perfect-plugin.json
  Cannot be combined with --generate-transcripts.
```

### `run_evals.py` Output Schema

```json
{
  "trigger_score": 74.0,
  "functional_score": 81.0,
  "combined_score": 78.2,
  "delta": 7.8,
  "is_improvement": true,
  "runs": 3,
  "trigger_detail": {
    "passed": 11,
    "failed": 4,
    "total": 15,
    "failures": ["exact query strings that failed"]
  },
  "functional_detail": {
    "passed_evals": 3,
    "failed_evals": 1,
    "total_evals": 4,
    "pass_threshold": 0.5,
    "per_eval": [
      { "id": "eval-001", "median_pass_rate": 0.83 }
    ],
    "grading_paths": ["evals/transcripts/eval-001-run-1-grading.json"]
  }
}
```

---

## `grading.json` Schema (grader agent output)

Plugin-forge's `grader.md` is copied and trimmed. The source grader reads output files from an `outputs_dir` — this plugin removes that dependency because **evals are transcript-only**: `input_files` provide context to the eval prompt but the grader reads only the resulting transcript (not output artefacts). Fields removed from source: `execution_metrics`, `timing`, `claims`, `user_notes_summary`, `eval_feedback`, `outputs_dir`. The grader receives `transcript_path` and reads it directly.

Output path: `evals/transcripts/eval-{id}-run-{n}-grading.json` (set by `run_evals.py` when dispatching).

```json
{
  "eval_id": "eval-001",
  "run_id": "run-1",
  "transcript_path": "evals/transcripts/eval-001-run-1.md",
  "expectations": [
    {
      "text": "Output contains exactly 3 sections",
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

---

## `score.py`

Input (passed as arguments or stdin JSON):
```json
{
  "trigger_score": 74.0,
  "functional_score": 81.0,
  "previous_best": 67.4,
  "weights": { "trigger": 0.4, "functional": 0.6 },
  "noise_floor": 2.0
}
```

Output:
```json
{
  "combined": 78.2,
  "delta": 10.8,
  "is_improvement": true
}
```

Formula: `combined = (trigger × 0.4) + (functional × 0.6)`. `delta = combined - previous_best`. `is_improvement = delta > noise_floor`.

---

## `validate_plugin.py` — Rules and Scan Scope

Exits non-zero on any failure. Prints the failing rule name and the offending file/value.

**Scan scope:** All files in the plugin directory tree with extensions `.md`, `.json`, `.yaml`, `.toml`. Does not scan binary files or `node_modules/`.

| # | Rule | Source |
|---|---|---|
| 1 | `.claude-plugin/plugin.json` exists and has `"name"` field matching kebab-case pattern `^[a-z][a-z0-9-]*[a-z0-9]$` | From plugin-forge quick_validate.py |
| 2 | Every `skills/*/SKILL.md` has frontmatter with `name:` matching its parent directory name | From plugin-forge quick_validate.py |
| 3 | Every `description:` in frontmatter is under 1024 chars and contains no `<` or `>` | From plugin-forge quick_validate.py |
| 4 | Every agent file's `tools:` frontmatter field is a YAML sequence (not a comma-separated string) | New |
| 5 | No string matching `^/Users/`, `^C:\\`, `^/home/`, `^/root/` appears in any scanned file | New |
| 6 | If `hooks/hooks.json` exists: any path in `command` fields that references a plugin file must use `${CLAUDE_PLUGIN_ROOT}`. If `hooks/hooks.json` does not exist, Rule 6 passes silently. | New |

---

## TSV Log Schema

File: `perfect-plugin-results.tsv` (gitignored, at plugin root)

```tsv
# metric_direction: higher_is_better
iteration	commit	trigger	functional	combined	delta	validate	status	description
0	a1b2c3d	62.0	71.0	67.4	0.0	pass	baseline	initial state
1	b2c3d4e	71.0	78.0	75.2	+7.8	pass	keep	add 4 trigger examples for edge case phrasing
2	-	68.0	74.0	71.6	-3.6	-	discard	rewrite body as numbered steps (hurt trigger)
3	-	-	-	-	-	fail	validation-failed	SKILL.md description exceeded 1024 chars
4	-	-	-	-	-	-	crash	add MCP config (syntax error in plugin.json)
5	-	-	-	-	-	-	no-op	attempted change produced no diff
6	-	-	-	-	-	-	hook-blocked	git pre-commit hook rejected commit
```

**Column definitions:**
- `validate`: `pass` (validate_plugin.py passed), `fail` (validate_plugin.py failed), `-` (not run — crash or no-op before validation)
- `status` values: `baseline`, `keep`, `discard`, `validation-failed` (validate_plugin failed before eval ran), `crash`, `no-op`, `hook-blocked` (git pre-commit hook rejected commit — distinct from validate_plugin failure)
- Sentinel `-` in metric columns (`trigger`, `functional`, `combined`, `delta`): used when no eval ran

**Distinction between `validation-failed` and `hook-blocked`:** `validation-failed` = `validate_plugin.py` returned non-zero before the git commit. `hook-blocked` = git pre-commit hook (not validate_plugin.py) rejected the commit. These are separate scenarios with separate status labels.

---

## Commands

### `/perfect-plugin` — Master Orchestrator

Reads `perfect-plugin.json` if it exists (resume mid-pipeline). Otherwise runs collect → build → optimize in sequence. Entry point for first-time use.

### `/perfect-plugin:collect`

1. Dialogue: captures NL use cases one at a time (description + expected_behavior per case)
2. Dispatches `eval-generator` agent with the collected use cases
3. Agent produces `evals/trigger-eval.json` + `evals/evals.json` conforming to schemas above
4. Writes `perfect-plugin.json` with `use_cases` and `evals` fields. Creates file if missing.

### `/perfect-plugin:build` — Scaffold Spec

1. Reads `perfect-plugin.json` — platform, use cases, evals
2. Determines required components (YAGNI: only what the use cases actually need)
3. Produces a minimal skeleton:

   **`.claude-plugin/plugin.json`:**
   ```json
   { "name": "<target-dir-name-in-kebab-case>", "version": "0.1.0" }
   ```
   Plugin name = the target directory's base name, lowercased, spaces replaced with hyphens. Validated against kebab-case regex before writing.

   **`skills/<plugin-name>/SKILL.md`:**
   ```markdown
   ---
   name: <plugin-name>
   description: >
     <One-paragraph summary synthesized from use_cases[].expected_behavior.
      Includes trigger phrases derived from use_cases[].description.
      Formatted as: "Use this skill when [trigger phrases from use cases]. [Expected behaviors].">
   ---

   # <Plugin Name>

   [Placeholder body — the optimize loop will refine this content.]
   ```

   **`evals/`** — the files already written by `:collect` (trigger-eval.json + evals.json). No additional content generated here.

   Additional components (agents, references, hooks) only if a use case explicitly requires a multi-step workflow, external tool, or event-driven behavior.
4. Runs `validate_plugin.py` — structural gate. Fails fast with error if validation fails; no TSV created.
5. Runs `run_evals.py --generate-transcripts` → Claude dispatches graders → `run_evals.py --score --baseline`.
   Writes `history.baseline_score` and `history.best_score` to state file.
6. Initializes `perfect-plugin-results.tsv` with baseline row.

### `/perfect-plugin:optimize`

Executes the 8-phase loop from `optimize-loop.md`. Stops when `combined_score >= scoring.threshold` OR `loop.current_iteration >= loop.max_iterations`.

### `/perfect-plugin:convert`

**Precondition:** `evals/trigger-eval.json` and `evals/evals.json` must exist. If either is missing,
abort with: "Run `/perfect-plugin:collect` first to generate evals before converting." Do not proceed.

1. Runs `run_evals.py --generate-transcripts` → Claude dispatches graders → `run_evals.py --score`
   on the existing CC plugin → stores combined_score result as `convert.original_score` in state file
2. Dispatches `cowork-converter` agent → applies conversion checklist in-place
3. Runs `validate_plugin.py` on converted result.
   **If validate_plugin.py fails:** abort with error message: "Converted plugin failed validation.
   Files have been modified in-place — review changes with `git diff` and fix manually,
   or run `git checkout -- .` to discard all conversion changes." Do NOT auto-revert.
4. Runs `run_evals.py --generate-transcripts` → Claude dispatches graders → `run_evals.py --score` → compares to `convert.original_score`
5. **If score dropped ≤ 5 points:** report success. Print conversion summary table.
6. **If score dropped > 5 points:** print per-component report (format below). Do NOT auto-revert. This is advisory — the developer decides whether to accept the result or run `/perfect-plugin:optimize` to recover the lost score.

**Per-component report format (on failure):**

```
Conversion score drop: -8.3 points (original: 74.2, post-convert: 65.9)

Component deltas:
  trigger score:    62.0 → 58.0  (-4.0)  ← description may need Cowork-specific phrasing
  functional score: 81.0 → 71.5  (-9.5)  ← likely caused by items below

Unresolved checklist items (manual intervention needed):
  ✗ Item 1: Found 3 claude -p calls in scripts/run.py lines 42, 67, 103 — could not determine replacement (inline eval vs static JSON)
  ✗ Item 8: MCP server "my-browser-mcp" uses browser-only transport — no Cowork equivalent available

Recommendation: address the unresolved items above and re-run /perfect-plugin:optimize (Iterations: 10).
```

---

## Optimize Loop (8 Phases)

Full protocol in `references/optimize-loop.md`. Summary with all decisions resolved:

**Phase 0 — Preconditions:**
```bash
git rev-parse --git-dir                        # fail fast if not a git repo
git status --porcelain                         # fail if dirty working tree (uncommitted user work)
python validate_plugin.py ./                   # structural gate
python run_evals.py --generate-transcripts     # trigger + transcript generation
# Claude dispatches grader agents for each entry in evals/transcripts-to-grade.json
python run_evals.py --score --baseline         # establish baseline; write history.baseline_score + best_score
```
Writes baseline row to TSV. Sets `loop.status = "running"` in state file.

**Phase 1 — Review (every iteration, mandatory):**
```bash
git log --oneline -20
git diff HEAD~1
tail -20 perfect-plugin-results.tsv
cat perfect-plugin.json
cat evals/analyzer-insight.md    # read if file exists (written by Phase 5.1 of previous iteration)
```
Read ALL plugin files (SKILL.md, agents/, references/).

**Phase 2 — Ideate (priority order):**
1. Fix crashes / validation failures
2. Exploit successes: read `git diff HEAD~1`, try variants of what worked. Incorporate analyzer insight from `evals/analyzer-insight.md` as additional signal.
3. Trigger score is weak leg (< functional score) → target description/frontmatter
4. Functional score is weak leg → target body, references, agents
5. Both weak → structural change (add reference file, add agent, reorganize)
6. 5+ consecutive discards → radical: rewrite description from scratch, restructure SKILL.md

**Phase 3 — Modify (one atomic change):**
- One-sentence test: if you need "and" to describe it, split it.
- **Structural validity rule:** Every Phase 3 change must leave the plugin passing `validate_plugin.py`. If a refactor requires multiple file edits, complete all of them within the same phase as a single commit. No mid-refactor commits.

**Phase 4 — Commit:**
```bash
git add skills/ agents/ references/ .claude-plugin/ hooks/ commands/   # all plugin dirs; NEVER git add -A
git diff --cached --quiet             # if exit 0: no-op, log status=no-op and skip to Phase 1
python validate_plugin.py ./          # if fails: revert staged (git checkout -- .), log status=validation-failed, skip to Phase 1
git commit -m "experiment(skill): <one-sentence description>"
# if git commit fails due to a pre-existing git pre-commit hook in the repo
# (e.g. husky, pre-commit framework — NOT installed by perfect-plugin):
# log status=hook-blocked, skip to Phase 1
```

**Note:** `hook-blocked` refers to git pre-commit hooks already present in the target repo (e.g. configured by the developer). `perfect-plugin` does not install any git hooks. If `validate_plugin.py` fails (before the commit), the status is `validation-failed`, not `hook-blocked`.

**Phase 5 — Verify:**
```bash
python run_evals.py --generate-transcripts   # trigger queries + eval transcript generation
# Claude then dispatches grader agents for each entry in evals/transcripts-to-grade.json
python run_evals.py --score                  # reads grading.json + trigger-results.json, calls score.py
```
Output JSON written to `evals/last-run.json`.

**Phase 5.1 — Analyzer (runs immediately after Phase 5 verify, only when is_improvement=true):**

Before the keep/discard decision in Phase 6, if `is_improvement = true`: dispatch `analyzer` agent:
```
Analyze why this iteration improved the score.

git_diff: <output of git diff HEAD~1>
previous_row: <previous TSV row as string>
current_row: <current TSV row as string>

Write a 2–4 sentence insight explaining what specifically caused the score improvement.
Output ONLY the insight text. No headers. No JSON.
```

Agent writes its output to `evals/analyzer-insight.md` (plain text, overwritten each time). Phase 1 of the next iteration reads this file. The analyzer does not run on discard, crash, no-op, or validation-failed outcomes.

**Stale file behavior:** `evals/analyzer-insight.md` is intentionally NOT cleared on discard, crash, or no-op. It retains the insight from the most recent successful improvement. This is correct: the agent should still know what worked last time, even if subsequent iterations failed. The file is only overwritten when a new improvement occurs.

**Phase 6 — Decide:**
```
is_improvement = true (from run_evals.py output JSON field "is_improvement", set by score.py) → KEEP
  write history.best_score = combined_score to state file
  write history.best_commit = git rev-parse --short HEAD to state file
  increment loop.current_iteration

is_improvement = false → DISCARD
  git revert HEAD --no-edit
  if git revert conflicts: git revert --abort && git reset --hard HEAD~1
  increment loop.current_iteration

crashed (run_evals.py failed, OOM, timeout) → fix if fixable (max 3 tries), else treat as DISCARD
  increment loop.current_iteration

(validation-failed and no-op are handled in Phase 4 — do NOT increment current_iteration for these)

no-op infinite loop prevention: if 3 consecutive no-op rows appear in the TSV, treat the next
iteration as a forced crash (log status=crash, increment current_iteration) and apply Phase 2
rule 6 (radical change) at the next Phase 2. This escapes agent stuck states where every
proposed change produces no diff.
```

**Phase 7 — Log:**
Append to TSV. Every 10 iterations, print:
```
=== perfect-plugin Progress (iteration 10) ===
Baseline: 67.4 → Current best: 78.9 (+11.5)
Keeps: 4 | Discards: 5 | Crashes: 1
Last 5: keep, discard, discard, keep, discard
```

**Phase 8 — Repeat:**
If `combined_score >= threshold` OR `current_iteration >= max_iterations`: set `loop.status = "complete"`, print final summary, stop.
Otherwise: go to Phase 1. Never ask user.

On unexpected exit: set `loop.status = "crashed"` in state file.

---

## Scoring

**Canonical formulas (matching run_evals.py Execution Path):**

```
Per trigger query:
  pass_rate_q = count(did_trigger_correctly across all runs) / runs_per_eval
trigger_score = (queries where pass_rate_q >= 0.5) / total_queries × 100

Per functional eval:
  pass_rate_e = median(grading.summary.pass_rate across all runs)
functional_score = average(pass_rate_e for all evals) × 100

For last-run.json summary fields: an eval counts as "passed" if pass_rate_e >= 0.5, "failed" otherwise.
(This threshold applies only to the passed_evals/failed_evals summary counters — it does not affect
the functional_score calculation, which uses the continuous average of medians.)

combined_score = (trigger_score × 0.4) + (functional_score × 0.6)
```

The `pass_rate >= 0.5` threshold is canonical for trigger queries. For `runs_per_eval = 3` this requires ≥2 correct detections; for `runs_per_eval = 2` this requires both runs to be correct. Do not substitute a "median of binary values" formulation — use the threshold formula.

`score.py` receives `trigger_score` and `functional_score` already computed by `run_evals.py`. It applies weights and noise_floor. It does NOT re-compute medians or thresholds.

---

## CC → Cowork Conversion Checklist (cowork-converter agent)

| # | CC artifact detected | Cowork adaptation | Decision rule |
|---|---|---|---|
| 1 | `claude -p` in script with captured output fed to another process | Inline eval logic (rewrite as Python that calls Claude API directly) | Use inline if the output is parsed; use static JSON if the output is only displayed |
| 2 | `claude -p` with HTML/browser display | `--static` flag for HTML output | Always static |
| 3 | `input()`, `sys.stdin.read()`, interactive terminal prompts | `AskUserQuestion` tool call | Always |
| 4 | Absolute paths in any file | `${CLAUDE_PLUGIN_ROOT}` prefix | Always |
| 5 | `type: command` hooks with CLI binaries | `type: prompt` hooks | Always |
| 6 | `commands/*.md` legacy slash commands | Create equivalent `skills/*/SKILL.md` | Always |
| 7 | `tools: Read, Grep` (comma string) in agent frontmatter | `tools: ["Read", "Grep"]` (JSON array) | Always |
| 8 | MCP servers with browser-only transport | Flag as incompatible, add to unresolved items in report | Cannot auto-fix |

Items that cannot be auto-resolved are collected into the unresolved list and appear in the failure report.

---

## Agents

### `eval-generator` (NEW)

**Input prompt structure:**
```
Generate trigger and functional evals from these use cases:
use_cases: [{ id, description, expected_behavior }]
trigger_output_path: evals/trigger-eval.json
functional_output_path: evals/evals.json
```

**Output:** writes both files conforming to schemas above. Enforces 10–20 trigger entries, 60/40 split, verifiable assertions only.

### `grader` (TRIMMED from plugin-forge)

**Behavioral contract:** For each expectation string, the grader reads the transcript, searches for evidence that the expectation was or was not met, and records `passed: true/false` with a verbatim quote from the transcript as evidence. If no evidence is found, `passed: false` and `evidence: "Not found in transcript"`. The grader does not infer or hallucinate evidence — it only quotes.

**Input prompt structure:**
```
Grade this eval execution:
eval_id: eval-001
expectations: ["...", "..."]
transcript_path: evals/transcripts/eval-001-run-1.md
output_path: evals/transcripts/eval-001-run-1-grading.json

For each expectation:
1. Read the transcript at transcript_path
2. Search for evidence that the expectation was met or not met
3. Record passed (true/false) and a verbatim quote from the transcript as evidence
4. If no evidence found: passed=false, evidence="Not found in transcript"
Write results to output_path as JSON conforming to the grading.json schema.
```

**Output:** writes `grading.json` conforming to trimmed schema above. Source: plugin-forge grader.md logic retained for the core grade-per-expectation loop. Fields removed: execution_metrics, timing, claims, user_notes_summary, eval_feedback, outputs_dir.

### `analyzer` (NEW — not adapted from plugin-forge)

**Input:** git diff string + two TSV row strings (passed inline in prompt by loop, see Phase 5.1).
**Output:** plain text written to `evals/analyzer-insight.md`. No other file writes. No JSON.

### `cowork-converter` (NEW)

**Input prompt structure:**
```
Convert this Claude Code plugin to Cowork compatibility:
plugin_path: ./
checklist: [items 1-8 above]
report_path: evals/convert-report.md
```

**Output:** modifies plugin files in-place. Writes conversion report to `evals/convert-report.md` listing each checklist item: resolved, unresolved, or skipped.

---

## Scripts

### `run_evals.py`

Full execution path defined in the `run_evals.py` section above. Also supports `--baseline` flag which skips the improvement check in `score.py` and always writes the result as the baseline.

### `score.py`

Input: JSON with `trigger_score`, `functional_score`, `previous_best`, `weights`, `noise_floor`.
Output: JSON with `combined`, `delta`, `is_improvement`.
Logic: `combined = t×0.4 + f×0.6`. `delta = combined - previous_best`. `is_improvement = delta > noise_floor`.

### `validate_plugin.py`

6 rules defined above. Scans all `.md`, `.json`, `.yaml`, `.toml` files in the plugin tree. Exits non-zero on any failure, prints the failing rule name and offending file path/value.

---

## Success Criteria

1. `/collect` → `/build` → `/optimize` (Iterations: 10) produces a git-tracked plugin with a TSV log showing score progression. **Measurable:** `git log` shows baseline + experiment commits; `wc -l perfect-plugin-results.tsv` ≥ 2; TSV has ≥1 row with `status=keep`.
2. Optimize loop runs without `AskUserQuestion` in phases 1–8. **Measurable:** grep for `AskUserQuestion` in loop output = 0 matches.
3. Converted CC plugin passes `validate_plugin.py` and scores within 5 points of `convert.original_score`. **Measurable:** `|post_convert_score - convert.original_score| ≤ 5`.
4. Every phase produces exactly one TSV row. **Measurable:** `wc -l perfect-plugin-results.tsv` = 1 (baseline) + `loop.current_iteration` (keep/discard/crash) + count(validation-failed rows) + count(no-op rows) + count(hook-blocked rows). Note: `validation-failed`, `no-op`, and `hook-blocked` each produce a TSV row but do NOT increment `loop.current_iteration`.

---

## Out of Scope

- Runtime delegation to autoresearch or plugin-forge plugins
- `platform: "both"` — cowork or claude-code only, not simultaneous
- Publishing to marketplace
- Claude.ai web support (requires `claude -p`)
- Multi-plugin optimization in one loop run
