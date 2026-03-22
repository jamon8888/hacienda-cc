# Hacienda-Maker Eval & Grading Enhancement Design

**Date:** 2026-03-22
**Status:** Draft
**Author:** Claude + User

## Problem Statement

The hacienda-maker eval and grading system has four critical bugs:
1. **JSON parse failures** - Double JSON decode in semantic grader is fragile
2. **Semantic grading issues** - Inconsistent results and wrong scoring
3. **Expectation format errors** - String vs object handling causes failures
4. **Timeout failures** - No retry logic, single timeout = failure

Additionally, performance is too slow:
- **5-10 minutes per optimize loop iteration** - unacceptable for fast iteration
- Subprocess spawning for each transcript and each semantic expectation
- Sequential processing with no parallelization

## Solution Overview

**Approach: Hybrid - Fix Both Paths**

1. **Fix subprocess path** for reliability:
   - Robust JSON parsing with schema validation
   - Batch semantic expectations into single LLM call
   - Parallel transcript generation with ordering preservation
   - Retry logic with exponential backoff

2. **Implement true inline evaluation** for optimize loop:
   - Inline trigger matching (keyword/pattern matching)
   - Inline deterministic expectation checking
   - Inline semantic evaluation (Claude judges its own outputs)
   - No subprocess spawning in optimize loop

3. **Unified interface** - both paths produce identical JSON with exact schema

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         optimize loop                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                 Inline Evaluator (NEW)                      ││
│  │  • Trigger matching via pattern/keyword analysis            ││
│  │  • Deterministic expectations: regex/contains inline        ││
│  │  • Semantic expectations: Claude judges output directly     ││
│  │  • No subprocess spawns, single-pass evaluation             ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      run_evals.py (FIXED)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ --generate   │  │   --grade    │  │   --score    │          │
│  │  transcripts │→ │   (fixed)    │→ │   (unchanged)│          │
│  │  (parallel)  │  │  (batched)   │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## Ground-Truth Output Schema

Both inline and subprocess paths MUST produce JSON conforming to this exact schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "GradingResult",
  "type": "object",
  "required": ["eval_id", "run_id", "transcript_path", "expectations", "summary"],
  "properties": {
    "eval_id": { "type": "string" },
    "run_id": { "type": "string", "pattern": "^run-[0-9]+$" },
    "transcript_path": { "type": "string" },
    "expectations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["text", "type", "grader_type", "passed", "evidence"],
        "properties": {
          "text": { "type": "string" },
          "type": { "enum": ["contains", "not_contains", "regex", "json_valid", "max_words", "semantic"] },
          "grader_type": { "enum": ["deterministic", "llm", "error"] },
          "passed": { "type": "boolean" },
          "evidence": { "type": "string" }
        }
      }
    },
    "summary": {
      "type": "object",
      "required": ["passed", "failed", "total", "pass_rate"],
      "properties": {
        "passed": { "type": "integer", "minimum": 0 },
        "failed": { "type": "integer", "minimum": 0 },
        "total": { "type": "integer", "minimum": 0 },
        "pass_rate": { "type": "number", "minimum": 0, "maximum": 1 }
      }
    },
    "validation_errors": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

**Parity verification:** Integration tests MUST verify FULL structural equality:

```python
def assert_full_parity(inline_result: Dict, subprocess_result: Dict):
    """Verify complete structural equality, not just passed booleans."""
    import json

    # Serialize both to canonical JSON for comparison
    inline_json = json.dumps(inline_result, sort_keys=True, indent=2)
    sub_json = json.dumps(subprocess_result, sort_keys=True, indent=2)

    assert inline_json == sub_json, (
        f"Parity mismatch:\n"
        f"Inline: {inline_json[:500]}...\n"
        f"Subprocess: {sub_json[:500]}..."
    )

    # Explicit field-by-field verification
    assert inline_result["eval_id"] == subprocess_result["eval_id"]
    assert inline_result["summary"]["pass_rate"] == subprocess_result["summary"]["pass_rate"]

    # Evidence strings must match (not just passed booleans)
    for i, (inline_exp, sub_exp) in enumerate(zip(
        inline_result["expectations"], subprocess_result["expectations"]
    )):
        assert inline_exp["text"] == sub_exp["text"], f"Expectation {i} text mismatch"
        assert inline_exp["type"] == sub_exp["type"], f"Expectation {i} type mismatch"
        assert inline_exp["grader_type"] == sub_exp["grader_type"], f"Expectation {i} grader_type mismatch"
        assert inline_exp["passed"] == sub_exp["passed"], f"Expectation {i} passed mismatch"
        # Evidence must match for deterministic expectations
        if inline_exp["grader_type"] == "deterministic":
            assert inline_exp["evidence"] == sub_exp["evidence"], f"Expectation {i} evidence mismatch"
```

## Component Design

### 1. Inline Evaluator (NEW)

**File:** `skills/hacienda-maker/scripts/inline_evaluator.py`

#### 1.1 Trigger Evaluation (Inline)

Match queries against skill description without subprocess:

```python
import re
from typing import List, Dict

# Intent patterns for common skill trigger scenarios
INTENT_PATTERNS = [
    (r'\b(build|create|make|generate|design|develop)\b', 'creation'),
    (r'\b(fix|repair|debug|solve|resolve)\b', 'fixing'),
    (r'\b(analyze|review|check|audit|inspect)\b', 'analysis'),
    (r'\b(optimize|improve|enhance|refactor)\b', 'optimization'),
    (r'\b(test|validate|verify|ensure)\b', 'testing'),
]

def matches_intent_pattern(query: str, skill_description: str) -> bool:
    """Check if query intent matches skill purpose using pattern matching."""
    query_lower = query.lower()
    desc_lower = skill_description.lower()

    for pattern, intent_type in INTENT_PATTERNS:
        if re.search(pattern, query_lower):
            # If query has this intent, check if description mentions it
            if intent_type in desc_lower or re.search(pattern, desc_lower):
                return True
    return False

def evaluate_trigger_inline(queries: list, skill_description: str) -> dict:
    """Match queries against skill description without subprocess.

    Calibration: This must match existing subprocess trigger evaluation semantics.
    Run calibration tests against trigger-eval.json results before deployment.
    """
    results = []
    for q in queries:
        # Keyword overlap analysis
        query_words = set(q["query"].lower().split())
        desc_words = set(skill_description.lower().split())
        # Remove common stop words for better matching
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'to', 'of', 'in', 'for', 'on', 'with'}
        query_words = query_words - stop_words
        desc_words = desc_words - stop_words

        overlap = len(query_words & desc_words) / max(len(query_words), 1)

        # Intent pattern matching
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

**Calibration Plan:**
1. Run existing subprocess trigger evaluation on baseline plugin
2. Run inline trigger evaluation on same plugin
3. Compare pass rates - must be within 5% variance
4. Adjust overlap threshold (currently 0.3) if needed
5. Document any intentional semantic differences

#### 1.2 Deterministic Expectations (Inline)

String/regex operations without subprocess:

```python
import json
import re
from typing import Dict, Tuple

