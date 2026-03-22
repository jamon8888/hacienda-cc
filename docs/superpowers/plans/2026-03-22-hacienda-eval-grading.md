# Hacienda-Maker Eval & Grading Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix eval/grading bugs (JSON parse, semantic grading, expectation format, timeout) and improve performance from 5-10 min to <2 min per optimize loop iteration.

**Architecture:** Hybrid approach - fix subprocess path for reliability (parallel + batched + retry), add inline evaluator for optimize loop speed (no subprocess spawning), both paths produce identical JSON schema.

**Tech Stack:** Python 3.x, concurrent.futures, json, re, subprocess, pytest

---

## File Structure

| File | Responsibility |
|------|----------------|
| `hacienda-maker/skills/hacienda-maker/scripts/inline_evaluator.py` | NEW - Inline trigger/expectation evaluation |
| `hacienda-maker/skills/hacienda-maker/scripts/grader.py` | MODIFY - Fix JSON parsing, add normalization |
| `hacienda-maker/skills/hacienda-maker/scripts/run_evals.py` | MODIFY - Parallel transcript gen, batched grading |
| `hacienda-maker/references/optimize-loop.md` | MODIFY - Use inline evaluator in Phase 5 |
| `hacienda-maker/tests/test_inline_evaluator.py` | NEW - Unit tests for inline evaluator |

---

## Task 1: Expectation Normalization

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/scripts/grader.py`
- Test: `hacienda-maker/tests/test_grader.py`

**Existing functions in grader.py:**
- `grade_deterministic(transcript, expectation)` - lines 11-51
- `grade_semantic(transcript, expectation)` - lines 54-88
- `main()` - lines 91-143
- Basic normalization in `main()` lines 106-113 (converts string to dict)

- [ ] **Step 1: Write failing tests for normalize_expectation**

Add to `tests/test_grader.py` (note: existing tests already have sys.path.insert at line 9-10):

```python
# === Normalization tests ===
def test_normalize_string_expectation():
    import grader
    result = grader.normalize_expectation("GDPR compliance")
    assert result == {"text": "GDPR compliance", "type": "contains"}

def test_normalize_dict_expectation():
    import grader
    result = grader.normalize_expectation({"text": "check this"})
    assert result == {"text": "check this", "type": "contains"}

def test_normalize_alternative_keys():
    import grader
    assert grader.normalize_expectation({"pattern": "test"})["text"] == "test"
    assert grader.normalize_expectation({"regex": r"\d+"})["text"] == r"\d+"
    assert grader.normalize_expectation({"value": "x"})["text"] == "x"

def test_normalize_missing_text_raises():
    import grader, pytest
    with pytest.raises(ValueError, match="text"):
        grader.normalize_expectation({"type": "contains"})

def test_normalize_invalid_type_raises():
    import grader, pytest
    with pytest.raises(ValueError, match="Invalid expectation type"):
        grader.normalize_expectation({"text": "x", "type": "fuzzy"})

def test_normalize_all_expectations():
    import grader
    expectations = ["str", {"text": "dict"}, {"type": "missing"}]
    valid, errors = grader.normalize_all_expectations(expectations)
    assert len(valid) == 2
    assert len(errors) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd hacienda-maker && pytest tests/test_grader.py -v -k normalize
```
Expected: FAIL with `AttributeError: module 'grader' has no attribute 'normalize_expectation'` (function not yet defined)

- [ ] **Step 3: Implement normalization functions**

Add to `grader.py` after imports:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd hacienda-maker && pytest tests/test_grader.py -v -k normalize
```
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/scripts/grader.py hacienda-maker/tests/test_grader.py
git commit -m "feat(grader): add expectation normalization with alternative key support"
```

---

## Task 2: Robust JSON Parsing

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/scripts/grader.py`
- Test: `hacienda-maker/tests/test_grader.py`

- [ ] **Step 1: Write failing tests for parse_grader_response**

Add to `tests/test_grader.py`:

