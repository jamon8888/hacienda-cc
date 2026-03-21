# Collect Workflow

## Purpose

Capture use cases from the user and generate eval files via the eval-generator agent.

## Dialogue Protocol

1. Ask: "What should this plugin do? Describe the first use case — what the user says and what the plugin should produce."
2. Record: `{ "id": "uc-001", "description": "<user input>", "expected_behavior": "<user input>" }`
3. Ask: "Any other use cases? (say 'done' when finished)"
4. Repeat until user says "done" or "that's all"
5. Dispatch `eval-generator` agent with:
   ```
   use_cases: [all collected use cases]
   trigger_output_path: evals/trigger-eval.json
   functional_output_path: evals/evals.json
   ```
6. Write `hm.json` (create if missing):
   - Set `use_cases` field to collected list
   - Set `evals.trigger_path` to `evals/trigger-eval.json`
   - Set `evals.functional_path` to `evals/evals.json`
   - Initialize `scoring`, `loop`, `history`, `convert` with defaults from state-schema.md
