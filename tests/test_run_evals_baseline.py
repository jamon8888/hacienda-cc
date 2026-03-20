# hacienda-maker/tests/test_run_evals_baseline.py
import json
import subprocess
import sys
import tempfile
from pathlib import Path

RUN_EVALS_PY = Path(__file__).parent.parent / "skills/hacienda-maker/scripts/run_evals.py"


def setup_minimal(tmp: Path, best_score=None):
    state = {
        "scoring": {"weights": {"trigger": 0.4, "functional": 0.6},
                    "threshold": 85, "noise_floor": 2.0, "runs_per_eval": 3},
        "history": {"baseline_score": None, "best_score": best_score,
                    "best_commit": None, "results_log": "hacienda-maker-results.tsv"}
    }
    (tmp / "hacienda-maker.json").write_text(json.dumps(state))
    evals = tmp / "evals"
    evals.mkdir()
    (evals / "trigger-results.json").write_text(json.dumps({
        "queries": [{"query": "q", "should_trigger": True, "results": [True,True,True],
                     "pass_rate_q": 1.0}],
        "total_queries": 1
    }))
    (evals / "transcripts-to-grade.json").write_text("[]")


def run(tmp: Path, mode: list) -> dict:
    subprocess.run(
        [sys.executable, str(RUN_EVALS_PY)] + mode,
        capture_output=True, text=True, cwd=str(tmp), check=True
    )
    return json.loads((tmp / "hacienda-maker.json").read_text())


def test_baseline_writes_baseline_score(tmp_path):
    setup_minimal(tmp_path)
    state = run(tmp_path, ["--score", "--baseline"])
    assert state["history"]["baseline_score"] is not None


def test_baseline_writes_best_score_when_null(tmp_path):
    setup_minimal(tmp_path, best_score=None)
    state = run(tmp_path, ["--score", "--baseline"])
    assert state["history"]["best_score"] is not None


def test_baseline_does_not_overwrite_existing_best_score(tmp_path):
    setup_minimal(tmp_path, best_score=99.0)
    state = run(tmp_path, ["--score", "--baseline"])
    assert state["history"]["best_score"] == 99.0


def test_baseline_sets_delta_zero_and_is_improvement_false(tmp_path):
    setup_minimal(tmp_path, best_score=None)
    subprocess.run(
        [sys.executable, str(RUN_EVALS_PY), "--score", "--baseline"],
        capture_output=True, text=True, cwd=str(tmp_path), check=True
    )
    last_run = json.loads((tmp_path / "evals/last-run.json").read_text())
    assert last_run["delta"] == 0.0
    assert last_run["is_improvement"] is False