```python
# === JSON parsing tests ===
def test_parse_wrapped_response():
    import grader
    raw = '{"result": "{\\"passed\\": true, \\"evidence\\": \\"found\\"}"}'
    result = grader.parse_grader_response(raw)
    assert result["passed"] is True
    assert result["evidence"] == "found"

def test_parse_unwrapped_response():
    import grader
    raw = '{"passed": false, "evidence": "not found"}'
    result = grader.parse_grader_response(raw)
    assert result["passed"] is False

def test_parse_missing_passed_field():
    import grader
    raw = '{"evidence": "something"}'
    result = grader.parse_grader_response(raw)
    assert result["passed"] is False
    assert "Missing" in result["evidence"]

def test_parse_invalid_json():
    import grader
    raw = 'not json at all'
    result = grader.parse_grader_response(raw)
    assert result["passed"] is False
    assert "JSON parse error" in result["evidence"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd hacienda-maker && pytest tests/test_grader.py -v -k "parse_grader"
```
Expected: FAIL with `AttributeError: module 'grader' has no attribute 'parse_grader_response'` (function not yet defined)

- [ ] **Step 3: Implement parse_grader_response**

Add to `grader.py`:

```python
def parse_grader_response(raw):
    """Parse grader response with validation. Handles wrapped and unwrapped formats."""
    try:
        outer = json.loads(raw)
        if isinstance(outer, dict) and "result" in outer:
            inner_raw = outer["result"]
            inner = json.loads(inner_raw) if isinstance(inner_raw, str) else inner_raw
        else:
            inner = outer
        if "passed" not in inner:
            return {"passed": False, "evidence": "Missing 'passed' field"}
        inner["passed"] = bool(inner.get("passed", False))
        inner.setdefault("evidence", "No evidence provided")
        return inner
    except json.JSONDecodeError as e:
        return {"passed": False, "evidence": f"JSON parse error: {e}"}
```

- [ ] **Step 4: Update grade_semantic to use parse_grader_response**

Replace the try/except block in `grade_semantic` function:

```python
def grade_semantic(transcript: str, expectation: dict) -> dict:
    text = expectation["text"]
    prompt = (
        f"Transcript:\n{transcript}\n\n"
        f'Expectation: "{text}"\n\n'
        f"Does the transcript satisfy this expectation?\n"
        f'Respond in JSON: {{"passed": true|false, "evidence": "quote or Not found"}}'
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json", "--print"],
            capture_output=True, text=True, timeout=60,
        )
        inner = parse_grader_response(result.stdout)
        passed = inner.get("passed", False)
        evidence = inner.get("evidence", "grader parse error")
    except subprocess.TimeoutExpired:
        passed = False
        evidence = "grader timeout (60s)"
    except FileNotFoundError:
        passed = False
        evidence = "grader error"

    return {
        "text": text,
        "type": "semantic",
        "grader_type": "llm",
        "passed": passed,
        "evidence": evidence,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd hacienda-maker && pytest tests/test_grader.py -v -k "parse_grader"
```
Expected: PASS (4 tests)

- [ ] **Step 6: Run full grader test suite**

```bash
cd hacienda-maker && pytest tests/test_grader.py -v
```
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/scripts/grader.py hacienda-maker/tests/test_grader.py
git commit -m "fix(grader): robust JSON parsing with wrapper handling"
```

---

## Task 3: Create inline_evaluator.py - Deterministic Checking

**Files:**
- Create: `hacienda-maker/skills/hacienda-maker/scripts/inline_evaluator.py`
- Create: `hacienda-maker/tests/test_inline_evaluator.py`

- [ ] **Step 1: Write failing tests for check_expectation_inline**

Create `tests/test_inline_evaluator.py` with proper import path setup:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd hacienda-maker && pytest tests/test_inline_evaluator.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'inline_evaluator'` (file not yet created)

- [ ] **Step 3: Create inline_evaluator.py with check_expectation_inline**

Create `skills/hacienda-maker/scripts/inline_evaluator.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd hacienda-maker && pytest tests/test_inline_evaluator.py -v
```
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/scripts/inline_evaluator.py hacienda-maker/tests/test_inline_evaluator.py
git commit -m "feat(inline): add check_expectation_inline with all deterministic types"
```

---

## Task 4: Inline Trigger Evaluation

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/scripts/inline_evaluator.py`
- Modify: `hacienda-maker/tests/test_inline_evaluator.py`

