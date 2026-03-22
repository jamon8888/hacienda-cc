#!/usr/bin/env python3
"""run_evals.py — eval orchestrator.
Modes:
  --generate-transcripts  : run claude -p for trigger + eval prompts, write output files
  --grade                 : call grader.py for each transcript, write grading.json files
  --score [--baseline]    : read grading.json files, compute scores, write last-run.json
"""
import json
import subprocess
import sys
from pathlib import Path
from statistics import median
from collections import defaultdict


def load_state(cwd: Path) -> dict:
    return json.loads((cwd / "hm.json").read_text())

def write_state(cwd: Path, state: dict):
    (cwd / "hm.json").write_text(json.dumps(state, indent=2))


def write_failed_grading(output_path: Path, entry: dict, reason: str):
    expectations = entry.get("expectations", [])
    results = []
    for e in expectations:
        if isinstance(e, str):
            results.append({"text": e, "type": "contains",
                          "grader_type": "deterministic",
                          "passed": False, "evidence": reason})
        else:
            results.append({"text": e.get("text", ""), "type": e.get("type", "contains"),
                          "grader_type": "llm" if e.get("type") == "semantic" else "deterministic",
                          "passed": False, "evidence": reason})
    total = len(results)
    grading = {
        "eval_id": entry["eval_id"],
        "run_id": f"run-{entry['run_n']}",
        "transcript_path": entry["transcript_path"],
        "expectations": results,
        "summary": {"passed": 0, "failed": total, "total": total, "pass_rate": 0.0}
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(grading, indent=2))


def safe_pass_rate(grading: dict) -> float:
    summary = grading.get("summary", {})
    rate = summary.get("pass_rate")
    if not isinstance(rate, (int, float)):
        print("WARNING: malformed grading.json — missing pass_rate", file=sys.stderr)
        return 0.0
    return float(rate)


