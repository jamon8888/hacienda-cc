# Grading Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--grade` mode to `run_evals.py` that automatically calls `grader.py` for each transcript, closing the gap between `--generate-transcripts` and `--score`.

**Architecture:** New `mode_grade()` function + `write_failed_grading()` helper in `run_evals.py`. Reads the `transcripts-to-grade.json` manifest, calls `grader.py` per entry via subprocess, writes grading.json files. Idempotent — skips already-graded entries.

**Tech Stack:** Python 3.13, pytest, subprocess, json (stdlib only)

**Spec:** `docs/superpowers/specs/2026-03-21-grading-bridge-design.md`

**Python executable:** `/c/Users/NMarchitecte/AppData/Local/Programs/Python/Python313/python.exe`

**Test command pattern:** `cd /c/Users/NMarchitecte/Documents/cc-cowork/hacienda-maker && /c/Users/NMarchitecte/AppData/Local/Programs/Python/Python313/python.exe -m pytest tests/<file> -v`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `hacienda-maker/skills/hacienda-maker/scripts/run_evals.py` | Modify | Add `write_failed_grading()`, `mode_grade()`, update `main()` |
| `hacienda-maker/tests/test_run_evals_grade.py` | Create | All tests for `--grade` mode |
| `hacienda-maker/skills/hacienda-maker/references/optimize-loop.md` | Modify | Replace grader comment with `--grade` call |
| `hacienda-maker/skills/hacienda-maker/references/build-workflow.md` | Modify | Replace grader comment with `--grade` call |

---

## Task 1: RED — Write ALL failing tests for `--grade` mode

**Files:**
- Create: `hacienda-maker/tests/test_run_evals_grade.py`

All 8 tests go in this task so every test is RED before any implementation.

- [ ] **Step 1: Create test file with ALL tests**

Create `hacienda-maker/tests/test_run_evals_grade.py`:

```python
# hacienda-maker/tests/test_run_evals_grade.py
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "skills/hacienda-maker/scripts"))
import run_evals

RUN_EVALS_PY = Path(__file__).parent.parent / "skills/hacienda-maker/scripts/run_evals.py"


def make_manifest(tmp: Path, entries: list):
    evals_dir = tmp / "evals"
    evals_dir.mkdir(exist_ok=True)
    (evals_dir / "transcripts-to-grade.json").write_text(json.dumps(entries))


def make_transcript(tmp: Path, eval_id: str, run_n: int, content: str = "Some transcript text with GDPR mention."):
    path = tmp / f"evals/transcripts/{eval_id}-run-{run_n}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return str(path.relative_to(tmp))


def make_entry(eval_id: str, run_n: int, expectations: list = None):
    if expectations is None:
        expectations = [{"text": "GDPR", "type": "contains"}]
    return {
        "eval_id": eval_id,
        "run_n": run_n,
        "expectations": expectations,
        "transcript_path": f"evals/transcripts/{eval_id}-run-{run_n}.md",
        "output_path": f"evals/transcripts/{eval_id}-run-{run_n}-grading.json",
    }


def run_grade_mode(tmp: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(RUN_EVALS_PY), "--grade"],
        capture_output=True, text=True, cwd=str(tmp)
    )
    return result.returncode, result.stdout


def test_grade_missing_manifest_exits_1():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        code, out = run_grade_mode(tmp)
        assert code == 1


def test_grade_handles_missing_transcript():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        entry = make_entry("eval-001", 1)
        make_manifest(tmp, [entry])
        # No transcript file created
        code, out = run_grade_mode(tmp)
        assert code == 0
        grading_path = tmp / entry["output_path"]
        assert grading_path.exists()
        grading = json.loads(grading_path.read_text())
        assert grading["summary"]["pass_rate"] == 0.0
        assert grading["expectations"][0]["evidence"] == "transcript missing"


def test_grade_semantic_expectation_uses_llm_grader_type_on_failure():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        entry = make_entry("eval-001", 1, expectations=[{"text": "tone is neutral", "type": "semantic"}])
        make_manifest(tmp, [entry])
        # No transcript → triggers write_failed_grading
        code, out = run_grade_mode(tmp)
        assert code == 0
        grading = json.loads((tmp / entry["output_path"]).read_text())
        assert grading["expectations"][0]["grader_type"] == "llm"
        assert grading["expectations"][0]["type"] == "semantic"


def test_grade_writes_grading_files():
    """Happy path: transcripts exist, deterministic expectations, grading.json written."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        entry1 = make_entry("eval-001", 1, [{"text": "GDPR", "type": "contains"}])
        entry2 = make_entry("eval-001", 2, [{"text": "GDPR", "type": "contains"}])
        make_manifest(tmp, [entry1, entry2])
        make_transcript(tmp, "eval-001", 1, "This mentions GDPR compliance.")
        make_transcript(tmp, "eval-001", 2, "This also mentions GDPR rules.")
        code, out = run_grade_mode(tmp)
        assert code == 0
        for entry in [entry1, entry2]:
            grading_path = tmp / entry["output_path"]
            assert grading_path.exists(), f"Missing {entry['output_path']}"
            grading = json.loads(grading_path.read_text())
            assert "summary" in grading
            assert isinstance(grading["summary"]["pass_rate"], (int, float))
            assert grading["eval_id"] == entry["eval_id"]


def test_grade_skips_existing_valid_grading():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        entry = make_entry("eval-001", 1)
        make_manifest(tmp, [entry])
        make_transcript(tmp, "eval-001", 1)
        # Pre-create a valid grading.json
        grading_path = tmp / entry["output_path"]
        grading_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {"eval_id": "eval-001", "run_id": "run-1",
                    "summary": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0},
                    "expectations": []}
        grading_path.write_text(json.dumps(existing))
        mtime_before = grading_path.stat().st_mtime
        code, out = run_grade_mode(tmp)
        assert code == 0
        assert "1 skipped" in out
        mtime_after = grading_path.stat().st_mtime
        assert mtime_before == mtime_after, "File should not be modified"


def test_grade_idempotent_rerun():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        entry = make_entry("eval-001", 1)
        make_manifest(tmp, [entry])
        make_transcript(tmp, "eval-001", 1)
        # First run
        code1, out1 = run_grade_mode(tmp)
        assert code1 == 0
        assert "1 succeeded" in out1
        # Second run
        code2, out2 = run_grade_mode(tmp)
        assert code2 == 0
        assert "1 skipped" in out2
        assert "0 succeeded" in out2


def test_grade_handles_grader_error(tmp_path):
    """When grader.py exits non-zero, write failed grading."""
    entry = make_entry("eval-001", 1, [{"text": "something", "type": "contains"}])
    make_manifest(tmp_path, [entry])
    make_transcript(tmp_path, "eval-001", 1)

    def fake_run(cmd, **kwargs):
        if "grader.py" in str(cmd):
            return type("r", (), {"returncode": 1, "stdout": "", "stderr": "error"})()
        return subprocess.run(cmd, **kwargs)

    with patch("run_evals.subprocess.run", side_effect=fake_run):
        run_evals.mode_grade(tmp_path)
    grading = json.loads((tmp_path / entry["output_path"]).read_text())
    assert grading["summary"]["pass_rate"] == 0.0
    assert grading["expectations"][0]["evidence"] == "grader error"


def test_grade_timeout_writes_failed_grading(tmp_path):
    """When grader.py subprocess times out, write failed grading."""
    entry = make_entry("eval-001", 1, [{"text": "something", "type": "contains"}])
    make_manifest(tmp_path, [entry])
    make_transcript(tmp_path, "eval-001", 1)

    def fake_run(cmd, **kwargs):
        if "grader.py" in str(cmd):
            raise subprocess.TimeoutExpired(cmd, 300)
        return subprocess.run(cmd, **kwargs)

    with patch("run_evals.subprocess.run", side_effect=fake_run):
        run_evals.mode_grade(tmp_path)
    grading = json.loads((tmp_path / entry["output_path"]).read_text())
    assert grading["summary"]["pass_rate"] == 0.0
    assert grading["expectations"][0]["evidence"] == "grader timeout"
```

- [ ] **Step 2: Run ALL tests to verify they fail**

