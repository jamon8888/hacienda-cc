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