def mode_score(cwd: Path, baseline: bool = False):
    state = load_state(cwd)
    scoring = state["scoring"]
    history = state["history"]

    evals_dir = cwd / "evals"

    # Read trigger results
    trigger_results = json.loads((evals_dir / "trigger-results.json").read_text()) \
        if (evals_dir / "trigger-results.json").exists() else {"queries": [], "total_queries": 0}
    queries = trigger_results.get("queries", [])
    total_queries = trigger_results.get("total_queries", 0)

    # Compute trigger detail
    passed_trigger = sum(1 for q in queries if q.get("pass_rate_q", 0) >= 0.5)
    failed_trigger = total_queries - passed_trigger
    trigger_score = (passed_trigger / total_queries * 100) if total_queries > 0 else 0.0
    trigger_failures = [q["query"] for q in queries if q.get("pass_rate_q", 0) < 0.5]

    # Read transcripts-to-grade
    ttg_path = evals_dir / "transcripts-to-grade.json"
    entries = json.loads(ttg_path.read_text()) if ttg_path.exists() else []

    # Group by eval_id
    by_eval = defaultdict(list)
    for entry in entries:
        by_eval[entry["eval_id"]].append(entry)

    per_eval_medians = {}
    grading_paths = []
    for eval_id, eval_entries in by_eval.items():
        rates = []
        for entry in eval_entries:
            grading_path = cwd / entry["output_path"]
            grading_paths.append(entry["output_path"])
            if grading_path.exists():
                grading = json.loads(grading_path.read_text())
                rates.append(safe_pass_rate(grading))
        per_eval_medians[eval_id] = median(rates) if rates else 0.0

    functional_score = (sum(per_eval_medians.values()) / len(per_eval_medians) * 100) \
        if per_eval_medians else 0.0
    passed_evals = sum(1 for m in per_eval_medians.values() if m >= 0.5)
    failed_evals = len(per_eval_medians) - passed_evals

    # Determine previous_best
    best_score = history.get("best_score")
    previous_best = 0.0 if (baseline or best_score is None) else float(best_score)

    # Call score.py
    score_input = {
        "trigger_score": trigger_score,
        "functional_score": functional_score,
        "previous_best": previous_best,
        "weights": scoring["weights"],
        "noise_floor": scoring["noise_floor"]
    }
    score_proc = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "score.py")],
        input=json.dumps(score_input),
        capture_output=True, text=True
    )
    if score_proc.returncode != 0:
        print(f"score.py failed: {score_proc.stderr}", file=sys.stderr)
        sys.exit(1)
    score_out = json.loads(score_proc.stdout)

    # Build last-run.json
    last_run = {
        "trigger_score": trigger_score,
        "functional_score": functional_score,
        "combined_score": score_out["combined"],
        "delta": score_out["delta"],
        "is_improvement": score_out["is_improvement"],
        "runs": scoring["runs_per_eval"],
        "trigger_detail": {
            "passed": passed_trigger, "failed": failed_trigger, "total": total_queries,
            "failures": trigger_failures
        },
        "functional_detail": {
            "passed_evals": passed_evals, "failed_evals": failed_evals,
            "total_evals": len(per_eval_medians),
            "pass_threshold": 0.5,
            "per_eval": [{"id": eid, "median_pass_rate": m} for eid, m in per_eval_medians.items()],
            "grading_paths": grading_paths
        }
    }

    # --baseline overrides
    if baseline:
        last_run["delta"] = 0.0
        last_run["is_improvement"] = False

    (evals_dir / "last-run.json").write_text(json.dumps(last_run, indent=2))

    # Write state
    if baseline:
        state["history"]["baseline_score"] = score_out["combined"]
        if state["history"]["best_score"] is None:
            state["history"]["best_score"] = score_out["combined"]
    elif score_out["is_improvement"]:
        state["history"]["best_score"] = score_out["combined"]
        state["history"]["best_commit"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
    write_state(cwd, state)

    print(json.dumps(last_run, indent=2))


def read_skill_name(plugin_dir: Path) -> str:
    """Read skill name from SKILL.md frontmatter."""
    import re
    for skill_md in plugin_dir.glob("skills/*/SKILL.md"):
        text = skill_md.read_text()
        m = re.search(r'^name:\s*(\S+)', text, re.MULTILINE)
        if m:
            return m.group(1)
    raise ValueError("Could not find skill name in any skills/*/SKILL.md")


def mode_generate_transcripts(cwd: Path):
    state = load_state(cwd)
    scoring = state["scoring"]
    runs_per_eval = scoring["runs_per_eval"]
    evals_path = state.get("evals", {})

    trigger_eval_path = cwd / evals_path.get("trigger_path", "evals/trigger-eval.json")
    functional_eval_path = cwd / evals_path.get("functional_path", "evals/evals.json")

    trigger_evals = json.loads(trigger_eval_path.read_text()) if trigger_eval_path.exists() else []
    functional_evals = json.loads(functional_eval_path.read_text()) if functional_eval_path.exists() else []

    skill_name = read_skill_name(cwd)
    system_msg = (f"After completing your response, on a new line write exactly: "
                  f"SKILL_USED: {skill_name} or SKILL_USED: none")

    # TRIGGER BRANCH
    query_results = {i: [] for i in range(len(trigger_evals))}
    for run_n in range(1, runs_per_eval + 1):
        for i, entry in enumerate(trigger_evals):
            try:
                result = subprocess.run(
                    ["claude", "-p", entry["query"],
                     "--plugin-dir", str(cwd),
                     "--append-system-prompt", system_msg,
                     "--output-format", "json"],
                    capture_output=True, text=True, timeout=60
                )
            except subprocess.TimeoutExpired:
                result = type("r", (), {"stdout": "", "returncode": 1, "stderr": "timeout"})()
            try:
                text = json.loads(result.stdout).get("result", "")
            except (json.JSONDecodeError, AttributeError):
                text = result.stdout
            triggered = f"SKILL_USED: {skill_name}".lower() in text.lower()
            query_results[i].append(triggered)

    trigger_results_data = {
        "skill_name": skill_name,
        "runs_per_eval": runs_per_eval,
        "queries": [],
        "total_queries": len(trigger_evals)
    }
    for i, entry in enumerate(trigger_evals):
        results = query_results[i]
        pass_rate_q = sum(1 for r, e in zip(results, [entry["should_trigger"]] * len(results))
                          if r == e) / len(results) if results else 0.0
        trigger_results_data["queries"].append({
            "query": entry["query"],
            "should_trigger": entry["should_trigger"],
            "results": results,
            "pass_rate_q": round(pass_rate_q, 4)
        })

    evals_dir = cwd / "evals"
    evals_dir.mkdir(exist_ok=True)
    (evals_dir / "trigger-results.json").write_text(json.dumps(trigger_results_data, indent=2))

    # FUNCTIONAL BRANCH
    transcripts_dir = evals_dir / "transcripts"
    transcripts_dir.mkdir(exist_ok=True)
    transcripts_to_grade = []

    for run_n in range(1, runs_per_eval + 1):
        for eval_entry in functional_evals:
            eval_id = eval_entry["id"]
            prompt = eval_entry["prompt"]
            input_files = eval_entry.get("input_files", [])
            context_flags = []
            for f in input_files:
                context_flags += ["--add-dir", str(cwd / f)]

            try:
                result = subprocess.run(
                    ["claude", "-p", prompt, "--plugin-dir", str(cwd)] + context_flags,
                    capture_output=True, text=True, timeout=60
                )
            except subprocess.TimeoutExpired:
                result = type("r", (), {"stdout": "", "returncode": 1, "stderr": "timeout"})()
            transcript_path = transcripts_dir / f"{eval_id}-run-{run_n}.md"
            transcript_path.write_text(result.stdout)

            output_path = f"evals/transcripts/{eval_id}-run-{run_n}-grading.json"
            transcripts_to_grade.append({
                "eval_id": eval_id,
                "run_n": run_n,
                "expectations": eval_entry.get("expectations", []),
                "transcript_path": f"evals/transcripts/{eval_id}-run-{run_n}.md",
                "output_path": output_path
            })

    (evals_dir / "transcripts-to-grade.json").write_text(json.dumps(transcripts_to_grade, indent=2))
    print(f"Written: evals/trigger-results.json, evals/transcripts-to-grade.json")
    print(f"Transcripts: {len(transcripts_to_grade)} entries ({runs_per_eval} runs × {len(functional_evals)} evals)")


def mode_grade(cwd: Path):
    evals_dir = cwd / "evals"
    ttg_path = evals_dir / "transcripts-to-grade.json"
    if not ttg_path.exists():
        print("Error: evals/transcripts-to-grade.json not found. Run --generate-transcripts first.", file=sys.stderr)
        sys.exit(1)

    entries = json.loads(ttg_path.read_text())
    grader_script = Path(__file__).parent / "grader.py"

    skipped = 0
    failed = 0
    succeeded = 0

    for entry in entries:
        output_path = cwd / entry["output_path"]

        # Idempotent: skip if already graded
        if output_path.exists():
            try:
                existing = json.loads(output_path.read_text())
                if isinstance(existing.get("summary", {}).get("pass_rate"), (int, float)):
                    skipped += 1
                    continue
            except (json.JSONDecodeError, KeyError):
                pass  # re-grade if malformed

        transcript_path = cwd / entry["transcript_path"]

        # Missing transcript → fail all expectations
        if not transcript_path.exists():
            write_failed_grading(output_path, entry, "transcript missing")
            failed += 1
            continue

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Call grader.py
        expectations_json = json.dumps(entry.get("expectations", []))
        try:
            result = subprocess.run(
                [sys.executable, str(grader_script),
                 "--transcript", str(transcript_path),
                 "--expectations", expectations_json,
                 "--output", str(output_path),
                 "--eval-id", entry["eval_id"],
                 "--run-n", str(entry["run_n"])],
                capture_output=True, text=True, timeout=300
            )
        except subprocess.TimeoutExpired:
            write_failed_grading(output_path, entry, "grader timeout")
            failed += 1
            continue

        if result.returncode != 0:
            reason = f"grader error: {result.stderr[:200]}" if result.stderr else "grader error"
            write_failed_grading(output_path, entry, reason)
            failed += 1
        else:
            succeeded += 1

    total = len(entries)
    print(f"Graded: {total} entries ({succeeded} succeeded, {skipped} skipped, {failed} failed)")


def main():
    args = sys.argv[1:]
    cwd = Path.cwd()

    if "--generate-transcripts" in args:
        mode_generate_transcripts(cwd)
    elif "--grade" in args:
        mode_grade(cwd)
    elif "--score" in args:
        mode_score(cwd, baseline="--baseline" in args)
    else:
        print("Usage: run_evals.py --generate-transcripts | --grade | --score [--baseline]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
