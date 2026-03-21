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


def test_trigger_call_uses_plugin_dir_flag(tmp_path):
    make_plugin(tmp_path)
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "SKILL_USED: test-skill"
    with patch("subprocess.run", return_value=fake) as mock_run:
        run_evals.mode_generate_transcripts(tmp_path)
    claude_calls = [c for c in mock_run.call_args_list if c[0][0][0] == "claude"]
    assert claude_calls, "Expected claude to be called"
    for call in claude_calls:
        args = call[0][0]
        assert "--plugin-dir" in args, f"Expected --plugin-dir in {args}"
        assert "--plugin" not in args, f"Old --plugin flag still present in {args}"


def test_trigger_call_uses_append_system_prompt_flag(tmp_path):
    make_plugin(tmp_path)
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "SKILL_USED: test-skill"
    with patch("subprocess.run", return_value=fake) as mock_run:
        run_evals.mode_generate_transcripts(tmp_path)
    trigger_calls = [c for c in mock_run.call_args_list
                     if c[0][0][0] == "claude" and "--plugin-dir" in c[0][0]
                     and any("SKILL_USED" in str(a) for a in c[0][0])]
    # Check all claude calls that include a system message use --append-system-prompt
    all_claude = [c for c in mock_run.call_args_list if c[0][0][0] == "claude"]
    for call in all_claude:
        args = call[0][0]
        if "--system" in args:
            assert False, f"Old --system flag found in {args}"
        if "--append-system-prompt" in args or "--plugin-dir" in args:
            pass  # OK


def test_trigger_calls_use_append_system_prompt_not_system(tmp_path):
    make_plugin(tmp_path)
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "SKILL_USED: test-skill"
    with patch("subprocess.run", return_value=fake) as mock_run:
        run_evals.mode_generate_transcripts(tmp_path)
    all_claude = [c for c in mock_run.call_args_list if c[0][0][0] == "claude"]
    # Trigger calls include system message — must use --append-system-prompt
    trigger_calls = [c for c in all_claude if "--append-system-prompt" in c[0][0]
                     or "--system" in c[0][0]]
    assert trigger_calls, "Expected trigger calls with system message"
    for call in trigger_calls:
        args = call[0][0]
        assert "--append-system-prompt" in args, f"Expected --append-system-prompt in {args}"
        assert "--system" not in args, f"Old --system flag in {args}"


def test_trigger_calls_use_output_format_json(tmp_path):
    make_plugin(tmp_path)
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = json.dumps({"result": "SKILL_USED: test-skill"})
    with patch("subprocess.run", return_value=fake) as mock_run:
        run_evals.mode_generate_transcripts(tmp_path)
    trigger_calls = [c for c in mock_run.call_args_list
                     if c[0][0][0] == "claude" and "--append-system-prompt" in c[0][0]]
    assert trigger_calls, "Expected trigger claude calls"
    for call in trigger_calls:
        args = call[0][0]
        assert "--output-format" in args, f"Expected --output-format in {args}"
        idx = args.index("--output-format")
        assert args[idx + 1] == "json", f"Expected json after --output-format, got {args[idx+1]}"


def test_functional_input_files_use_add_dir_not_context(tmp_path):
    make_plugin(tmp_path)
    evals = [{"id": "eval-001", "prompt": "test", "input_files": ["some/file.md"], "expectations": []}]
    (tmp_path / "evals/evals.json").write_text(json.dumps(evals))
    (tmp_path / "some").mkdir()
    (tmp_path / "some/file.md").write_text("context")
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "Response"
    with patch("subprocess.run", return_value=fake) as mock_run:
        run_evals.mode_generate_transcripts(tmp_path)
    functional_calls = [c for c in mock_run.call_args_list
                        if c[0][0][0] == "claude" and "--append-system-prompt" not in c[0][0]]
    assert any("--add-dir" in c[0][0] for c in functional_calls), \
        "Expected --add-dir in functional calls with input_files"
    assert not any("--context" in c[0][0] for c in functional_calls), \
        "Old --context flag still present in functional calls"


def test_subprocess_calls_have_timeout_60(tmp_path):
    make_plugin(tmp_path)
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "SKILL_USED: test-skill"
    with patch("subprocess.run", return_value=fake) as mock_run:
        run_evals.mode_generate_transcripts(tmp_path)
    claude_calls = [c for c in mock_run.call_args_list if c[0][0][0] == "claude"]
    for call in claude_calls:
        kwargs = call[1]
        assert kwargs.get("timeout") == 60, \
            f"Expected timeout=60 in subprocess call, got: {kwargs.get('timeout')}"


def test_trigger_detection_uses_json_result_field(tmp_path):
    """When stdout is JSON, trigger detection uses full 'result' field — not just last 3 lines."""
    make_plugin(tmp_path)
    # JSON pretty-printed so SKILL_USED is in 'result' key but NOT in the last 3 lines of raw text.
    # json.dumps with indent=2 puts "result" near the top; extra padding lines push it out of last 3.
    data = {
        "result": "SKILL_USED: test-skill",
        "padding": ["x"] * 20,  # 20 lines of padding push result out of last 3 lines of raw JSON
    }
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = json.dumps(data, indent=2)
    with patch("subprocess.run", return_value=fake):
        run_evals.mode_generate_transcripts(tmp_path)
    tr = json.loads((tmp_path / "evals/trigger-results.json").read_text())
    q = next(q for q in tr["queries"] if q["query"] == "run my skill")
    assert q["pass_rate_q"] == 1.0, \
        "Should detect SKILL_USED in full JSON result field even if not in last 3 lines of raw text"
