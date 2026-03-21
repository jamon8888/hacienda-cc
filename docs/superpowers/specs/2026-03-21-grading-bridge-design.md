# Grading Bridge: `run_evals.py --grade`

**Date:** 2026-03-21
**Status:** Draft
**Scope:** Close the grading gap in hacienda-maker's eval pipeline

---

## Problem

The eval pipeline has three steps:

1. `run_evals.py --generate-transcripts` — runs claude -p, writes transcripts and `transcripts-to-grade.json`
2. _(gap)_ — reference docs say "dispatch grader agent for each entry" (a comment, not a script call)
3. `run_evals.py --score` — reads `grading.json` files, computes scores

Step 2 depends on the orchestrating Claude session interpreting a comment and manually dispatching N agent calls. If skipped, `--score` silently returns 0.0 for all functional evals because no grading files exist.

This gap makes the optimize loop unreliable — functional scores are meaningless if grading never happened.

---

## Solution

Add a `--grade` mode to `run_evals.py` that bridges the gap deterministically.

### Pipeline After Fix

```bash
python scripts/run_evals.py --generate-transcripts
python scripts/run_evals.py --grade
python scripts/run_evals.py --score [--baseline]
```

Three explicit script calls. No comments. No agent dispatch required.

---

## `--grade` Mode Specification

### Interface

```bash
python skills/hacienda-maker/scripts/run_evals.py --grade
```

Must be run from the target plugin directory (same as other modes).

### Behavior

1. Read `evals/transcripts-to-grade.json` — abort with error if missing.
2. For each entry in the manifest:
   a. Check if the output grading.json already exists and is valid JSON with a `summary.pass_rate` field. If so, skip (idempotent).
   b. Check if the transcript file exists. If missing, write a grading.json with `pass_rate: 0.0` and all expectations failed with evidence `"transcript missing"`.
   c. Otherwise, call `grader.py` via subprocess:
      ```bash
      python grader.py \
        --transcript <transcript_path> \
        --expectations '<json array>' \
        --output <output_path> \
        --eval-id <eval_id> \
        --run-n <run_n>
      ```
   d. If `grader.py` exits non-zero, write a grading.json with `pass_rate: 0.0` and evidence `"grader error"`.
3. Print summary to stdout: `Graded: N/M entries (X skipped, Y failed, Z succeeded)`

### Idempotency

Re-running `--grade` after a partial run grades only the missing entries. This makes the pipeline resumable after crashes.

### Error Handling

| Condition | Behavior |
|-----------|----------|
| `transcripts-to-grade.json` missing | Exit 1 with error message |
| Transcript file missing | Write grading.json with pass_rate=0.0, evidence="transcript missing" |
| `grader.py` exits non-zero | Write grading.json with pass_rate=0.0, evidence="grader error" |
| `grader.py` subprocess timeout (>300s) | Write grading.json with pass_rate=0.0, evidence="grader timeout" |
| Individual semantic call timeout (60s) | Handled by grader.py internally per expectation |
| Existing valid grading.json | Skip (no overwrite) |

---

## Files Modified

| File | Change |
|------|--------|
| `skills/hacienda-maker/scripts/run_evals.py` | Add `mode_grade()` function and `--grade` CLI flag |
| `skills/hacienda-maker/references/optimize-loop.md` | Replace comment with `python ... --grade` call |
| `skills/hacienda-maker/references/build-workflow.md` | Replace comment with `python ... --grade` call |
| `tests/test_run_evals_grade.py` | New test file (TDD) |

---

## `mode_grade()` Implementation

```python
def mode_grade(cwd: Path):
    evals_dir = cwd / "evals"
    ttg_path = evals_dir / "transcripts-to-grade.json"
    if not ttg_path.exists():
        print("Error: evals/transcripts-to-grade.json not found. Run --generate-transcripts first.", file=sys.stderr)
        sys.exit(1)

    entries = json.loads(ttg_path.read_text())
    grader_script = Path(__file__).parent / "grader.py"

    skipped = 0
    failed = 0
    succeeded = 0

    for entry in entries:
        output_path = cwd / entry["output_path"]

        # Idempotent: skip if already graded
        if output_path.exists():
            try:
                existing = json.loads(output_path.read_text())
                if isinstance(existing.get("summary", {}).get("pass_rate"), (int, float)):
                    skipped += 1
                    continue
            except (json.JSONDecodeError, KeyError):
                pass  # re-grade if malformed

        transcript_path = cwd / entry["transcript_path"]

        # Missing transcript → fail all expectations
        if not transcript_path.exists():
            write_failed_grading(output_path, entry, "transcript missing")
            failed += 1
            continue

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Call grader.py
        expectations_json = json.dumps(entry.get("expectations", []))
        try:
            result = subprocess.run(
                [sys.executable, str(grader_script),
                 "--transcript", str(transcript_path),
                 "--expectations", expectations_json,
                 "--output", str(output_path),
                 "--eval-id", entry["eval_id"],
                 "--run-n", str(entry["run_n"])],
                capture_output=True, text=True, timeout=300
            )
        except subprocess.TimeoutExpired:
            write_failed_grading(output_path, entry, "grader timeout")
            failed += 1
            continue

        if result.returncode != 0:
            write_failed_grading(output_path, entry, "grader error")
            failed += 1
        else:
            succeeded += 1

    total = len(entries)
    print(f"Graded: {total} entries ({succeeded} succeeded, {skipped} skipped, {failed} failed)")
```

