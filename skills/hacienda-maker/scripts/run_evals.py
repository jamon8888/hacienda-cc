#!/usr/bin/env python3
"""run_evals.py — eval orchestrator.
Modes:
  --generate-transcripts  : run claude -p for trigger + eval prompts, write output files
  --score [--baseline]    : read grading.json files, compute scores, write last-run.json
"""
import json
import subprocess
import sys
from pathlib import Path
from statistics import median
from collections import defaultdict


def load_state(cwd: Path) -> dict:
    return json.loads((cwd / "hacienda-maker.json").read_text())

def write_state(cwd: Path, state: dict):
    (cwd / "hacienda-maker.json").write_text(json.dumps(state, indent=2))


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
                rates.append(grading["summary"]["pass_rate"])
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
    write_state(cwd, state)

    print(json.dumps(last_run, indent=2))


def mode_generate_transcripts(cwd: Path):
    # Implemented in Task 6
    print("--generate-transcripts not yet implemented", file=sys.stderr)
    sys.exit(1)


def main():
    args = sys.argv[1:]
    cwd = Path.cwd()

    if "--generate-transcripts" in args:
        mode_generate_transcripts(cwd)
    elif "--score" in args:
        mode_score(cwd, baseline="--baseline" in args)
    else:
        print("Usage: run_evals.py --generate-transcripts | --score [--baseline]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
