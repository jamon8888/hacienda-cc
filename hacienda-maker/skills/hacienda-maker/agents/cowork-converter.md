---
name: cowork-converter
description: Converts a Claude Code plugin to Cowork-compatible format using an 8-item checklist.
tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# cowork-converter

Apply all 8 conversion items to the plugin at `plugin_path`. Work through each item systematically.

## Input

```
plugin_path: ./
checklist: [items 1-8]
report_path: evals/convert-report.md
```

## Checklist

| # | Detect | Adapt | Rule |
|---|--------|-------|------|
| 1 | `claude -p` in script with captured output fed to another process | Rewrite as inline Python: `from anthropic import Anthropic; result = Anthropic().messages.create(model="claude-opus-4-6", max_tokens=1024, messages=[{"role":"user","content":prompt}]).content[0].text` | Use inline if output is parsed; static JSON if only displayed |
| 2 | `claude -p` with HTML/browser display | Add `--static` flag | Always |
| 3 | `input()`, `sys.stdin.read()`, interactive prompts | Replace with `AskUserQuestion` tool call | Always |
| 4 | Absolute paths | Replace with `${CLAUDE_PLUGIN_ROOT}` prefix | Always |
| 5 | `type: command` hooks with CLI binaries | Change to `type: prompt` hooks | Always |
| 6 | `commands/*.md` slash commands | Create equivalent `skills/*/SKILL.md` | Always |
| 7 | `tools: Read, Grep` (comma string) in agent frontmatter | Rewrite as `tools:\n  - Read\n  - Grep` (YAML list) | Always |
| 8 | MCP servers with browser-only transport | Flag as incompatible — cannot auto-fix | Manual only |

## Output

Modify plugin files in-place. Write report to `report_path`:
```markdown
# Conversion Report

| Item | Status | Detail |
|------|--------|--------|
| 1    | resolved / unresolved / skipped | ... |
...
```

Collect unresolved items — these appear in the failure report if score drops more than 5 points.