### Helper: `write_failed_grading()`

```python
def write_failed_grading(output_path: Path, entry: dict, reason: str):
    expectations = entry.get("expectations", [])
    results = [{"text": e.get("text", ""), "type": e.get("type", "contains"),
                "grader_type": "llm" if e.get("type") == "semantic" else "deterministic",
                "passed": False, "evidence": reason}
               for e in expectations]
    total = len(results)
    grading = {
        "eval_id": entry["eval_id"],
        "run_id": f"run-{entry['run_n']}",
        "transcript_path": entry["transcript_path"],
        "expectations": results,
        "summary": {"passed": 0, "failed": total, "total": total, "pass_rate": 0.0}
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(grading, indent=2))
```

---

## `main()` Update

Replace the existing dispatch in `run_evals.py`:

```python
def main():
    args = sys.argv[1:]
    cwd = Path.cwd()

    if "--generate-transcripts" in args:
        mode_generate_transcripts(cwd)
    elif "--grade" in args:
        mode_grade(cwd)
    elif "--score" in args:
        mode_score(cwd, baseline="--baseline" in args)
    else:
        print("Usage: run_evals.py --generate-transcripts | --grade | --score [--baseline]", file=sys.stderr)
        sys.exit(1)
```

---

## Reference Doc Updates

### `optimize-loop.md` — Phase 0 and Phase 5

Replace:
```bash
python skills/hacienda-maker/scripts/run_evals.py --generate-transcripts
# dispatch grader agent for each entry in evals/transcripts-to-grade.json
python skills/hacienda-maker/scripts/run_evals.py --score --baseline
```

With:
```bash
python skills/hacienda-maker/scripts/run_evals.py --generate-transcripts
python skills/hacienda-maker/scripts/run_evals.py --grade
python skills/hacienda-maker/scripts/run_evals.py --score --baseline
```

Same change in Phase 5 (without `--baseline`).

### `build-workflow.md` — Step 5

Same replacement.

---

## Tests (TDD — RED first)

### `tests/test_run_evals_grade.py`

```python
test_grade_writes_grading_files
    # Setup: transcripts-to-grade.json with 2 entries, transcript files exist, expectations are deterministic
    # Assert: both grading.json files written with valid schema

test_grade_skips_existing_valid_grading
    # Setup: one entry already has a valid grading.json
    # Assert: that file is not overwritten, summary shows "1 skipped"

test_grade_handles_missing_transcript
    # Setup: transcript file does not exist
    # Assert: grading.json written with pass_rate=0.0, evidence="transcript missing"

test_grade_handles_grader_error
    # Setup: patch subprocess.run to return non-zero for grader.py calls
    # Assert: grading.json written with pass_rate=0.0, evidence="grader error"

test_grade_missing_manifest_exits_1
    # Setup: no transcripts-to-grade.json
    # Assert: exit code 1

test_grade_idempotent_rerun
    # Setup: run --grade twice with same data
    # Assert: second run skips all, no files modified

test_grade_semantic_expectation_uses_llm_grader_type_on_failure
    # Setup: entry with type=semantic, transcript missing
    # Assert: grading.json has grader_type="llm" (not "deterministic")

test_grade_timeout_writes_failed_grading
    # Setup: patch subprocess.run to raise TimeoutExpired
    # Assert: grading.json written with pass_rate=0.0, evidence="grader timeout"
```

---

## Non-Included (Out of Scope)

- Loop resilience (script-managed loop.status, no_op_streak)
- Validation polish (Rule 5, French prompt, score.py inlining)
- Convert revert path
- End-to-end integration tests of the full optimize loop