def check_expectation_inline(transcript: str, expectation: dict) -> dict:
    """Check expectation without subprocess.

    Handles edge cases:
    - Empty transcript: all expectations fail
    - Invalid regex: returns error
    - json_valid: extracts JSON from markdown OR plain text
    - max_words: proper word counting with punctuation normalization
    """
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
            # Try multiple JSON extraction strategies in order:
            # 1. Markdown code block with json tag: ```json ... ```
            # 2. Markdown code block without tag: ``` ... ```
            # 3. Inline JSON object/array in text: {...} or [...]
            # 4. Entire transcript as JSON

            json_patterns = [
                r'```json\s*([\s\S]*?)```',      # Explicit json tag
                r'```\s*([\s\S]*?)```',           # Generic code block
                r'(\{[\s\S]*\})',                 # JSON object
                r'(\[[\s\S]*\])',                 # JSON array
            ]

            parsed = False
            for pattern in json_patterns:
                match = re.search(pattern, transcript)
                if match:
                    content = match.group(1).strip()
                    try:
                        json.loads(content)
                        passed = True
                        evidence = f"Valid JSON (extracted via pattern: {pattern[:20]}...)"
                        parsed = True
                        break
                    except json.JSONDecodeError:
                        continue

            if not parsed:
                # Try entire transcript as last resort
                try:
                    json.loads(transcript)
                    passed = True
                    evidence = "Valid JSON (full transcript)"
                except json.JSONDecodeError as e:
                    passed = False
                    evidence = f"No valid JSON found: {e}"

        elif etype == "max_words":
            # Proper word counting with punctuation normalization
            import re

            # Normalize: replace punctuation with spaces, collapse multiple spaces
            normalized = re.sub(r'[^\w\s]', ' ', transcript)
            normalized = re.sub(r'\s+', ' ', normalized).strip()

            # Split on whitespace
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

#### 1.3 Semantic Expectations (Inline)

Claude evaluates within the current session with structured output contract:

**Prompt Construction:**

```python
def build_semantic_prompt(transcript: str, expectations: List[Dict]) -> str:
    """Build prompt for inline semantic evaluation."""
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

Requirements:
- Evidence MUST be a verbatim quote from the transcript, or "Not found"
- If passed is false, evidence should explain why
- Respond with exactly {len(expectations)} JSON objects, one per line"""
```

**Output Parsing Contract:**

```python
def parse_semantic_response(response: str, expectations: List[Dict]) -> List[Dict]:
    """Parse Claude's response into structured results.

    MUST return exactly len(expectations) results.

    Handles these edge cases in order:
    1. Wrapped in Claude CLI format: {"result": "..."}
    2. Top-level array: [...]
    3. One JSON object per line
    4. Fewer/more lines than expected
    5. Malformed JSON on any line
    """
    raw = response.strip()

    # Step 1: Handle Claude CLI wrapper {"result": "..."}
    try:
        outer = json.loads(raw)
        if isinstance(outer, dict) and "result" in outer:
            raw = outer["result"]
            # result might be string or already parsed
            if isinstance(raw, str):
                raw = raw.strip()
    except json.JSONDecodeError:
        pass  # Not wrapped, continue with raw

    # Step 2: Try parsing as top-level array
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            lines = [json.dumps(obj) for obj in arr]
        else:
            lines = [json.dumps(arr)]  # Single object, not array
    except json.JSONDecodeError:
        # Step 3: Parse as one JSON object per line
        lines = [l.strip() for l in raw.split('\n') if l.strip()]

    # Step 4: Build results, handling count mismatch
    results = []
    for i, exp in enumerate(expectations):
        if i < len(lines):
            try:
                obj = json.loads(lines[i])
                idx = obj.get("idx", i)
                passed = bool(obj.get("passed", False))
                evidence = str(obj.get("evidence", "No evidence provided"))
                # Validate idx matches
                if idx != i:
                    evidence = f"idx mismatch: expected {i}, got {idx}"
            except json.JSONDecodeError as e:
                passed = False
                evidence = f"JSON parse error: {e}"
        else:
            # Fewer lines than expectations
            passed = False
            evidence = "Missing response line"

        results.append({
            "text": exp["text"],
            "type": "semantic",
            "passed": passed,
            "evidence": evidence,
            "grader_type": "llm"
        })

    # Step 5: Log warning if more lines than expectations (don't fail)
    if len(lines) > len(expectations):
        import sys
        print(f"WARNING: {len(lines)} response lines but only {len(expectations)} expectations",
              file=sys.stderr)

    return results
```