Run: `cd /c/Users/NMarchitecte/Documents/cc-cowork/hacienda-maker && /c/Users/NMarchitecte/AppData/Local/Programs/Python/Python313/python.exe -m pytest tests/test_run_evals_grade.py -v`

Expected: Most tests FAIL — `mode_grade` and `write_failed_grading` don't exist yet. `test_grade_missing_manifest_exits_1` may pass since current `main()` exits 1 for unknown flags.

- [ ] **Step 3: Commit RED tests**

```bash
git add hacienda-maker/tests/test_run_evals_grade.py
git commit -m "test: add failing tests for run_evals.py --grade mode (RED)"
```

---

## Task 2: GREEN — Implement `write_failed_grading()` and `mode_grade()` and `main()` update

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/scripts/run_evals.py`

- [ ] **Step 1: Add `write_failed_grading()` helper**

Add before `mode_score()` in `run_evals.py` (around line 22, after `write_state`):

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

- [ ] **Step 2: Add `mode_grade()` function**

Add after `mode_generate_transcripts()`, before `main()`:

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

- [ ] **Step 3: Update `main()` dispatch**

Find the existing `def main():` function and replace it entirely with:

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


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run ALL tests to verify GREEN**

Run: `cd /c/Users/NMarchitecte/Documents/cc-cowork/hacienda-maker && /c/Users/NMarchitecte/AppData/Local/Programs/Python/Python313/python.exe -m pytest tests/test_run_evals_grade.py -v`

Expected: All 8 tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `cd /c/Users/NMarchitecte/Documents/cc-cowork/hacienda-maker && /c/Users/NMarchitecte/AppData/Local/Programs/Python/Python313/python.exe -m pytest tests/ -v`

Expected: All tests PASS (56 existing + 8 new = 64).

- [ ] **Step 6: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/scripts/run_evals.py
git commit -m "feat: add run_evals.py --grade mode with write_failed_grading helper (GREEN)"
```

---

## Task 3: Update reference docs

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/references/optimize-loop.md:7-14`
- Modify: `hacienda-maker/skills/hacienda-maker/references/optimize-loop.md:57-61`
- Modify: `hacienda-maker/skills/hacienda-maker/references/build-workflow.md:17-21`

- [ ] **Step 1: Update optimize-loop.md Phase 0**

In `hacienda-maker/skills/hacienda-maker/references/optimize-loop.md`, replace lines 7-14:

```bash
git rev-parse HEAD          # record starting commit
git status                  # confirm clean working tree
python skills/hacienda-maker/scripts/validate_plugin.py .
python skills/hacienda-maker/scripts/run_evals.py --generate-transcripts
# dispatch grader agent for each entry in evals/transcripts-to-grade.json
python skills/hacienda-maker/scripts/run_evals.py --score --baseline
```

With:

```bash
git rev-parse HEAD          # record starting commit
git status                  # confirm clean working tree
python skills/hacienda-maker/scripts/validate_plugin.py .
python skills/hacienda-maker/scripts/run_evals.py --generate-transcripts
python skills/hacienda-maker/scripts/run_evals.py --grade
python skills/hacienda-maker/scripts/run_evals.py --score --baseline
```

- [ ] **Step 2: Update optimize-loop.md Phase 5**

Replace lines 57-61:

```bash
python skills/hacienda-maker/scripts/run_evals.py --generate-transcripts
# dispatch grader agent for each entry in evals/transcripts-to-grade.json
python skills/hacienda-maker/scripts/run_evals.py --score
```

With:

```bash
python skills/hacienda-maker/scripts/run_evals.py --generate-transcripts
python skills/hacienda-maker/scripts/run_evals.py --grade
python skills/hacienda-maker/scripts/run_evals.py --score
```

- [ ] **Step 3: Update build-workflow.md Step 5**

Replace lines 17-21:

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

- [ ] **Step 4: Run full test suite to verify nothing broke**

Run: `cd /c/Users/NMarchitecte/Documents/cc-cowork/hacienda-maker && /c/Users/NMarchitecte/AppData/Local/Programs/Python/Python313/python.exe -m pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/references/optimize-loop.md hacienda-maker/skills/hacienda-maker/references/build-workflow.md
git commit -m "docs: replace grader agent comment with explicit --grade call in reference docs"
```
