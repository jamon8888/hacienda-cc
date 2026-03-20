# hacienda-maker/tests/test_grader.py
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

GRADER_PY = Path(__file__).parent.parent / "skills/hacienda-maker/scripts/grader.py"
sys.path.insert(0, str(Path(__file__).parent.parent / "skills/hacienda-maker/scripts"))
import grader


# --- contains ---
def test_contains_passes():
    result = grader.grade_deterministic("Hello GDPR world", {"text": "gdpr", "type": "contains"})
    assert result["passed"] is True
    assert result["grader_type"] == "deterministic"


def test_contains_fails():
    result = grader.grade_deterministic("Hello world", {"text": "gdpr", "type": "contains"})
    assert result["passed"] is False


def test_no_type_defaults_to_contains():
    result = grader.grade_deterministic("Hello GDPR world", {"text": "gdpr"})
    assert result["passed"] is True
    assert result["type"] == "contains"


# --- not_contains ---
def test_not_contains_passes():
    result = grader.grade_deterministic("Hello world", {"text": "gdpr", "type": "not_contains"})
    assert result["passed"] is True


def test_not_contains_fails():
    result = grader.grade_deterministic("Hello GDPR world", {"text": "gdpr", "type": "not_contains"})
    assert result["passed"] is False


# --- regex ---
def test_regex_passes():
    result = grader.grade_deterministic("Order #12345", {"text": r"#\d+", "type": "regex"})
    assert result["passed"] is True


def test_regex_fails():
    result = grader.grade_deterministic("No order here", {"text": r"#\d+", "type": "regex"})
    assert result["passed"] is False


# --- json_valid ---
def test_json_valid_passes():
    result = grader.grade_deterministic('{"key": "value"}', {"text": "", "type": "json_valid"})
    assert result["passed"] is True


def test_json_valid_fails():
    result = grader.grade_deterministic("not json", {"text": "", "type": "json_valid"})
    assert result["passed"] is False


# --- max_words ---
def test_max_words_passes():
    result = grader.grade_deterministic("one two three", {"text": "5", "type": "max_words"})
    assert result["passed"] is True


def test_max_words_fails():
    result = grader.grade_deterministic("one two three four five six", {"text": "3", "type": "max_words"})
    assert result["passed"] is False


# --- grader_type field ---
def test_grader_type_field_present():
    result = grader.grade_deterministic("hello", {"text": "hello", "type": "contains"})
    assert "grader_type" in result


# --- semantic ---
def test_semantic_passed_true():
    fake = MagicMock()
    fake.stdout = json.dumps({"result": json.dumps({"passed": True, "evidence": "verbatim quote"})})
    fake.returncode = 0
    with patch("subprocess.run", return_value=fake):
        result = grader.grade_semantic("some transcript", {"text": "le ton est neutre", "type": "semantic"})
    assert result["passed"] is True
    assert result["grader_type"] == "llm"
    assert result["evidence"] == "verbatim quote"


def test_semantic_passed_false():
    fake = MagicMock()
    fake.stdout = json.dumps({"result": json.dumps({"passed": False, "evidence": "Not found"})})
    fake.returncode = 0
    with patch("subprocess.run", return_value=fake):
        result = grader.grade_semantic("some transcript", {"text": "check", "type": "semantic"})
    assert result["passed"] is False


def test_semantic_parse_error_returns_false():
    fake = MagicMock()
    fake.stdout = "not json"
    fake.returncode = 0
    with patch("subprocess.run", return_value=fake):
        result = grader.grade_semantic("transcript", {"text": "check", "type": "semantic"})
    assert result["passed"] is False
    assert result["evidence"] == "grader parse error"


# --- end-to-end schema via CLI ---
def test_grading_json_schema_valid():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        transcript_path = tmp / "transcript.md"
        transcript_path.write_text("Hello GDPR world")
        output_path = tmp / "grading.json"
        expectations = [{"text": "gdpr", "type": "contains"}]

        result = subprocess.run(
            [sys.executable, str(GRADER_PY),
             "--transcript", str(transcript_path),
             "--expectations", json.dumps(expectations),
             "--output", str(output_path),
             "--eval-id", "eval-001",
             "--run-n", "1"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        loaded = json.loads(output_path.read_text())
        assert "eval_id" in loaded
        assert "run_id" in loaded
        assert "expectations" in loaded
        assert "summary" in loaded
        assert "pass_rate" in loaded["summary"]
        assert all("grader_type" in e for e in loaded["expectations"])
