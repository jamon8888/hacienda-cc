---
name: hacienda-maker
description: >
  Use this skill when the user wants to build, evaluate, or improve a Claude Cowork plugin.
  Trigger phrases: "build a plugin", "evaluate my plugin", "improve plugin quality",
  "optimize plugin", "convert plugin to cowork", "run plugin evals", "start hacienda-maker",
  "plugin eval loop", "plugin score", "plugin benchmark". Use when the user invokes
  /hacienda-maker, /hacienda-maker:collect, /hacienda-maker:build, /hacienda-maker:optimize,
  or /hacienda-maker:convert.
---

# hacienda-maker

Routes user commands to the appropriate workflow. Read the command reference in commands/ for each subcommand.

## Commands

- `/hacienda-maker` — full pipeline (collect → build → optimize) or resume
- `/hacienda-maker:collect` — capture use cases and generate evals
- `/hacienda-maker:build` — scaffold plugin skeleton from evals
- `/hacienda-maker:optimize` — run autonomous improvement loop
- `/hacienda-maker:convert` — convert Claude Code plugin to Cowork format