- [ ] **Step 1: Write failing tests for trigger evaluation**

Add to `tests/test_inline_evaluator.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd hacienda-maker && pytest tests/test_inline_evaluator.py -v -k trigger
```
Expected: FAIL with `AttributeError: module 'inline_evaluator' has no attribute 'evaluate_trigger_inline'` (function not yet defined)

- [ ] **Step 3: Implement trigger evaluation**

Add to `inline_evaluator.py`:

```python
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
            if intent_type in desc_lower or re.search(pattern, desc_lower):
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd hacienda-maker && pytest tests/test_inline_evaluator.py -v -k trigger
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/scripts/inline_evaluator.py hacienda-maker/tests/test_inline_evaluator.py
git commit -m "feat(inline): add trigger evaluation with keyword and intent matching"
```

---

## Task 5: Semantic Response Parsing

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/scripts/inline_evaluator.py`
- Modify: `hacienda-maker/tests/test_inline_evaluator.py`

- [ ] **Step 1: Write failing tests for parse_semantic_response**

Add to `tests/test_inline_evaluator.py`:

```python
def test_parse_semantic_wrapped():
    response = '{"result": "{\\"idx\\": 0, \\"passed\\": true, \\"evidence\\": \\"found\\"}"}'
    expectations = [{"text": "check"}]
    results = inline_evaluator.parse_semantic_response(response, expectations)
    assert len(results) == 1
    assert results[0]["passed"] is True
    assert results[0]["grader_type"] == "llm"

def test_parse_semantic_array():
    response = '[{"idx": 0, "passed": true, "evidence": "a"}, {"idx": 1, "passed": false, "evidence": "b"}]'
    expectations = [{"text": "a"}, {"text": "b"}]
    results = inline_evaluator.parse_semantic_response(response, expectations)
    assert len(results) == 2
    assert results[0]["passed"] is True
    assert results[1]["passed"] is False

def test_parse_semantic_line_by_line():
    response = '{"idx": 0, "passed": true, "evidence": "x"}\n{"idx": 1, "passed": false, "evidence": "y"}'
    expectations = [{"text": "a"}, {"text": "b"}]
    results = inline_evaluator.parse_semantic_response(response, expectations)
    assert len(results) == 2

def test_parse_semantic_missing_lines():
    response = '{"idx": 0, "passed": true, "evidence": "x"}'
    expectations = [{"text": "a"}, {"text": "b"}]
    results = inline_evaluator.parse_semantic_response(response, expectations)
    assert len(results) == 2
    assert results[1]["evidence"] == "Missing response line"