### 2. Subprocess Path Fixes

#### 2.1 Parallel Transcript Generation

Use `concurrent.futures.ThreadPoolExecutor` with ordering preservation:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
import time

def generate_transcripts_parallel(entries: List[dict], max_workers: int = 4,
                                  timeout_per_entry: int = 60,
                                  retries: int = 2) -> List[Tuple[dict, Optional[str]]]:
    """Generate transcripts in parallel with ordering preserved.

    Returns list of (entry, transcript) tuples in same order as input entries.
    """
    def run_with_retry(entry: dict) -> Tuple[int, Optional[str]]:
        """Run transcript generation with exponential backoff retry."""
        idx = entry.get("_index", 0)
        for attempt in range(retries + 1):
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
                time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
            except Exception as e:
                return (idx, None)
        return (idx, None)

    # Add index to each entry for ordering
    indexed_entries = [{**e, "_index": i} for i, e in enumerate(entries)]

    # Execute in parallel
    results = [None] * len(entries)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_with_retry, entry): entry for entry in indexed_entries}
        for future in as_completed(futures):
            idx, transcript = future.result()
            results[idx] = (entries[idx], transcript)

    return results
```

**Ordering guarantee:** Results are returned in same order as input entries using index tracking.

#### 2.2 Batched Semantic Grading

Batch all semantic expectations into single LLM call with exact output format:

```python
def grade_semantic_batch(transcript: str, expectations: List[Dict],
                        timeout: int = 120) -> List[Dict]:
    """Grade multiple semantic expectations in one LLM call.

    Output format is EXACTLY one JSON object per line, no wrapping.
    """
    if not expectations:
        return []

    exp_list = "\n".join(f"{i}. {e['text']}" for i, e in enumerate(expectations))
    prompt = f"""Evaluate the following transcript against each expectation.

<transcript>
{transcript}
</transcript>

<expectations>
{exp_list}
</expectations>

For each expectation, respond with a JSON object on its own line:
{{"idx": <number>, "passed": true|false, "evidence": "<verbatim quote or 'Not found'>"}}

Respond with exactly {len(expectations)} JSON objects, one per line. No wrapping, no markdown."""

    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True, timeout=timeout
    )

    # Parse response - NO double decode
    try:
        # Claude CLI with --output-format json wraps in {"result": "..."}
        outer = json.loads(result.stdout)
        raw_response = outer.get("result", result.stdout)
    except json.JSONDecodeError:
        raw_response = result.stdout

    # Parse each line as separate JSON object
    return parse_semantic_response(raw_response, expectations)
```

**Key fix:** Single decode path, explicit format specification in prompt.

#### 2.3 Robust JSON Parsing

Schema validation with clear error messages:

```python
import json
from typing import Dict, Any, Optional

def parse_grader_response(raw: str) -> Dict[str, Any]:
    """Parse grader response with validation.

    Handles both wrapped (Claude CLI output) and unwrapped formats.
    Returns validated dict or error dict.
    """
    try:
        outer = json.loads(raw)

        # Handle Claude CLI wrapped format: {"result": "{...}"}
        if isinstance(outer, dict) and "result" in outer:
            inner_raw = outer["result"]
            inner = json.loads(inner_raw) if isinstance(inner_raw, str) else inner_raw
        else:
            inner = outer

        # Validate required fields
        if "passed" not in inner:
            return {"passed": False, "evidence": "Missing 'passed' field in response"}

        # Ensure boolean
        inner["passed"] = bool(inner.get("passed", False))

        # Ensure evidence exists
        inner.setdefault("evidence", "No evidence provided")

        return inner

    except json.JSONDecodeError as e:
        return {"passed": False, "evidence": f"JSON parse error: {e}"}
```

#### 2.4 Expectation Format Normalization

Normalize early, validate schema, handle all known formats:

```python
from typing import Union, Dict, List, Tuple

