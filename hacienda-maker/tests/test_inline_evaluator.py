#!/usr/bin/env python3
"""Tests for inline_evaluator.py"""
import sys
from pathlib import Path
# Add scripts directory to path (same pattern as test_grader.py)
sys.path.insert(0, str(Path(__file__).parent.parent / "skills/hacienda-maker/scripts"))

import inline_evaluator


def test_contains_passes():
    result = inline_evaluator.check_expectation_inline(
        "Hello GDPR world", {"text": "gdpr", "type": "contains"}
    )
    assert result["passed"] is True
    assert result["grader_type"] == "deterministic"


def test_contains_fails():
    result = inline_evaluator.check_expectation_inline(
        "Hello world", {"text": "gdpr", "type": "contains"}
    )
    assert result["passed"] is False


def test_not_contains_passes():
    result = inline_evaluator.check_expectation_inline(
        "Hello world", {"text": "gdpr", "type": "not_contains"}
    )
    assert result["passed"] is True


def test_regex_passes():
    result = inline_evaluator.check_expectation_inline(
        "Order #12345", {"text": r"#\d+", "type": "regex"}
    )
    assert result["passed"] is True


def test_regex_invalid_returns_error():
    result = inline_evaluator.check_expectation_inline(
        "text", {"text": r"[", "type": "regex"}
    )
    assert result["passed"] is False
    assert "Invalid regex" in result["evidence"]


def test_json_valid_in_markdown():
    result = inline_evaluator.check_expectation_inline(
        '```json\n{"key": "value"}\n```', {"text": "", "type": "json_valid"}
    )
    assert result["passed"] is True


def test_json_valid_inline():
    result = inline_evaluator.check_expectation_inline(
        'Response: {"status": "ok"}', {"text": "", "type": "json_valid"}
    )
    assert result["passed"] is True


def test_json_valid_fails():
    result = inline_evaluator.check_expectation_inline(
        "not json at all", {"text": "", "type": "json_valid"}
    )
    assert result["passed"] is False


def test_max_words_passes():
    result = inline_evaluator.check_expectation_inline(
        "one two three", {"text": "5", "type": "max_words"}
    )
    assert result["passed"] is True


def test_max_words_with_punctuation():
    result = inline_evaluator.check_expectation_inline(
        "Hello, world! How are you?", {"text": "5", "type": "max_words"}
    )
    assert result["passed"] is True  # 5 words after punctuation normalization


def test_empty_transcript():
    result = inline_evaluator.check_expectation_inline(
        "", {"text": "anything", "type": "contains"}
    )
    assert result["passed"] is False
    assert "Empty transcript" in result["evidence"]


# === Trigger evaluation tests ===
def test_trigger_keyword_overlap():
    queries = [{"query": "build a plugin", "should_trigger": True}]
    desc = "Use when the user wants to build or create plugins"
    result = inline_evaluator.evaluate_trigger_inline(queries, desc)
    assert result["queries"][0]["triggered"] is True


def test_trigger_intent_pattern():
    queries = [{"query": "fix the bug", "should_trigger": True}]
    desc = "Use when debugging or fixing issues"
    result = inline_evaluator.evaluate_trigger_inline(queries, desc)
    assert result["queries"][0]["triggered"] is True


def test_trigger_no_match():
    queries = [{"query": "what is the weather", "should_trigger": False}]
    desc = "Use when building plugins"
    result = inline_evaluator.evaluate_trigger_inline(queries, desc)
    assert result["queries"][0]["triggered"] is False


def test_trigger_pass_calculation():
    queries = [
        {"query": "build plugin", "should_trigger": True},
        {"query": "weather today", "should_trigger": False}
    ]
    desc = "Use when building plugins"
    result = inline_evaluator.evaluate_trigger_inline(queries, desc)
    assert result["queries"][0]["pass"] is True
    assert result["queries"][1]["pass"] is True  # didn't trigger, shouldn't trigger
