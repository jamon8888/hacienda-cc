#!/usr/bin/env python3
"""inline_evaluator.py - Evaluate plugins within Claude session without subprocess."""
import json
import re
from typing import Dict, List, Tuple


def check_expectation_inline(transcript: str, expectation: dict) -> dict:
    """Check expectation without subprocess."""
    if not transcript:
        return {
            "text": expectation.get("text", ""),
            "type": expectation.get("type", "contains"),
            "passed": False,
            "evidence": "Empty transcript",
            "grader_type": "deterministic"
        }

    etype = expectation.get("type", "contains")
    text = expectation.get("text", "")

    try:
        if etype == "contains":
            passed = text.lower() in transcript.lower()
            evidence = text if passed else "Not found"

        elif etype == "not_contains":
            passed = text.lower() not in transcript.lower()
            evidence = "Not present" if passed else f"Found: {text}"

        elif etype == "regex":
            try:
                pattern = re.compile(text, re.IGNORECASE | re.MULTILINE)
                match = pattern.search(transcript)
                passed = match is not None
                evidence = match.group(0) if match else "No match"
            except re.error as e:
                passed = False
                evidence = f"Invalid regex: {e}"

        elif etype == "json_valid":
            json_patterns = [
                r'```json\s*([\s\S]*?)```',
                r'```\s*([\s\S]*?)```',
                r'(\{[\s\S]*\})',
                r'(\[[\s\S]*\])',
            ]
            parsed = False
            for pattern in json_patterns:
                match = re.search(pattern, transcript)
                if match:
                    content = match.group(1).strip()
                    try:
                        json.loads(content)
                        passed = True
                        evidence = "Valid JSON"
                        parsed = True
                        break
                    except json.JSONDecodeError:
                        continue
            if not parsed:
                try:
                    json.loads(transcript)
                    passed = True
                    evidence = "Valid JSON"
                except json.JSONDecodeError as e:
                    passed = False
                    evidence = f"No valid JSON found: {e}"

        elif etype == "max_words":
            normalized = re.sub(r'[^\w\s]', ' ', transcript)
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            words = normalized.split() if normalized else []
            word_count = len(words)
            limit = int(text)
            passed = word_count <= limit
            evidence = f"{word_count} words (limit: {limit})"

        else:
            passed = False
            evidence = f"Unknown expectation type: {etype}"

    except Exception as e:
        passed = False
        evidence = f"Error: {e}"

    return {
        "text": text,
        "type": etype,
        "passed": passed,
        "evidence": evidence,
        "grader_type": "deterministic"
    }