VALID_EXPECTATION_TYPES = {"contains", "not_contains", "regex", "json_valid", "max_words", "semantic"}

# Alternative key names that map to "text"
TEXT_KEY_ALIASES = {"text", "pattern", "regex", "value", "expectation", "query"}

def normalize_expectation(exp: Union[str, Dict]) -> Dict:
    """Convert any expectation format to canonical dict.

    Handles:
    - String expectations -> {"text": str, "type": "contains"}
    - Dict with "text" key -> standard format
    - Dict with alternative keys (pattern, regex, value) -> maps to "text"
    - Dict with "grader_type" -> ignored (not part of expectation input)
    - Malformed text (non-string) -> converted to string

    Raises:
        ValueError: If no recognizable text field found or invalid type.
    """
    if isinstance(exp, str):
        return {"text": exp, "type": "contains"}

    if isinstance(exp, dict):
        result = exp.copy()

        # Find text field from various possible keys
        text_value = None
        for key in TEXT_KEY_ALIASES:
            if key in result:
                text_value = result.pop(key)  # Remove alias
                break

        if text_value is None:
            raise ValueError(f"Expectation missing text field (tried: {TEXT_KEY_ALIASES}): {exp}")

        # Ensure text is string
        if not isinstance(text_value, str):
            text_value = str(text_value)

        result["text"] = text_value

        # Set default type
        result.setdefault("type", "contains")

        # Validate type
        if result["type"] not in VALID_EXPECTATION_TYPES:
            raise ValueError(f"Invalid expectation type '{result['type']}'. Valid: {VALID_EXPECTATION_TYPES}")

        # Remove grader_type if present (not an input field)
        result.pop("grader_type", None)
        result.pop("passed", None)
        result.pop("evidence", None)

        return result

    raise ValueError(f"Expectation must be string or dict, got {type(exp).__name__}")

def normalize_all_expectations(expectations: List) -> Tuple[List[Dict], List[str]]:
    """Normalize all expectations, returning (valid_list, error_list)."""
    valid = []
    errors = []
    for i, exp in enumerate(expectations):
        try:
            valid.append(normalize_expectation(exp))
        except ValueError as e:
            errors.append(f"Expectation {i}: {e}")
    return valid, errors
```

### 3. Unified Interface

#### 3.1 Evaluator Interface

```python
# inline_evaluator.py
class InlineEvaluator:
    """Evaluate plugins within current Claude session."""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.trigger_threshold = self.config.get("trigger_threshold", 0.3)

    def evaluate_trigger(self, queries: List[Dict], skill_description: str) -> Dict:
        """Inline trigger evaluation.

        Args:
            queries: List of {"query": str, "should_trigger": bool}
            skill_description: SKILL.md description text

        Returns:
            {"queries": [...], "total_queries": int, "trigger_score": float}
        """
        ...

    def evaluate_functional(self, evals: List[Dict]) -> Dict:
        """Inline functional evaluation.

        Args:
            evals: List of {"id": str, "prompt": str, "expectations": [...]}

        Returns:
            {"evals": [...], "functional_score": float}
        """
        ...

    def compute_score(self, trigger_result: Dict, functional_result: Dict,
                      weights: Dict) -> Dict:
        """Compute combined score.

        Args:
            trigger_result: Output from evaluate_trigger
            functional_result: Output from evaluate_functional
            weights: {"trigger": float, "functional": float}

        Returns:
            {"combined": float, "delta": float, "is_improvement": bool}
        """
        ...
```

#### 3.2 Timeout Integration

**TimeoutStrategy** is wired into ALL subprocess operations:

```python
import time
from typing import Callable, TypeVar, Tuple

T = TypeVar('T')