def test_parse_semantic_malformed_json():
    response = 'not json\n{"idx": 1, "passed": true, "evidence": "x"}'
    expectations = [{"text": "a"}, {"text": "b"}]
    results = inline_evaluator.parse_semantic_response(response, expectations)
    assert results[0]["passed"] is False
    assert "JSON parse error" in results[0]["evidence"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd hacienda-maker && pytest tests/test_inline_evaluator.py -v -k "parse_semantic"
```
Expected: FAIL with `AttributeError: module 'inline_evaluator' has no attribute 'parse_semantic_response'` (function not yet defined)

- [ ] **Step 3: Implement parse_semantic_response**

Add to `inline_evaluator.py`:

```python
def parse_semantic_response(response: str, expectations: List[Dict]) -> List[Dict]:
    """Parse Claude's response into structured results."""
    raw = response.strip()

    # Handle Claude CLI wrapper
    try:
        outer = json.loads(raw)
        if isinstance(outer, dict) and "result" in outer:
            raw = outer["result"]
            if isinstance(raw, str):
                raw = raw.strip()
    except json.JSONDecodeError:
        pass

    # Try parsing as top-level array
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            lines = [json.dumps(obj) for obj in arr]
        else:
            lines = [json.dumps(arr)]
    except json.JSONDecodeError:
        lines = [l.strip() for l in raw.split('\n') if l.strip()]

    results = []
    for i, exp in enumerate(expectations):
        if i < len(lines):
            try:
                obj = json.loads(lines[i])
                passed = bool(obj.get("passed", False))
                evidence = str(obj.get("evidence", "No evidence provided"))
            except json.JSONDecodeError as e:
                passed = False
                evidence = f"JSON parse error: {e}"
        else:
            passed = False
            evidence = "Missing response line"

        results.append({
            "text": exp["text"],
            "type": "semantic",
            "passed": passed,
            "evidence": evidence,
            "grader_type": "llm"
        })

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd hacienda-maker && pytest tests/test_inline_evaluator.py -v -k "parse_semantic"
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/scripts/inline_evaluator.py hacienda-maker/tests/test_inline_evaluator.py
git commit -m "feat(inline): add semantic response parsing with edge case handling"
```

---

## Task 6: Parallel Transcript Generation

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/scripts/run_evals.py`
- Test: `hacienda-maker/tests/test_run_evals.py`

**Existing functions in run_evals.py:**
- `load_state(cwd)` - reads hm.json
- `write_state(cwd, state)`
- `write_failed_grading(output_path, entry, reason)`
- `safe_pass_rate(grading)`
- `mode_score(cwd, baseline)`
- `mode_generate_transcripts(cwd)` - sequential, uses subprocess.run
- `mode_grade(cwd)` - sequential grading
- `main()` - mode dispatcher

- [ ] **Step 1: Write failing tests for parallel generation**

Add to `tests/test_run_evals.py` (note: existing tests already have sys.path.insert at line 9):

```python
import time

def test_parallel_generation_preserves_order():
    """Parallel generation must return results in input order."""
    import run_evals
    from unittest.mock import patch, MagicMock

    entries = [
        {"prompt": "say A"},
        {"prompt": "say B"},
        {"prompt": "say C"},
    ]

    # Mock subprocess.run to return predictable results
    def mock_run(cmd, **kwargs):
        prompt = cmd[cmd.index("-p") + 1]
        return MagicMock(stdout=f"Response for: {prompt}", returncode=0)

    with patch("run_evals.subprocess.run", side_effect=mock_run):
        results = run_evals.generate_transcripts_parallel(
            entries, max_workers=2, timeout_per_entry=30, retries=0, total_timeout_budget=120
        )

    assert len(results) == 3
    # Verify order matches input order
    assert results[0][0]["prompt"] == "say A"
    assert results[1][0]["prompt"] == "say B"
    assert results[2][0]["prompt"] == "say C"

def test_parallel_generation_timeout_budget():
    """Budget exhausted should not hang indefinitely."""
    import run_evals

    start = time.time()
    entries = [{"prompt": f"test {i}"} for i in range(10)]

    results = run_evals.generate_transcripts_parallel(
        entries, max_workers=4, timeout_per_entry=60, retries=0, total_timeout_budget=2
    )

    elapsed = time.time() - start
    # Should return within reasonable time of budget (not 10x timeout_per_entry)
    assert elapsed < 10, f"Took {elapsed}s, should be under 10s with 2s budget"
    assert len(results) == 10
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd hacienda-maker && pytest tests/test_run_evals.py -v -k "parallel"
```
Expected: FAIL with `AttributeError: module 'run_evals' has no attribute 'generate_transcripts_parallel'` (function not yet defined)

- [ ] **Step 3: Implement parallel generation**

Add to `run_evals.py` after imports:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def generate_transcripts_parallel(entries, max_workers=4, timeout_per_entry=60,
                                   retries=2, total_timeout_budget=600, cwd=None):
    """Generate transcripts in parallel with ordering preserved and bounded total time."""
    cwd = cwd or Path.cwd()
    start_time = time.time()

    def run_single(entry):
        idx = entry.get("_index", 0)
        for attempt in range(retries + 1):
            if time.time() - start_time > total_timeout_budget:
                return (idx, None)
            try:
                result = subprocess.run(
                    ["claude", "-p", entry["prompt"], "--plugin-dir", str(cwd)],
                    capture_output=True, text=True,
                    timeout=timeout_per_entry * (attempt + 1)
                )
                return (idx, result.stdout)
            except subprocess.TimeoutExpired:
                if attempt == retries:
                    return (idx, None)
                time.sleep(2 ** attempt)
            except Exception:
                return (idx, None)
        return (idx, None)

    indexed = [{**e, "_index": i} for i, e in enumerate(entries)]
    results = [None] * len(entries)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_single, e): e for e in indexed}
        for future in as_completed(futures):
            if time.time() - start_time > total_timeout_budget:
                for f in futures:
                    f.cancel()
                break
            idx, transcript = future.result()
            results[idx] = (entries[idx], transcript)

    for i in range(len(results)):
        if results[i] is None:
            results[i] = (entries[i], None)

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd hacienda-maker && pytest tests/test_run_evals.py -v -k "parallel"
```
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/scripts/run_evals.py hacienda-maker/tests/test_run_evals.py
git commit -m "feat(evals): add parallel transcript generation with ordering and budget"
```

