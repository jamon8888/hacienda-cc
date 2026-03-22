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
   - Parallel transcript generation
   - Retry logic with exponential backoff

2. **Implement true inline evaluation** for optimize loop:
   - Inline trigger matching (keyword/pattern matching)
   - Inline deterministic expectation checking
   - Inline semantic evaluation (Claude judges its own outputs)
   - No subprocess spawning in optimize loop

3. **Unified interface** - both paths produce identical JSON

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

## Component Design

### 1. Inline Evaluator (NEW)

**File:** `skills/hacienda-maker/scripts/inline_evaluator.py`

#### 1.1 Trigger Evaluation (Inline)

Match queries against skill description without subprocess:

```python
def evaluate_trigger_inline(queries: list, skill_description: str) -> dict:
    """Match queries against skill description without subprocess."""
    results = []
    for q in queries:
        # Keyword overlap analysis
        query_words = set(q["query"].lower().split())
        desc_words = set(skill_description.lower().split())
        overlap = len(query_words & desc_words) / max(len(query_words), 1)

        # Intent pattern matching (configurable patterns)
        triggered = overlap > 0.3 or matches_intent_pattern(q["query"], skill_description)

        results.append({
            "query": q["query"],
            "should_trigger": q["should_trigger"],
            "triggered": triggered,
            "pass": triggered == q["should_trigger"]
        })
    return results
```

**Why this works:** Trigger evaluation is fundamentally about keyword/intent matching. No LLM needed.

#### 1.2 Deterministic Expectations (Inline)

String/regex operations without subprocess:

```python
def check_expectation_inline(transcript: str, expectation: dict) -> dict:
    """Check expectation without subprocess."""
    etype = expectation.get("type", "contains")
    text = expectation["text"]

    if etype == "contains":
        passed = text.lower() in transcript.lower()
    elif etype == "not_contains":
        passed = text.lower() not in transcript.lower()
    elif etype == "regex":
        passed = re.search(text, transcript) is not None
    elif etype == "json_valid":
        try: json.loads(transcript); passed = True
        except: passed = False
    elif etype == "max_words":
        passed = len(transcript.split()) <= int(text)
    else:
        raise ValueError(f"Unknown type: {etype}")

    return {"text": text, "type": etype, "passed": passed,
            "evidence": text if passed else "Not found",
            "grader_type": "deterministic"}
```

#### 1.3 Semantic Expectations (Inline)

Claude evaluates within the current session. The optimize loop already runs in Claude. Instead of spawning a subprocess to ask "does this meet the expectation?", Claude judges directly.

**Protocol (in SKILL.md):**

```markdown
## Inline Semantic Evaluation Protocol

When running inline evaluation for semantic expectations:

1. Read the transcript
2. For each semantic expectation, judge:
   - Does the transcript satisfy the expectation?
   - Provide verbatim evidence or "Not found"
3. Return structured JSON with results
```

### 2. Subprocess Path Fixes

#### 2.1 Parallel Transcript Generation

Use `concurrent.futures.ThreadPoolExecutor` for parallel processing:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def generate_transcripts_parallel(entries: list, max_workers: int = 4) -> list:
    """Generate transcripts in parallel."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_claude, entry): entry
            for entry in entries
        }
        for future in as_completed(futures):
            entry = futures[future]
            try:
                transcript = future.result(timeout=60)
                results.append((entry, transcript))
            except TimeoutError:
                results.append((entry, None))  # Handle gracefully
    return results
```

**Speedup:** 4 workers = ~4x faster for transcript generation phase.

#### 2.2 Batched Semantic Grading

Batch all semantic expectations into single LLM call instead of one spawn per expectation:

```python
def grade_semantic_batch(transcript: str, expectations: list) -> list:
    """Grade multiple semantic expectations in one LLM call."""
    exp_list = "\n".join(f"{i}. {e['text']}" for i, e in enumerate(expectations))
    prompt = f"""Transcript:
{transcript}

Expectations to evaluate:
{exp_list}