class TimeoutStrategy:
    """Graceful timeout handling with configurable retries.

    Wired into:
    - Transcript generation (generate_transcripts_parallel)
    - Batch semantic grading (grade_semantic_batch)
    - Single semantic grading (grade_semantic_single)
    """

    def __init__(self, timeout: int = 60, retries: int = 2):
        self.timeout = timeout
        self.retries = retries
        self.total_timeout_budget = timeout * (2 ** retries - 1)  # Geometric series

    def execute(self, func: Callable[..., T], *args) -> Tuple[bool, T]:
        """Execute with exponential backoff retry.

        Returns: (success, result_or_error_message)
        """
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                current_timeout = self.timeout * (attempt + 1)
                result = func(*args, timeout=current_timeout)
                return True, result
            except TimeoutError as e:
                last_error = f"Timeout after {current_timeout}s"
                if attempt < self.retries:
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s...
            except Exception as e:
                last_error = str(e)
                break

        return False, last_error or "Unknown error"


# === WIRING INTO SUBPROCESS PATHS ===

def run_transcript_with_timeout(entry: dict, timeout_strategy: TimeoutStrategy) -> Tuple[dict, Optional[str]]:
    """Generate transcript with timeout strategy applied."""
    def _run(timeout: int):
        return subprocess.run(
            ["claude", "-p", entry["prompt"], "--plugin-dir", str(cwd)],
            capture_output=True, text=True, timeout=timeout
        )

    success, result = timeout_strategy.execute(_run)
    if success:
        return (entry, result.stdout)
    return (entry, None)


def grade_semantic_batch_with_timeout(transcript: str, expectations: List[Dict],
                                       timeout_strategy: TimeoutStrategy) -> List[Dict]:
    """Batch semantic grading with timeout strategy applied."""
    def _run(timeout: int):
        prompt = build_semantic_prompt(transcript, expectations)
        return subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=timeout
        )

    success, result = timeout_strategy.execute(_run)
    if not success:
        # Return all failures with timeout message
        return [{
            "text": e["text"],
            "type": "semantic",
            "passed": False,
            "evidence": result,  # Error message
            "grader_type": "llm"
        } for e in expectations]

    return parse_semantic_response(result.stdout, expectations)


# Default timeout configurations for each operation type
DEFAULT_TIMEOUTS = {
    "transcript_generation": TimeoutStrategy(timeout=60, retries=2),
    "semantic_batch": TimeoutStrategy(timeout=120, retries=1),
    "semantic_single": TimeoutStrategy(timeout=60, retries=1),
}
```

**Inline path note:** No timeout handling needed - Claude evaluates directly within session context.

### 4. Error Handling

#### 4.1 Empty Expectations Edge Case

```python
def grade_with_partial_failure(transcript: str, expectations: List[Dict]) -> Dict:
    """Grade even if some expectations fail. Handles empty list."""
    if not expectations:
        return {
            "expectations": [],
            "summary": {
                "passed": 0,
                "failed": 0,
                "total": 0,
                "pass_rate": 1.0  # Edge case: empty = perfect pass rate
            },
            "validation_errors": ["Empty expectations list"]
        }

    results = []
    failed_count = 0

    for exp in expectations:
        try:
            if exp.get("type") == "semantic":
                result = grade_semantic_single(transcript, exp)
            else:
                result = check_expectation_inline(transcript, exp)
            if not result["passed"]:
                failed_count += 1
        except Exception as e:
            result = {
                "text": exp.get("text", ""),
                "type": exp.get("type", "unknown"),
                "passed": False,
                "evidence": f"Error: {e}",
                "grader_type": "error"
            }
            failed_count += 1
        results.append(result)

    total = len(results)
    return {
        "expectations": results,
        "summary": {
            "passed": total - failed_count,
            "failed": failed_count,
            "total": total,
            "pass_rate": (total - failed_count) / total if total > 0 else 1.0
        }
    }
