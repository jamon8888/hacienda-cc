# Hacienda-Maker Cowork Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge cowork-plugin-management capabilities into hacienda-maker, providing a single plugin for create → optimize → customize lifecycle.

**Architecture:** This is a **Claude Code skill/command plugin**. The markdown files (commands/, references/, SKILL.md) ARE the implementation — they instruct Claude on what to do when users invoke commands. Claude reads these files at runtime and follows the instructions. The Python scripts in `scripts/` are for the quality evaluation loop only and remain unchanged. MCP tools (search_mcp_registry, suggest_connectors) are called by Claude at runtime — no code changes needed.

**Tech Stack:** Markdown skills/commands (the implementation), Python scripts (unchanged evaluation logic), MCP tools (runtime discovery).

**Important:** All "Create" and "Modify" tasks are creating/editing markdown instruction files. These ARE the feature implementation — Claude reads these at command invocation time.

---

## File Structure

| Action | File | Purpose |
|--------|------|---------|
| Copy | `hacienda-maker/skills/hacienda-maker/references/component-schemas.md` | Component format specs |
| Copy | `hacienda-maker/skills/hacienda-maker/references/example-plugins.md` | Example plugin structures |
| Copy | `hacienda-maker/skills/hacienda-maker/references/mcp-servers.md` | MCP discovery workflow |
| Copy | `hacienda-maker/skills/hacienda-maker/references/search-strategies.md` | Knowledge MCP query patterns |
| Create | `hacienda-maker/skills/hacienda-maker/references/customize-workflow.md` | Full customize workflow |
| Create | `hacienda-maker/commands/hacienda-maker/customize.md` | Customize command entrypoint |
| Modify | `hacienda-maker/commands/hacienda-maker/build.md` | Add guided workflow branch |
| Modify | `hacienda-maker/skills/hacienda-maker/references/build-workflow.md` | Add guided workflow steps |
| Modify | `hacienda-maker/skills/hacienda-maker/SKILL.md` | Add customize triggers |

---

## Task 1: Copy Reference Files

**Files:**
- Copy: `cowork-plugin-management/skills/create-cowork-plugin/references/component-schemas.md` → `hacienda-maker/skills/hacienda-maker/references/component-schemas.md`
- Copy: `cowork-plugin-management/skills/create-cowork-plugin/references/example-plugins.md` → `hacienda-maker/skills/hacienda-maker/references/example-plugins.md`
- Copy: `cowork-plugin-management/skills/cowork-plugin-customizer/references/mcp-servers.md` → `hacienda-maker/skills/hacienda-maker/references/mcp-servers.md`
- Copy: `cowork-plugin-management/skills/cowork-plugin-customizer/references/search-strategies.md` → `hacienda-maker/skills/hacienda-maker/references/search-strategies.md`

- [ ] **Step 1: Copy component-schemas.md**

```bash
cp cowork-plugin-management/skills/create-cowork-plugin/references/component-schemas.md \
   hacienda-maker/skills/hacienda-maker/references/
```

- [ ] **Step 2: Copy example-plugins.md**

```bash
cp cowork-plugin-management/skills/create-cowork-plugin/references/example-plugins.md \
   hacienda-maker/skills/hacienda-maker/references/
```

- [ ] **Step 3: Copy mcp-servers.md**

```bash
cp cowork-plugin-management/skills/cowork-plugin-customizer/references/mcp-servers.md \
   hacienda-maker/skills/hacienda-maker/references/
```

- [ ] **Step 4: Copy search-strategies.md**

```bash
cp cowork-plugin-management/skills/cowork-plugin-customizer/references/search-strategies.md \
   hacienda-maker/skills/hacienda-maker/references/
```

- [ ] **Step 5: Verify files copied**

Run: `ls -la hacienda-maker/skills/hacienda-maker/references/`
Expected: 4 new files present (component-schemas.md, example-plugins.md, mcp-servers.md, search-strategies.md)

- [ ] **Step 6: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/references/component-schemas.md \
        hacienda-maker/skills/hacienda-maker/references/example-plugins.md \
        hacienda-maker/skills/hacienda-maker/references/mcp-servers.md \
        hacienda-maker/skills/hacienda-maker/references/search-strategies.md
git commit -m "feat(hacienda-maker): add reference files from cowork-plugin-management

