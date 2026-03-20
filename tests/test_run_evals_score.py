# hacienda-maker/tests/test_run_evals_score.py
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from statistics import median

RUN_EVALS_PY = Path(__file__).parent.parent / "skills/hacienda-maker/scripts/run_evals.py"
SCORE_PY = Path(__file__).parent.parent / "skills/hacienda-maker/scripts/score.py"


def make_state(tmp: Path, best_score=None):
    state = {
        "scoring": {"weights": {"trigger": 0.4, "functional": 0.6},
                    "threshold": 85, "noise_floor": 2.0, "runs_per_eval": 3},
        "history": {"baseline_score": None, "best_score": best_score,
                    "best_commit": None, "results_log": "hacienda-maker-results.tsv"}
    }
    (tmp / "hacienda-maker.json").write_text(json.dumps(state))
    return state


def make_trigger_results(tmp: Path, queries: list):
    data = {"skill_name": "test-skill", "runs_per_eval": 3, "queries": queries,
            "total_queries": len(queries)}
    evals_dir = tmp / "evals"
    evals_dir.mkdir(exist_ok=True)
    (evals_dir / "trigger-results.json").write_text(json.dumps(data))


def make_grading(tmp: Path, eval_id: str, run_n: int, pass_rate: float):
    grading = {"eval_id": eval_id, "run_id": f"run-{run_n}",
               "summary": {"passed": int(pass_rate * 4), "failed": int((1-pass_rate)*4),
                            "total": 4, "pass_rate": pass_rate}}
    path = tmp / f"evals/transcripts/{eval_id}-run-{run_n}-grading.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(grading))
    return str(path.relative_to(tmp))


def make_transcripts_to_grade(tmp: Path, entries: list):
    (tmp / "evals").mkdir(exist_ok=True)
    (tmp / "evals/transcripts-to-grade.json").write_text(json.dumps(entries))


def run_score_mode(tmp: Path) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, str(RUN_EVALS_PY), "--score"],
        capture_output=True, text=True, cwd=str(tmp)
    )
    if result.returncode != 0:
        return result.returncode, {}
    return 0, json.loads((tmp / "evals/last-run.json").read_text())


def test_trigger_score_computed_from_pass_rate():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        make_state(tmp, best_score=0.0)
        queries = [
            {"query": f"q{i}", "should_trigger": True, "results": [True,True,True], "pass_rate_q": 1.0}
            for i in range(8)
        ] + [
            {"query": f"q{8+i}", "should_trigger": True, "results": [False,False,False], "pass_rate_q": 0.0}
            for i in range(2)
        ]
        make_trigger_results(tmp, queries)
        make_transcripts_to_grade(tmp, [])
        code, out = run_score_mode(tmp)
        assert code == 0
        assert out["trigger_score"] == 80.0  # 8/10 * 100


def test_functional_score_median_then_average():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        make_state(tmp, best_score=0.0)
        make_trigger_results(tmp, [])
        # eval-001: 3 runs with pass_rates 0.5, 0.75, 1.0 → median = 0.75
        # eval-002: 3 runs with pass_rates 0.25, 0.5, 0.75 → median = 0.5
        # functional_score = average([0.75, 0.5]) * 100 = 62.5
        entries = []
        for run_n, pr in enumerate([0.5, 0.75, 1.0], 1):
            p = make_grading(tmp, "eval-001", run_n, pr)
            entries.append({"eval_id": "eval-001", "run_n": run_n, "expectations": [],
                             "transcript_path": "", "output_path": p})
        for run_n, pr in enumerate([0.25, 0.5, 0.75], 1):
            p = make_grading(tmp, "eval-002", run_n, pr)
            entries.append({"eval_id": "eval-002", "run_n": run_n, "expectations": [],
                             "transcript_path": "", "output_path": p})
        make_transcripts_to_grade(tmp, entries)
        code, out = run_score_mode(tmp)
        assert code == 0
        assert abs(out["functional_score"] - 62.5) < 0.01


def test_combined_score_weighted():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        make_state(tmp, best_score=0.0)
        queries = [{"query": "q", "should_trigger": True, "results": [True,True,True], "pass_rate_q": 1.0}]
        make_trigger_results(tmp, queries)
        p = make_grading(tmp, "eval-001", 1, 1.0)
        p2 = make_grading(tmp, "eval-001", 2, 1.0)
        p3 = make_grading(tmp, "eval-001", 3, 1.0)
        entries = [
            {"eval_id": "eval-001", "run_n": 1, "expectations": [], "transcript_path": "", "output_path": p},
            {"eval_id": "eval-001", "run_n": 2, "expectations": [], "transcript_path": "", "output_path": p2},
            {"eval_id": "eval-001", "run_n": 3, "expectations": [], "transcript_path": "", "output_path": p3},
        ]
        make_transcripts_to_grade(tmp, entries)
        code, out = run_score_mode(tmp)
        assert code == 0
        assert out["combined_score"] == 100.0  # 100*0.4 + 100*0.6

def test_passed_evals_threshold_0_5():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        make_state(tmp, best_score=0.0)
        make_trigger_results(tmp, [])
        # eval-001 median = 0.6 (passes), eval-002 median = 0.4 (fails)
        for run_n, pr in enumerate([0.6, 0.6, 0.6], 1):
            make_grading(tmp, "eval-001", run_n, pr)
        entries_1 = [{"eval_id": "eval-001", "run_n": i, "expectations": [], "transcript_path": "",
                       "output_path": str((tmp / f"evals/transcripts/eval-001-run-{i}-grading.json").relative_to(tmp))}
                      for i in range(1, 4)]
        for run_n, pr in enumerate([0.4, 0.4, 0.4], 1):
            make_grading(tmp, "eval-002", run_n, pr)
        entries_2 = [{"eval_id": "eval-002", "run_n": i, "expectations": [], "transcript_path": "",
                       "output_path": str((tmp / f"evals/transcripts/eval-002-run-{i}-grading.json").relative_to(tmp))}
                      for i in range(1, 4)]
        make_transcripts_to_grade(tmp, entries_1 + entries_2)
        code, out = run_score_mode(tmp)
        assert code == 0
        assert out["functional_detail"]["passed_evals"] == 1
        assert out["functional_detail"]["failed_evals"] == 1