---

## Task 7: Batched Semantic Grading

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/scripts/run_evals.py`
- Test: `hacienda-maker/tests/test_run_evals.py`

**Note:** This adds new functions to run_evals.py, not modifying existing ones.

- [ ] **Step 1: Write failing tests for batched grading**

Add to `tests/test_run_evals.py` (note: patch target must be `run_evals.subprocess.run`):

```python
def test_batch_semantic_single_call():
    """Batch semantic should call Claude once for multiple expectations."""
    import run_evals
    from unittest.mock import patch, MagicMock

    expectations = [
        {"text": "tone is professional"},
        {"text": "mentions GDPR"},
    ]

    mock_response = '{"result": "[{\\"idx\\": 0, \\"passed\\": true, \\"evidence\\": \\"a\\"}, {\\"idx\\": 1, \\"passed\\": false, \\"evidence\\": \\"b\\"}]"}'

    with patch("run_evals.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_response, returncode=0)
        results = run_evals.grade_semantic_batch("transcript text", expectations, timeout=60)

    assert len(results) == 2
    assert results[0]["passed"] is True
    assert results[1]["passed"] is False
    assert results[0]["grader_type"] == "llm"
    # Verify single subprocess call
    assert mock_run.call_count == 1

def test_batch_semantic_empty_expectations():
    """Empty expectations should return empty list."""
    import run_evals
    results = run_evals.grade_semantic_batch("transcript", [], timeout=60)
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd hacienda-maker && pytest tests/test_run_evals.py -v -k "batch_semantic"
```
Expected: FAIL with `AttributeError: module 'run_evals' has no attribute 'grade_semantic_batch'` (function not yet defined)

- [ ] **Step 3: Implement batched semantic grading**

Add to `run_evals.py`:

```python
def build_semantic_prompt(transcript, expectations):
    """Build prompt for semantic evaluation."""
    exp_list = "\n".join(f"{i}. {e['text']}" for i, e in enumerate(expectations))
    return f"""Evaluate the following transcript against each expectation.

<transcript>
{transcript}
</transcript>

<expectations>
{exp_list}
</expectations>

For each expectation, respond with a JSON object on its own line:
{{"idx": <number>, "passed": true|false, "evidence": "<verbatim quote or 'Not found'>"}}

Respond with exactly {len(expectations)} JSON objects, one per line. No wrapping, no markdown."""

def grade_semantic_batch(transcript, expectations, timeout=120):
    """Grade multiple semantic expectations in one LLM call."""
    if not expectations:
        return []

    prompt = build_semantic_prompt(transcript, expectations)
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True, timeout=timeout
    )

    try:
        outer = json.loads(result.stdout)
        raw = outer.get("result", result.stdout)
    except json.JSONDecodeError:
        raw = result.stdout

    # Import parse function from inline_evaluator
    from inline_evaluator import parse_semantic_response
    return parse_semantic_response(raw, expectations)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd hacienda-maker && pytest tests/test_run_evals.py -v -k "batch_semantic"
```
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/scripts/run_evals.py hacienda-maker/tests/test_run_evals.py
git commit -m "feat(evals): add batched semantic grading for fewer Claude calls"
```

---