- component-schemas.md: plugin component format specs
- example-plugins.md: example plugin structures
- mcp-servers.md: MCP discovery and connection workflow
- search-strategies.md: knowledge MCP query patterns"
```

---

## Task 2: Create customize-workflow.md

**Files:**
- Create: `hacienda-maker/skills/hacienda-maker/references/customize-workflow.md`

- [ ] **Step 1: Create customize-workflow.md**

```markdown
# Customize Workflow

Tailor a plugin for a specific organization with MCP connector setup.

## Mode Detection

Check conditions in order:

1. **Scoped mode**: User provides `--focus=<section>` argument
2. **Generic setup mode**: `~~` placeholders detected in plugin files
3. **General mode**: No placeholders, no focus argument

## Placeholder Detection

Search for `~~`-prefixed placeholders using regex:

```
pattern: (?<!\\)~~[\w-]+
```

This matches `~~chat`, `~~project-tracker` but NOT escaped `\~~not-a-placeholder`.

Use grep or the Grep tool to find all occurrences:
```bash
grep -rn '(?<!\\)~~[\w-]+' <plugin-dir> --include='*.md' --include='*.json'
```

## Generic Setup Mode

**Trigger**: `~~` placeholders detected, no `--focus` argument

**Steps**:

1. Find all unique placeholders across plugin files
2. Group by category (e.g., `~~chat`, `~~project-tracker`)
3. For each placeholder, ask user via AskUserQuestion:
   - "What tool/service should replace `~~chat`?" (e.g., Slack, Microsoft Teams)
4. Apply replacements using Edit tool with `replace_all=true`
5. Update `CONNECTORS.md` if present
6. Proceed to MCP Connection phase

**Replacement tracking**: Keep a map of all replacements to show summary at end.

## Scoped Mode

**Trigger**: User provides `--focus=<section>` argument

**Keyword-to-file mapping**:

| Focus Keyword | Files to Modify |
|---------------|-----------------|
| `connectors`, `mcp`, `tools` | `.mcp.json`, `CONNECTORS.md` |
| `skill`, `skills` | `skills/*/SKILL.md` |
| `agents` | `agents/*.md` |
| `hooks` | `hooks/hooks.json` |
| `description`, `readme` | `README.md` |

**Steps**:

1. Identify files from keyword mapping
2. Read only those files
3. Ask targeted question: "What changes do you want for {section}?"
4. Apply changes to identified files only
5. Proceed to MCP Connection if connector-related

## General Mode

**Trigger**: No placeholders, no `--focus` argument

**Steps**:

1. Read all plugin files to understand current state
2. Ask: "What would you like to change about this plugin?"
3. Search knowledge MCPs for org context (if available)
4. Create todo list from response
5. Complete items using context or AskUserQuestion
6. Proceed to MCP Connection phase

## MCP Connection Phase

**Reference**: See `references/mcp-servers.md` for full details.

**Steps**:

1. Identify tool categories from customization changes
2. Search MCP registry with category keywords:
   - `search_mcp_registry(keywords=["slack", "chat", "messaging"])`
3. If results found: present to user, let them choose
4. If user chooses an MCP: call `suggest_connectors(directoryUuids=["uuid"])` if not already connected
5. Update `.mcp.json`:

```json
{
  "mcpServers": {
    "slack": {
      "type": "sse",
      "url": "https://slack-mcp.example.com"
    }
  }
}
```

**Config file location**:
1. Check `plugin.json` for `mcpServers` field → use that path
2. Otherwise use `.mcp.json` at plugin root

**Fallback** (if MCP registry unavailable):
- Print manual setup instructions
- Include example `.mcp.json` snippet
- Note required environment variables

## Packaging

**Output directory**: `./outputs/` (created if not exists)

**Steps**:

1. Validate plugin structure:
   ```bash
   python skills/hacienda-maker/scripts/validate_plugin.py <plugin-dir>
   ```
2. Create outputs directory:
   ```bash
   mkdir -p ./outputs
   ```
3. Create zip (run from plugin directory):
   ```bash
   cd <plugin-dir> && zip -r ../outputs/<plugin-name>.plugin . -x "*.DS_Store" -x "setup/*"
   ```
4. Present file to user

**Naming**: Use `name` field from `plugin.json` (e.g., `my-plugin` → `my-plugin.plugin`)

