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


INTENT_PATTERNS = [
    (r'\b(build|create|make|generate|design|develop)\b', 'creation'),
    (r'\b(fix|repair|debug|solve|resolve)\b', 'fixing'),
    (r'\b(analyze|review|check|audit|inspect)\b', 'analysis'),
    (r'\b(optimize|improve|enhance|refactor)\b', 'optimization'),
    (r'\b(test|validate|verify|ensure)\b', 'testing'),
]


def matches_intent_pattern(query: str, skill_description: str) -> bool:
    """Check if query intent matches skill purpose."""
    query_lower = query.lower()
    desc_lower = skill_description.lower()
    for pattern, intent_type in INTENT_PATTERNS:
        if re.search(pattern, query_lower):
            # Check for intent type word OR any word from pattern in description
            if intent_type in desc_lower:
                return True
            # Extract words from pattern and check if any appear (including as substrings)
            words_in_pattern = re.findall(r'\b\w+\b', pattern)
            for word in words_in_pattern:
                if word in desc_lower:
                    return True
    return False


def evaluate_trigger_inline(queries: list, skill_description: str) -> dict:
    """Match queries against skill description without subprocess."""
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'to', 'of', 'in', 'for', 'on', 'with'}
    results = []
    for q in queries:
        query_words = set(q["query"].lower().split()) - stop_words
        desc_words = set(skill_description.lower().split()) - stop_words
        overlap = len(query_words & desc_words) / max(len(query_words), 1)
        intent_match = matches_intent_pattern(q["query"], skill_description)
        triggered = overlap > 0.3 or intent_match
        results.append({
            "query": q["query"],
            "should_trigger": q["should_trigger"],
            "triggered": triggered,
            "pass": triggered == q["should_trigger"]
        })
    return {"queries": results, "total_queries": len(results)}
