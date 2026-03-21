---
name: hacienda-maker
description: >
  Use this skill when the user wants to build, evaluate, improve, or customize a Claude Cowork plugin.
  Trigger phrases: "build a plugin", "evaluate my plugin", "improve plugin quality",
  "optimize plugin", "convert plugin to cowork", "run plugin evals", "start hacienda-maker",
  "plugin eval loop", "plugin score", "plugin benchmark", "customize plugin",
  "set up plugin connectors", "configure plugin MCP", "tailor plugin",
  "adjust plugin settings". Use when the user invokes /hacienda-maker, /hacienda-maker:collect,
  /hacienda-maker:build, /hacienda-maker:optimize, /hacienda-maker:convert, or /hacienda-maker:customize.
---

# hacienda-maker

Routes user commands to the appropriate workflow. Read the command reference in commands/ for each subcommand.

## Commands

- `/hacienda-maker` — full pipeline (collect → build → optimize) or resume
- `/hacienda-maker:collect` — capture use cases and generate evals
- `/hacienda-maker:build` — scaffold plugin skeleton from evals or guided workflow
- `/hacienda-maker:optimize` — run autonomous improvement loop
- `/hacienda-maker:convert` — convert Claude Code plugin to Cowork format
- `/hacienda-maker:customize` — org-specific setup with MCP connector configuration
