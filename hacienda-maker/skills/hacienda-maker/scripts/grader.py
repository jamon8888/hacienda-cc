#!/usr/bin/env python3
"""grader.py — hybrid deterministic + LLM grader for hacienda-maker evals."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


VALID_EXPECTATION_TYPES = {"contains", "not_contains", "regex", "json_valid", "max_words", "semantic"}
TEXT_KEY_ALIASES = {"text", "pattern", "regex", "value", "expectation", "query"}


def normalize_expectation(exp):
    """Convert any expectation format to canonical dict."""
    if isinstance(exp, str):
        return {"text": exp, "type": "contains"}
    if isinstance(exp, dict):
        result = exp.copy()
        text_value = None
        for key in TEXT_KEY_ALIASES:
            if key in result:
                text_value = result.pop(key)
                break
        if text_value is None:
            raise ValueError(f"Expectation missing text field: {exp}")
        if not isinstance(text_value, str):
            text_value = str(text_value)
        result["text"] = text_value
        result.setdefault("type", "contains")
        if result["type"] not in VALID_EXPECTATION_TYPES:
            raise ValueError(f"Invalid expectation type '{result['type']}'")
        result.pop("grader_type", None)
        result.pop("passed", None)
        result.pop("evidence", None)
        return result
    raise ValueError(f"Expectation must be string or dict, got {type(exp).__name__}")


def normalize_all_expectations(expectations):
    """Normalize all expectations, returning (valid_list, error_list)."""
    valid, errors = [], []
    for i, exp in enumerate(expectations):
        try:
            valid.append(normalize_expectation(exp))
        except ValueError as e:
            errors.append(f"Expectation {i}: {e}")
    return valid, errors


def grade_deterministic(transcript: str, expectation: dict) -> dict:
    text = expectation["text"]
    etype = expectation.get("type", "contains")

    if etype == "contains":
        passed = text.lower() in transcript.lower()
        evidence = text if passed else "Not found"
    elif etype == "not_contains":
        passed = text.lower() not in transcript.lower()
        evidence = "Not present" if passed else f"Found: {text}"
    elif etype == "regex":
        try:
            m = re.search(text, transcript)
            passed = m is not None
            evidence = m.group(0) if m else "No match"
        except re.error as e:
            passed = False
            evidence = f"Invalid regex: {e}"
    elif etype == "json_valid":
        try:
            json.loads(transcript)
            passed = True
            evidence = "Valid JSON"
        except json.JSONDecodeError as e:
            passed = False
            evidence = str(e)
    elif etype == "max_words":
        limit = int(text)
        word_count = len(transcript.split())
        passed = word_count <= limit
        evidence = f"{word_count} words"
    else:
        raise ValueError(f"Unknown type: {etype}")

    return {
        "text": text,
        "type": etype,
        "grader_type": "deterministic",
        "passed": passed,
        "evidence": evidence,
    }


def grade_semantic(transcript: str, expectation: dict) -> dict:
    text = expectation["text"]
    prompt = (
        f"Transcript:\n{transcript}\n\n"
        f'Expectation: "{text}"\n\n'
        f"Est-ce que le transcript satisfait cette expectation ?\n"
        f'Réponds en JSON strict : {{"passed": true|false, "evidence": '
        f'"citation verbatim du transcript, ou \'Not found\' si absent"}}'
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json", "--print"],
            capture_output=True, text=True, timeout=60,
        )
        outer = json.loads(result.stdout)
        inner = json.loads(outer.get("result", "{}"))
        passed = bool(inner.get("passed", False))
        evidence = inner.get("evidence", "grader parse error")
    except json.JSONDecodeError:
        passed = False
        evidence = "grader parse error"
    except subprocess.TimeoutExpired:
        passed = False
        evidence = "grader timeout (60s)"
    except FileNotFoundError:
        passed = False
        evidence = "grader parse error"

    return {
        "text": text,
        "type": "semantic",
        "grader_type": "llm",
        "passed": passed,
        "evidence": evidence,
    }


def main():
    parser = argparse.ArgumentParser(description="Grade a transcript against expectations.")
    parser.add_argument("--transcript", required=True, help="Path to transcript file")
    parser.add_argument("--expectations", required=True, help="JSON array of expectations")
    parser.add_argument("--output", required=True, help="Path to write grading.json")
    parser.add_argument("--eval-id", required=True, dest="eval_id")
    parser.add_argument("--run-n", required=True, type=int, dest="run_n")
    args = parser.parse_args()

    transcript = Path(args.transcript).read_text()
    try:
        expectations = json.loads(args.expectations)
    except json.JSONDecodeError as e:
        sys.exit(f"Error: Invalid JSON in --expectations: {e}")

    # Normalize expectations: convert strings to objects
    normalized = []
    for exp in expectations:
        if isinstance(exp, str):
            normalized.append({"text": exp, "type": "contains"})
        else:
            normalized.append(exp)
    expectations = normalized

    results = []
    for exp in expectations:
        etype = exp.get("type", "contains")
        if etype == "semantic":
            results.append(grade_semantic(transcript, exp))
        else:
            results.append(grade_deterministic(transcript, exp))

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    grading = {
        "eval_id": args.eval_id,
        "run_id": f"run-{args.run_n}",
        "transcript_path": args.transcript,
        "expectations": results,
        "summary": {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "pass_rate": passed / total if total > 0 else 0.0,
        },
    }

    Path(args.output).write_text(json.dumps(grading, indent=2))
    print(json.dumps(grading, indent=2))


if __name__ == "__main__":
    main()