## Error Handling

| Condition | Behavior |
|-----------|----------|
| Plugin directory not found | Abort: "Plugin not found. Customize requires Cowork desktop app with plugins in mnt/.local-plugins or mnt/.plugins." |
| MCP registry unavailable | Print manual instructions, continue packaging |
| User skips all questions | Leave `~~` placeholders unchanged, print warning |
| Validation fails | Print errors, do not package |
```

- [ ] **Step 2: Verify file created**

Run: `test -f hacienda-maker/skills/hacienda-maker/references/customize-workflow.md && echo "PASS" || echo "FAIL"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/references/customize-workflow.md
git commit -m "feat(hacienda-maker): add customize-workflow.md reference"
```

---

## Task 3: Create customize.md Command

**Files:**
- Create: `hacienda-maker/commands/hacienda-maker/customize.md`

- [ ] **Step 1: Create customize.md**

```markdown
---
description: >
  Use when the user runs /hacienda-maker:customize. Tailors a plugin for a specific
  organization with placeholder replacement and MCP connector setup.
---

# /hacienda-maker:customize

Tailor a plugin for a specific organization with MCP connector setup.

**Usage**: `/hacienda-maker:customize [plugin-name] [--focus=<section>]`

- `plugin-name`: Optional. Name or path to plugin directory. If omitted, searches for plugin in `mnt/.local-plugins` and `mnt/.plugins`.
- `--focus`: Optional. Restricts customization to specific section (e.g., `--focus=connectors`).

Read `references/customize-workflow.md` for the full protocol.

Summary:
1. Locate plugin directory (Cowork mounts or provided path)
2. Detect mode: scoped (--focus), generic setup (~~ placeholders), or general
3. Apply customizations based on mode
4. Connect MCPs for identified tools
5. Validate and package as `.plugin` file
```

- [ ] **Step 2: Verify file created**

Run: `test -f hacienda-maker/commands/hacienda-maker/customize.md && echo "PASS" || echo "FAIL"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add hacienda-maker/commands/hacienda-maker/customize.md
git commit -m "feat(hacienda-maker): add /hacienda-maker:customize command"
```

---

## Task 4: Update build.md Command

**Files:**
- Modify: `hacienda-maker/commands/hacienda-maker/build.md`

- [ ] **Step 1: Update build.md**

Replace entire file content with:

```markdown
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
```

- [ ] **Step 2: Verify file updated**

Run: `grep -q "guided workflow" hacienda-maker/commands/hacienda-maker/build.md && echo "PASS" || echo "FAIL"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add hacienda-maker/commands/hacienda-maker/build.md
git commit -m "feat(hacienda-maker): add guided workflow branch to /build command"
```

---

## Task 5: Update build-workflow.md

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/references/build-workflow.md`

- [ ] **Step 1: Update build-workflow.md**

Replace entire file content with:

```markdown
# Build Workflow

## Purpose

Scaffold a plugin skeleton from collected evals or through guided discovery, then run baseline evaluation or package.

## Mode Detection

At the start of the workflow:

1. Check if `hacienda-maker.json` exists in working directory
2. If exists: validate and check for `use_cases` and `evals`
3. If missing: run guided workflow

## Evals-Based Workflow

**Trigger**: `hacienda-maker.json` exists with valid `use_cases` and `evals` fields

### Steps

1. Read `hacienda-maker.json` — verify `use_cases` and `evals` fields exist
2. Determine plugin name from `hacienda-maker.json` or ask user
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

## Guided Workflow

**Trigger**: `hacienda-maker.json` does not exist OR has no evals

### Steps

1. **Discovery** — understand what the user wants to build:
   - What should this plugin do?
   - Who will use it?
   - Does it integrate with external tools?

2. **Component Planning** — determine which components are needed:
   - Skills: domain knowledge, user-initiated actions
   - Agents: autonomous multi-step tasks (uncommon)
   - Hooks: event-driven automation (rare)
   - MCP Servers: external service integration

3. **Design** — clarify each component:
   - For skills: trigger phrases, knowledge domains, reference files
   - For MCP: server type, authentication, tools exposed
   - Use `references/component-schemas.md` for format specs

4. **Implementation** — create plugin files:
   - Create directory structure
   - Create `plugin.json` manifest
   - Create each component file
   - Create `README.md`

5. **Package** — deliver the finished plugin:
   - Validate: `python skills/hacienda-maker/scripts/validate_plugin.py <plugin-dir>`
   - Create outputs directory: `mkdir -p ./outputs`
   - Package: `cd <plugin-dir> && zip -r ../outputs/<name>.plugin . -x "*.DS_Store"`
   - Present `.plugin` file to user

## Error Handling

| Condition | Behavior | User Message |
|-----------|----------|--------------|
| `hacienda-maker.json` malformed (invalid JSON) | Abort | "hacienda-maker.json is malformed. Run /hacienda-maker:collect to regenerate." |
| `use_cases` empty array or missing | Abort | "No use cases defined. Run /hacienda-maker:collect first." |
| `evals` empty array | Auto-generate from use cases | (proceed silently) |
| User skips all discovery questions | Create minimal plugin | "Creating minimal plugin with default skill." |
| Validation fails after scaffolding | Print errors, stop | (show validation errors) |

## SKILL.md Description Synthesis

Generate description from use cases:
- Lead with: "Use this skill when the user wants to..."
- Include 3–5 exact phrasings from use case descriptions
- Keep under 500 characters
- No angle brackets
```

