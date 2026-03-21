---
description: >
  Use when the user runs /hacienda-maker:build. Scaffolds plugin skeleton from evals
  or guided workflow, runs baseline evaluation, initializes TSV log.
---

# /hacienda-maker:build

Scaffold a plugin from existing evals or through guided discovery.

Read `references/build-workflow.md` for the full protocol.

## Behavior

**If `hacienda-maker.json` exists with `use_cases` and `evals`:**
1. Scaffold plugin skeleton from evals
2. Run validation
3. Run baseline evaluation
4. Initialize TSV log

**If `hacienda-maker.json` missing or has no evals:**
1. Run guided discovery workflow (see `references/component-schemas.md`)
2. Create plugin files
3. Package as `.plugin` file in `./outputs/`

Summary:
1. Check for `hacienda-maker.json` in working directory
2. If exists with evals: scaffold from evals, run baseline
3. If missing or no evals: run guided workflow, package
4. Handle malformed config with helpful error messages
