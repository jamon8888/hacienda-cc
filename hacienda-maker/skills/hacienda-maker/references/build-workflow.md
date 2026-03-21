# Build Workflow

## Purpose

Scaffold a minimal plugin skeleton from collected evals, then run baseline evaluation.

## Steps

1. Read `hacienda-maker.json` — verify `use_cases` and `evals` fields exist. If missing, abort: "Run /hacienda-maker:collect first."
2. Determine plugin name from `hacienda-maker.json` or ask user.
3. Create minimal skeleton:
   - `.claude-plugin/plugin.json` with `{"name": "<plugin-name>", "version": "0.1.0"}`
   - `skills/<plugin-name>/SKILL.md` with frontmatter synthesized from use cases
4. Run structural gate: `python skills/hacienda-maker/scripts/validate_plugin.py .`
   - If fails: print Rule N error and stop. User must fix before continuing.
5. Run baseline:
   ```bash
   python skills/hacienda-maker/scripts/run_evals.py --generate-transcripts
   python skills/hacienda-maker/scripts/run_evals.py --grade
   python skills/hacienda-maker/scripts/run_evals.py --score --baseline
   ```
6. Initialize TSV log: write header row to `hacienda-maker-results.tsv`:
   ```
   iteration\tcombined_score\ttrigger_score\tfunctional_score\tdelta\tis_improvement\tcommit_sha\ttimestamp
   ```
   Then append baseline row (iteration=0).

## SKILL.md Description Synthesis

Generate description from use cases:
- Lead with: "Use this skill when the user wants to..."
- Include 3–5 exact phrasings from use case descriptions
- Keep under 500 characters
- No angle brackets