For each expectation, respond with JSON array:
[{{"idx": 0, "passed": true, "evidence": "quote"}}, ...]"""

    result = subprocess.run(["claude", "-p", prompt, "--output-format", "json"],
                           capture_output=True, text=True, timeout=120)
    # Parse and return results
```

**Speedup:** If 5 semantic expectations → 5x fewer Claude spawns.

#### 2.3 Robust JSON Parsing

Schema validation with clear error messages:

```python
def parse_grader_response(raw: str) -> dict:
    """Parse grader response with validation."""
    try:
        outer = json.loads(raw)
        # Handle both wrapped and unwrapped formats
        inner_raw = outer.get("result", raw) if isinstance(outer, dict) else raw
        inner = json.loads(inner_raw) if isinstance(inner_raw, str) else inner_raw

        # Validate required fields
        if "passed" not in inner:
            raise ValueError("Missing 'passed' field")
        return inner
    except json.JSONDecodeError as e:
        return {"passed": False, "evidence": f"JSON parse error: {e}"}
```

#### 2.4 Expectation Format Normalization

Normalize early, validate schema:

```python
EXPECTATION_SCHEMA = {
    "text": str,
    "type": str,  # contains|not_contains|regex|json_valid|max_words|semantic
}

def normalize_expectation(exp) -> dict:
    """Convert any expectation format to canonical dict."""
    if isinstance(exp, str):
        return {"text": exp, "type": "contains"}
    if isinstance(exp, dict):
        # Validate required fields
        if "text" not in exp:
            raise ValueError(f"Expectation missing 'text': {exp}")
        exp.setdefault("type", "contains")
        return exp
    raise ValueError(f"Invalid expectation type: {type(exp)}")
```

### 3. Unified Interface

#### 3.1 Shared Output Schema

Both inline and subprocess paths produce identical JSON:

```json
{
  "eval_id": "eval-001",
  "run_id": "run-1",
  "transcript_path": "evals/transcripts/eval-001-run-1.md",
  "expectations": [
    {
      "text": "GDPR compliance",
      "type": "contains",
      "grader_type": "deterministic",
      "passed": true,
      "evidence": "GDPR compliance"
    },
    {
      "text": "tone is professional",
      "type": "semantic",
      "grader_type": "llm",
      "passed": true,
      "evidence": "The response maintains a formal..."
    }
  ],
  "summary": {
    "passed": 2,
    "failed": 0,
    "total": 2,
    "pass_rate": 1.0
  }
}
```

#### 3.2 Evaluator Interface

```python
# inline_evaluator.py
class InlineEvaluator:
    """Evaluate plugins within current Claude session."""

    def evaluate_trigger(self, queries: list, skill_description: str) -> dict:
        """Inline trigger evaluation."""
        ...

    def evaluate_functional(self, evals: list) -> dict:
        """Inline functional evaluation."""
        ...

    def compute_score(self, trigger_result: dict, functional_result: dict,
                      weights: dict) -> dict:
        """Compute combined score."""
        ...

# run_evals.py (updated)
def mode_generate_transcripts(cwd: Path, parallel: bool = True, workers: int = 4):
    """Generate transcripts (optionally parallel)."""
    ...

def mode_grade(cwd: Path, batch_semantic: bool = True):
    """Grade transcripts (optionally batch semantic)."""
    ...
```

#### 3.3 Optimize Loop Integration

```markdown
## Phase 5: Evaluate (Updated)

Choose evaluation path based on context:

**Inline Path** (default for optimize loop):
1. Call InlineEvaluator methods directly
2. No subprocess spawns
3. Results available immediately

**Subprocess Path** (fallback/debug):
1. Call run_evals.py --generate-transcripts --parallel
2. Call run_evals.py --grade --batch-semantic
3. Call run_evals.py --score
```

### 4. Error Handling

#### 4.1 Timeout Handling

```python
class TimeoutStrategy:
    """Graceful timeout handling with configurable retries."""

    def __init__(self, timeout: int = 60, retries: int = 2):
        self.timeout = timeout
        self.retries = retries

    def execute_with_retry(self, func, *args) -> tuple[bool, str]:
        """Execute with exponential backoff retry."""
        for attempt in range(self.retries + 1):
            try:
                result = func(*args, timeout=self.timeout * (attempt + 1))
                return True, result
            except TimeoutError:
                if attempt == self.retries:
                    return False, f"Timeout after {self.timeout * (attempt + 1)}s"
                time.sleep(2 ** attempt)  # Exponential backoff
        return False, "Max retries exceeded"
```

**Inline path benefit:** No subprocess timeout - Claude evaluates directly.

#### 4.2 Malformed Input Recovery

```python
def safe_parse_transcript(path: Path) -> tuple[bool, str]:
    """Read transcript with encoding handling."""
    try:
        content = path.read_text(encoding='utf-8')
        return True, content
    except UnicodeDecodeError:
        # Try common encodings
        for enc in ['latin-1', 'cp1252', 'utf-16']:
            try:
                return True, path.read_text(encoding=enc)
            except:
                continue
        return False, "Unable to decode transcript"
    except FileNotFoundError:
        return False, "Transcript not found"
```

#### 4.3 Expectation Validation Errors

```python
def validate_expectations(expectations: list) -> tuple[list, list]:
    """Validate and normalize with clear errors."""
    errors = []
    valid = []

    for i, exp in enumerate(expectations):
        try:
            normalized = normalize_expectation(exp)
            # Validate type is known
            valid_types = {"contains", "not_contains", "regex", "json_valid", "max_words", "semantic"}
            if normalized["type"] not in valid_types:
                errors.append(f"Expectation {i}: unknown type '{normalized['type']}'")
                continue
            valid.append(normalized)
        except ValueError as e:
            errors.append(f"Expectation {i}: {e}")

    return valid, errors
```

Output includes errors for debugging:
```json
{
  "expectations": [...],
  "validation_errors": ["Expectation 2: unknown type 'fuzzy'"]
}
```

#### 4.4 Partial Failure Handling

```python
def grade_with_partial_failure(transcript: str, expectations: list) -> dict:
    """Grade even if some expectations fail."""
    results = []
    failed_count = 0

    for exp in expectations:
        try:
            if exp["type"] == "semantic":
                result = grade_semantic_single(transcript, exp)
            else:
                result = check_expectation_inline(transcript, exp)
            if not result["passed"]:
                failed_count += 1
        except Exception as e:
            result = {
                "text": exp["text"],
                "type": exp["type"],
                "passed": False,
                "evidence": f"Error: {e}",
                "grader_type": "error"
            }
            failed_count += 1
        results.append(result)

    return {
        "expectations": results,
        "summary": {
            "passed": len(results) - failed_count,
            "failed": failed_count,
            "total": len(results),
            "pass_rate": (len(results) - failed_count) / len(results)
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

1. **Unit tests** for each component:
   - `test_inline_evaluator.py` - Test inline trigger/expectation logic
   - `test_grader.py` - Updated for new parsing/validation
   - `test_run_evals.py` - Test parallel generation and batch grading

2. **Integration tests**:
   - Run full optimize loop with inline evaluator
   - Compare inline vs subprocess results for parity

3. **Performance benchmarks**:
   - Measure time before/after for optimize loop iteration
   - Target: < 2 minutes per iteration (down from 5-10 min)

## Migration Plan

1. **Phase 1:** Add inline_evaluator.py without changing optimize loop
2. **Phase 2:** Fix subprocess path (parallel + batched)
3. **Phase 3:** Update optimize loop to use inline by default
4. **Phase 4:** Remove deprecated code paths

## Success Metrics

| Metric | Before | After |
|--------|--------|-------|
| JSON parse failures | Frequent | Zero |
| Semantic grading errors | Inconsistent | Reliable |
| Expectation format errors | Occasional | Validated early |
| Timeout failures | No retry | 2 retries with backoff |
| Optimize loop time | 5-10 min | < 2 min |
| Claude spawns per iteration | ~20-50 | 0 (inline) or ~5 (parallel) |