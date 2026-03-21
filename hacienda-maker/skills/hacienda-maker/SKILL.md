---
name: hm
description: >
  Use this skill when the user wants to build, evaluate, improve, or customize a Claude Cowork plugin.
  Trigger phrases: "build a plugin", "evaluate my plugin", "improve plugin quality",
  "optimize plugin", "convert plugin to cowork", "run plugin evals", "start hm",
  "plugin eval loop", "plugin score", "plugin benchmark", "customize plugin",
  "set up plugin connectors", "configure plugin MCP", "tailor plugin",
  "adjust plugin settings". Use when the user invokes /hm, /hm:collect,
  /hm:build, /hm:optimize, /hm:convert, or /hm:customize.
---

# hm

Routes user commands to the appropriate workflow. Read the command reference in commands/ for each subcommand.

## Commands

- `/hm` — full pipeline (collect → build → optimize) or resume
- `/hm:collect` — capture use cases and generate evals
- `/hm:build` — scaffold plugin skeleton from evals or guided workflow
- `/hm:optimize` — run autonomous improvement loop
- `/hm:convert` — convert Claude Code plugin to Cowork format
- `/hm:customize` — org-specific setup with MCP connector configuration