```

## Files Changed

| File | Change |
|------|--------|
| `skills/hacienda-maker/scripts/inline_evaluator.py` | NEW - Inline evaluation logic |
| `skills/hacienda-maker/scripts/run_evals.py` | Add parallel transcript gen, batched grading |
| `skills/hacienda-maker/scripts/grader.py` | Fix JSON parsing, add retry logic |
| `skills/hacienda-maker/references/optimize-loop.md` | Update Phase 5 to use inline evaluator |
| `skills/hacienda-maker/references/inline-evaluation.md` | Update with new inline protocol |

## Testing Strategy

### Unit Tests

1. **test_inline_evaluator.py**
   - Test trigger evaluation with known queries
   - Test each expectation type (contains, regex, json_valid, etc.)
   - Test edge cases: empty transcript, invalid regex, unicode
   - Test empty expectations list

2. **test_grader.py** (updated)
   - Test new parse_grader_response with various formats
   - Test normalize_expectation with string/dict inputs
   - Test batch semantic grading output parsing

3. **test_run_evals.py** (updated)
   - Test parallel generation preserves ordering
   - Test timeout strategy retry logic
   - Test parity: inline vs subprocess results

### Integration Tests

```python
def test_inline_subprocess_parity():
    """Verify inline and subprocess paths produce FULLY identical results."""
    test_plugin = load_test_plugin()
    queries = load_trigger_queries()
    evals = load_functional_evals()

    # Run both paths
    inline_result = run_inline_evaluation(test_plugin, queries, evals)
    subprocess_result = run_subprocess_evaluation(test_plugin, queries, evals)

    # Use the full parity check defined in schema section
    assert_full_parity(inline_result, subprocess_result)

def test_runtime_mode_switching():
    """Verify HM_EVAL_MODE switches between paths correctly."""
    import os

    # Test inline mode
    os.environ["HM_EVAL_MODE"] = "inline"
    evaluator = get_evaluator({})
    assert isinstance(evaluator, InlineEvaluator)

    # Test subprocess mode
    os.environ["HM_EVAL_MODE"] = "subprocess"
    evaluator = get_evaluator({})
    assert isinstance(evaluator, SubprocessEvaluator)

    # Cleanup
    del os.environ["HM_EVAL_MODE"]
```

### Performance Benchmarks

```python
def benchmark_optimize_loop():
    """Measure time before/after optimization."""
    import time

    # Baseline (current subprocess approach)
    start = time.time()
    run_subprocess_evaluation(plugin, queries, evals)
    baseline_time = time.time() - start

    # Optimized (inline approach)
    start = time.time()
    run_inline_evaluation(plugin, queries, evals)
    optimized_time = time.time() - start

    # Target: optimized_time < baseline_time * 0.4 (60%+ improvement)
    assert optimized_time < baseline_time * 0.4, \
        f"Insufficient speedup: {optimized_time}s vs {baseline_time}s baseline"
```

## Migration Plan with Acceptance Gates

### Phase 1: Add inline_evaluator.py
**Changes:**
- Create `inline_evaluator.py` with all inline evaluation logic
- Add unit tests for inline evaluator
- No changes to existing optimize loop

**Acceptance Gate:**
```
pytest tests/test_inline_evaluator.py -v
# All tests pass
# Code coverage > 80%
```

### Phase 2: Fix subprocess path
**Changes:**
- Update `run_evals.py` with parallel generation
- Update `grader.py` with robust parsing
- Add batch semantic grading

**Acceptance Gate:**
```
pytest tests/test_run_evals.py tests/test_grader.py -v
# All tests pass
# Parity test passes (inline vs subprocess results match)
# JSON parse failures = 0 in test suite
```

### Phase 3: Update optimize loop
**Changes:**
- Update `optimize-loop.md` to use inline by default
- Add fallback to subprocess path

**Acceptance Gate:**
```
# Run optimize loop on test plugin
./run_optimize.sh --plugin test-plugin --iterations 3
# All iterations complete successfully
# Combined scores computed correctly
# No subprocess spawns in logs (verify inline path used)
```

### Phase 4: Remove deprecated paths
**Changes:**
- Remove old subprocess-only code paths
- Update documentation

**Acceptance Gate:**
```
# Full regression suite
pytest tests/ -v --integration
# All tests pass
# Performance: optimize loop time < 2 minutes
```

## Runtime Switching & Rollback Mechanics

### Environment Variable Control

```bash
# Force inline evaluation path (default for optimize loop)
HM_EVAL_MODE=inline

