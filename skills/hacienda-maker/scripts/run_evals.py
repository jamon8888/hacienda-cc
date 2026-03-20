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
            result = subprocess.run(
                ["claude", "-p", entry["query"],
                 "--plugin", str(cwd),
                 "--system", system_msg],
                capture_output=True, text=True
            )
            transcript = result.stdout
            lines = transcript.strip().splitlines()
            last_lines = lines[-3:] if len(lines) >= 3 else lines
            triggered = any(f"SKILL_USED: {skill_name}".lower() in l.lower() for l in last_lines)
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
                context_flags += ["--context", str(cwd / f)]

            result = subprocess.run(
                ["claude", "-p", prompt, "--plugin", str(cwd)] + context_flags,
                capture_output=True, text=True
            )
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