- [ ] **Step 2: Verify file updated**

Run: `grep -q "Guided Workflow" hacienda-maker/skills/hacienda-maker/references/build-workflow.md && echo "PASS" || echo "FAIL"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/references/build-workflow.md
git commit -m "feat(hacienda-maker): add guided workflow to build-workflow.md"
```

---

## Task 6: Update SKILL.md

**Files:**
- Modify: `hacienda-maker/skills/hacienda-maker/SKILL.md`

- [ ] **Step 1: Update SKILL.md frontmatter**

Replace lines 1-10 with:

```markdown
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
```

- [ ] **Step 2: Verify file updated**

Run: `grep -q "hacienda-maker:customize" hacienda-maker/skills/hacienda-maker/SKILL.md && echo "PASS" || echo "FAIL"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add hacienda-maker/skills/hacienda-maker/SKILL.md
git commit -m "feat(hacienda-maker): add customize triggers and command to SKILL.md"
```

---

## Task 7: Verify Tests Pass

**Files:**
- Test: `hacienda-maker/tests/`

- [ ] **Step 1: Run existing test suite**

```bash
cd hacienda-maker && pytest tests/ -v
```

Expected: All tests pass (exit code 0)

- [ ] **Step 2: Verify new files present**

```bash
ls hacienda-maker/skills/hacienda-maker/references/ | grep -E "component-schemas|example-plugins|mcp-servers|search-strategies|customize-workflow"
```

Expected: 5 files listed

- [ ] **Step 3: Verify new command present**

```bash
test -f hacienda-maker/commands/hacienda-maker/customize.md && echo "PASS" || echo "FAIL"
```

Expected: PASS

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git status
# If clean, no commit needed
# If changes, commit with: git commit -m "fix(hacienda-maker): test fixes"
```

---

## Success Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | 4 reference files copied | Task 1, Step 5 |
| 2 | customize-workflow.md created | Task 2, Step 2 |
| 3 | customize.md command created | Task 3, Step 2 |
| 4 | build.md updated with guided workflow | Task 4, Step 2 |
| 5 | build-workflow.md updated | Task 5, Step 2 |
| 6 | SKILL.md updated with customize triggers | Task 6, Step 2 |
| 7 | Existing tests pass | Task 7, Step 1 |

## Verification Notes

**Automated verification limitations:**
- The `/customize` workflow uses `AskUserQuestion` for interactive user input
- Placeholder replacement and MCP connection behaviors require user interaction
- These cannot be fully automated in test scripts
- Manual testing required: run `/hacienda-maker:customize` in Cowork desktop app with a plugin containing `~~` placeholders

**Manual verification for `/customize`:**
1. Create a test plugin with `~~chat` and `~~project-tracker` placeholders
2. Run `/hacienda-maker:customize test-plugin`
3. Answer questions with "Slack" and "Linear"
4. Verify: no `~~` tokens remain, replacement values present
5. Verify: `.mcp.json` created with `mcpServers` object

**Platform compatibility:**
- Shell commands use Git Bash syntax (works on Windows with Git for Windows)
- Alternative: use Claude tools (Grep, Glob, Read) instead of shell commands if preferred
