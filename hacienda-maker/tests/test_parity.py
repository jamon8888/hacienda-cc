"""Test parity between inline and subprocess evaluation paths."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "skills/hacienda-maker/scripts"))

import json
import grader
import inline_evaluator


def assert_expectations_parity(inline_results, sub_results):
    """Verify structural equality for expectations list."""
    assert len(inline_results) == len(sub_results), "Result count mismatch"

    for i, (inline_exp, sub_exp) in enumerate(zip(inline_results, sub_results)):
        assert inline_exp["text"] == sub_exp["text"], f"Expectation {i} text mismatch"
        assert inline_exp["type"] == sub_exp["type"], f"Expectation {i} type mismatch"
        assert inline_exp["grader_type"] == sub_exp["grader_type"], f"Expectation {i} grader_type mismatch"
        assert inline_exp["passed"] == sub_exp["passed"], f"Expectation {i} passed mismatch"

        if inline_exp["grader_type"] == "deterministic":
            assert inline_exp["evidence"] == sub_exp["evidence"], f"Expectation {i} evidence mismatch"


def test_deterministic_parity():
    """Inline and subprocess deterministic grading must match."""
    transcript = "This response mentions GDPR compliance and follows EU regulations."
    expectations_raw = [
        "GDPR",
        {"text": "EU", "type": "contains"},
        {"text": " HIPAA ", "type": "not_contains"},
        {"text": r"\bEU\b", "type": "regex"},
    ]

    expectations, _ = grader.normalize_all_expectations(expectations_raw)

    # Subprocess path (using grader module directly)
    sub_results = [grader.grade_deterministic(transcript, e) for e in expectations]

    # Inline path
    inline_results = [inline_evaluator.check_expectation_inline(transcript, e) for e in expectations]

    assert_expectations_parity(inline_results, sub_results)

    # Verify pass rates match
    sub_pass_rate = sum(r["passed"] for r in sub_results) / len(sub_results)
    inline_pass_rate = sum(r["passed"] for r in inline_results) / len(inline_results)
    assert sub_pass_rate == inline_pass_rate


def test_all_deterministic_types_parity():
    """All deterministic types must produce identical results for plain text."""
    # Note: json_valid only works for plain JSON, not markdown-wrapped
    transcript = '{"status": "ok", "count": 42}'
    expectations_raw = [
        {"text": "status", "type": "contains"},
        {"text": "xml", "type": "not_contains"},
        {"text": r'"count":\s*\d+', "type": "regex"},
        {"text": "", "type": "json_valid"},
        {"text": "10", "type": "max_words"},
    ]

    expectations, _ = grader.normalize_all_expectations(expectations_raw)

    sub_results = [grader.grade_deterministic(transcript, e) for e in expectations]
    inline_results = [inline_evaluator.check_expectation_inline(transcript, e) for e in expectations]

    for i, (sub, inline) in enumerate(zip(sub_results, inline_results)):
        assert sub["passed"] == inline["passed"], f"Type {expectations[i]['type']}: passed mismatch"
        assert sub["grader_type"] == inline["grader_type"], f"Type {expectations[i]['type']}: grader_type mismatch"