# Force subprocess evaluation path (for debugging/testing)
HM_EVAL_MODE=subprocess

# Auto-select based on context (default)
HM_EVAL_MODE=auto
```

### Configuration in hm.json

```json
{
  "evaluation": {
    "mode": "auto",
    "fallback_on_error": true,
    "timeout_strategy": {
      "transcript_generation": {"timeout": 60, "retries": 2},
      "semantic_batch": {"timeout": 120, "retries": 1}
    }
  }
}
```

### Rollback Triggers

Automatic rollback to subprocess path occurs when:

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Inline parse failures | > 5% of evaluations | Log warning, continue inline |
| Inline score drift | > 10% difference from subprocess | Force subprocess for next iteration |
| Inline exceptions | Any unhandled exception | Immediate fallback to subprocess |
| User override | HM_EVAL_MODE=subprocess | Respect user choice |

### Rollback Procedure

```python
def get_evaluator(config: dict) -> Union[InlineEvaluator, SubprocessEvaluator]:
    """Select evaluator based on config and runtime conditions."""
    mode = os.environ.get("HM_EVAL_MODE", config.get("evaluation", {}).get("mode", "auto"))

    if mode == "subprocess":
        return SubprocessEvaluator(config)
    elif mode == "inline":
        return InlineEvaluator(config)
    else:  # auto
        # Check for recent inline failures
        if has_recent_inline_failures(config):
            log_warning("Recent inline failures detected, using subprocess")
            return SubprocessEvaluator(config)
        return InlineEvaluator(config)
```

### Phase Rollback Criteria

If any phase fails acceptance gate:

1. **Do not proceed** to next phase
2. **Document failure** with:
   - Test output
   - Error messages
   - Environment details
3. **Automatic rollback**:
   - Set `HM_EVAL_MODE=subprocess` in environment
   - Log rollback event to `hm-results.tsv`
4. **Fix issue** before re-attempting phase
5. **If unfixable in 2 attempts**, escalate to human decision

### Regression Detection

After each phase deployment, monitor for:

```python
def detect_regression(before_metrics: dict, after_metrics: dict) -> List[str]:
    """Detect unacceptable regressions after deployment."""
    regressions = []

    # Score distribution must stay within 5%
    if abs(after_metrics["mean_score"] - before_metrics["mean_score"]) > 5:
        regressions.append(f"Score drift: {before_metrics['mean_score']} -> {after_metrics['mean_score']}")

    # Error rate must not increase
    if after_metrics["error_rate"] > before_metrics["error_rate"] * 1.1:
        regressions.append(f"Error rate increase: {before_metrics['error_rate']} -> {after_metrics['error_rate']}")

    # Latency must improve, not degrade
    if after_metrics["p95_latency"] > before_metrics["p95_latency"]:
        regressions.append(f"Latency regression: {before_metrics['p95_latency']}s -> {after_metrics['p95_latency']}s")

    return regressions
```

## Success Metrics

| Metric | Before | After | Verification |
|--------|--------|-------|--------------|
| JSON parse failures | Frequent | Zero | Unit tests |
| Semantic grading errors | Inconsistent | Reliable | Parity tests |
| Expectation format errors | Occasional | Validated early | Error tests |
| Timeout failures | No retry | 2 retries with backoff | Timeout tests |
| Optimize loop time | 5-10 min | < 2 min | Benchmark |
| Claude spawns per iteration | ~20-50 | 0 (inline) or ~5 (parallel) | Log analysis |