## Task 8: Update mode_grade to use batched semantic

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/scripts/run_evals.py`

- [ ] **Step 1: Update mode_grade to batch semantic expectations**

Modify the `mode_grade` function to group semantic expectations and batch them:

```python
def mode_grade(cwd: Path, batch_semantic: bool = True):
    """Grade transcripts, optionally batching semantic expectations."""
    evals_dir = cwd / "evals"
    ttg_path = evals_dir / "transcripts-to-grade.json"
    if not ttg_path.exists():
        print("Error: evals/transcripts-to-grade.json not found", file=sys.stderr)
        sys.exit(1)

    entries = json.loads(ttg_path.read_text())
    grader_script = Path(__file__).parent / "grader.py"
    import grader as grader_module

    skipped, failed, succeeded = 0, 0, 0

    for entry in entries:
        output_path = cwd / entry["output_path"]

        if output_path.exists():
            try:
                existing = json.loads(output_path.read_text())
                if isinstance(existing.get("summary", {}).get("pass_rate"), (int, float)):
                    skipped += 1
                    continue
            except (json.JSONDecodeError, KeyError):
                pass

        transcript_path = cwd / entry["transcript_path"]
        if not transcript_path.exists():
            write_failed_grading(output_path, entry, "transcript missing")
            failed += 1
            continue

        transcript = transcript_path.read_text(encoding='utf-8')
        expectations_raw = entry.get("expectations", [])
        expectations, norm_errors = grader_module.normalize_all_expectations(expectations_raw)

        if norm_errors:
            print(f"Warning: {entry['eval_id']}: {norm_errors}", file=sys.stderr)

        # Separate deterministic and semantic
        deterministic = [e for e in expectations if e["type"] != "semantic"]
        semantic = [e for e in expectations if e["type"] == "semantic"]

        results = []

        # Check deterministic inline
        for exp in deterministic:
            result = grader_module.grade_deterministic(transcript, exp)
            results.append(result)

        # Batch semantic if enabled and present
        if semantic:
            if batch_semantic:
                try:
                    semantic_results = grade_semantic_batch(transcript, semantic, timeout=120)
                    results.extend(semantic_results)
                except Exception as e:
                    for exp in semantic:
                        results.append({
                            "text": exp["text"],
                            "type": "semantic",
                            "grader_type": "llm",
                            "passed": False,
                            "evidence": f"Batch error: {e}"
                        })
            else:
                # Fall back to individual calls
                for exp in semantic:
                    result = grader_module.grade_semantic(transcript, exp)
                    results.append(result)

        passed_count = sum(1 for r in results if r["passed"])
        total = len(results)
        grading = {
            "eval_id": entry["eval_id"],
            "run_id": f"run-{entry['run_n']}",
            "transcript_path": entry["transcript_path"],
            "expectations": results,
            "summary": {
                "passed": passed_count,
                "failed": total - passed_count,
                "total": total,
                "pass_rate": passed_count / total if total > 0 else 1.0
            }
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(grading, indent=2))
        succeeded += 1

    print(f"Graded: {len(entries)} entries ({succeeded} succeeded, {skipped} skipped, {failed} failed)")
```

- [ ] **Step 2: Run full test suite**

```bash
cd hacienda-maker && pytest tests/test_run_evals.py tests/test_grader.py -v
```
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/scripts/run_evals.py
git commit -m "feat(evals): integrate batched semantic grading into mode_grade"
```

---

## Task 9: Integration Test - Parity Check

**Files:**
- Create: `hacienda-maker/tests/test_parity.py`

- [ ] **Step 1: Write parity integration test**

Create `tests/test_parity.py`:

```python
"""Test parity between inline and subprocess evaluation paths."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "skills/hacienda-maker/scripts"))

import json
import grader
import inline_evaluator

def assert_full_parity(inline_result, subprocess_result):
    """Verify structural equality with semantic evidence exemption."""
    assert inline_result["eval_id"] == subprocess_result["eval_id"]
    assert inline_result["summary"]["pass_rate"] == subprocess_result["summary"]["pass_rate"]

    for i, (inline_exp, sub_exp) in enumerate(zip(
        inline_result["expectations"], subprocess_result["expectations"]
    )):
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

    # Subprocess path
    sub_results = [grader.grade_deterministic(transcript, e) for e in expectations]

    # Inline path
    inline_results = [inline_evaluator.check_expectation_inline(transcript, e) for e in expectations]

    # Build comparable structures
    sub_grading = {"expectations": sub_results, "summary": {
        "passed": sum(r["passed"] for r in sub_results),
        "pass_rate": sum(r["passed"] for r in sub_results) / len(sub_results)
    }}
    inline_grading = {"expectations": inline_results, "summary": {
        "passed": sum(r["passed"] for r in inline_results),
        "pass_rate": sum(r["passed"] for r in inline_results) / len(inline_results)
    }}

    assert_full_parity(inline_grading, sub_grading)
```

- [ ] **Step 2: Run parity test**

```bash
cd hacienda-maker && pytest tests/test_parity.py -v
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add hacienda-maker/tests/test_parity.py
git commit -m "test: add parity tests for inline vs subprocess evaluation"
```

---

## Task 10: Update optimize-loop.md

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/references/optimize-loop.md`

- [ ] **Step 1: Update Phase 5 to document inline evaluation**

Update the Phase 5 section in `optimize-loop.md` to clarify inline evaluation is now the default:

```markdown
## Phase 5: Evaluate (Inline)

**IMPORTANT**: All evaluation happens INLINE within this session. Do NOT spawn external processes.

### 5.1 Trigger Evaluation (Inline)

For each query in `evals/trigger-eval.json`:
1. Read SKILL.md description
2. Use keyword overlap + intent pattern matching
3. Determine if query matches skill purpose
4. Check against `should_trigger` field
5. Compute pass rate

### 5.2 Functional Evaluation (Inline)

For each eval in `evals/evals.json`:
1. Read the prompt and expectations
2. Execute the prompt (respond as the skill would)
3. Check output against expectations:
   - For "contains" type: check if text appears in output (inline)
   - For "semantic" type: judge if expectation is met (inline judgment)
4. Record pass/fail for each expectation
5. Compute median pass rate per eval

### 5.3 Score Calculation

```
combined = trigger_score * 0.4 + functional_score * 0.6
delta = combined - history.best_score
is_improvement = delta > noise_floor
```
```

- [ ] **Step 2: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/references/optimize-loop.md
git commit -m "docs: update optimize-loop to clarify inline evaluation is default"
```

---

## Task 11: Run Full Test Suite

- [ ] **Step 1: Run all tests**

```bash
cd hacienda-maker && pytest tests/ -v
```
Expected: All tests pass

- [ ] **Step 2: Run baseline evaluation to verify end-to-end**

```bash
cd hacienda-maker && python skills/hacienda-maker/scripts/run_evals.py --generate-transcripts --grade --score --baseline
```
Expected: Completes without error, produces evals/last-run.json

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(hacienda): complete eval/grading enhancement

- Fix JSON parse failures with robust parsing
- Add expectation normalization with alternative key support
- Implement inline evaluator for optimize loop speed
- Add parallel transcript generation with ordering
- Add batched semantic grading for fewer Claude calls
- Add comprehensive test coverage

Fixes: JSON parse, semantic grading, expectation format, timeout issues
Performance: < 2 min per iteration (down from 5-10 min)"
```

---

## Summary

| Task | Files | Tests |
|------|-------|-------|
| 1. Expectation normalization | grader.py | 7 |
| 2. Robust JSON parsing | grader.py | 4 |
| 3. Inline deterministic | inline_evaluator.py | 11 |
| 4. Inline trigger | inline_evaluator.py | 4 |
| 5. Semantic parsing | inline_evaluator.py | 5 |
| 6. Parallel generation | run_evals.py | 2 |
| 7. Batched semantic | run_evals.py | 2 |
| 8. Integrate batch mode | run_evals.py | - |
| 9. Parity tests | test_parity.py | 1 |
| 10. Update docs | optimize-loop.md | - |
| 11. Full verification | all | all |

**Total new tests:** 36+
**Expected performance improvement:** 60-80% faster optimize loop iterations
