# hacienda-maker/tests/test_run_evals_generate.py
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import run_evals as a module for unit testing with mocked subprocess
sys.path.insert(0, str(Path(__file__).parent.parent / "skills/hacienda-maker/scripts"))
import run_evals

def make_plugin(tmp: Path, skill_name: str = "test-skill"):
    (tmp / "skills" / skill_name).mkdir(parents=True)
    (tmp / f"skills/{skill_name}/SKILL.md").write_text(f"---\nname: {skill_name}\n---\n")
    (tmp / "evals").mkdir()
    (tmp / "evals/trigger-eval.json").write_text(json.dumps([
        {"query": "run my skill", "should_trigger": True},
        {"query": "do something else", "should_trigger": False}
    ]))
    (tmp / "evals/evals.json").write_text(json.dumps([
        {"id": "eval-001", "prompt": "test prompt", "input_files": [], "expectations": ["some check"]}
    ]))
    state = {
        "platform": "cowork",
        "scoring": {"runs_per_eval": 2, "weights": {"trigger": 0.4, "functional": 0.6},
                    "threshold": 85, "noise_floor": 2.0},
        "evals": {"trigger_path": "evals/trigger-eval.json", "functional_path": "evals/evals.json"},
        "history": {"best_score": None}
    }
    (tmp / "hacienda-maker.json").write_text(json.dumps(state))
    return tmp


def test_trigger_results_written(tmp_path):
    make_plugin(tmp_path)
    fake_response = MagicMock()
    fake_response.returncode = 0
    fake_response.stdout = "Here is my answer.\nSKILL_USED: test-skill"
    with patch("subprocess.run", return_value=fake_response):
        run_evals.mode_generate_transcripts(tmp_path)
    tr = json.loads((tmp_path / "evals/trigger-results.json").read_text())
    assert tr["total_queries"] == 2
    assert len(tr["queries"]) == 2


def test_trigger_detection_correct(tmp_path):
    make_plugin(tmp_path)
    fake_response = MagicMock()
    fake_response.returncode = 0
    fake_response.stdout = "Some response.\nSKILL_USED: test-skill"
    with patch("subprocess.run", return_value=fake_response):
        run_evals.mode_generate_transcripts(tmp_path)
    tr = json.loads((tmp_path / "evals/trigger-results.json").read_text())
    for q in tr["queries"]:
        assert "results" in q
        assert "pass_rate_q" in q


def test_transcripts_written_for_each_eval_run(tmp_path):
    make_plugin(tmp_path)
    fake_response = MagicMock()
    fake_response.returncode = 0
    fake_response.stdout = "Eval response. SKILL_USED: none"
    with patch("subprocess.run", return_value=fake_response):
        run_evals.mode_generate_transcripts(tmp_path)
    # runs_per_eval=2, 1 eval → 2 transcripts
    transcripts = list((tmp_path / "evals/transcripts").glob("eval-001-run-*.md"))
    assert len(transcripts) == 2


def test_transcripts_to_grade_has_one_entry_per_eval_run(tmp_path):
    make_plugin(tmp_path)
    fake_response = MagicMock()
    fake_response.returncode = 0
    fake_response.stdout = "Response. SKILL_USED: none"
    with patch("subprocess.run", return_value=fake_response):
        run_evals.mode_generate_transcripts(tmp_path)
    ttg = json.loads((tmp_path / "evals/transcripts-to-grade.json").read_text())
    # 1 eval × 2 runs = 2 entries
    assert len(ttg) == 2
    assert all("eval_id" in e and "run_n" in e and "output_path" in e for e in ttg)
