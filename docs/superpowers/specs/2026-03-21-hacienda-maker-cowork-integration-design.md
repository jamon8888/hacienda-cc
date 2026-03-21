# Design: Integrate cowork-plugin-management into hacienda-maker

**Date**: 2026-03-21
**Status**: Draft

## Context

### Current State

**hacienda-maker** (`C:\Users\NMarchitecte\Documents\cc-cowork\hacienda-maker\`):
- Autonomous plugin quality loop that evaluates trigger precision and functional correctness
- Iteratively improves plugins until a score threshold is met
- Current entrypoints:
  - `commands/hacienda-maker.md` — dispatcher command
  - `commands/hacienda-maker/collect.md` — capture use cases, generate evals
  - `commands/hacienda-maker/build.md` — scaffold plugin from evals
  - `commands/hacienda-maker/optimize.md` — run autonomous improvement loop
  - `commands/hacienda-maker/convert.md` — convert Claude Code plugin to Cowork
- Core skill: `skills/hacienda-maker/SKILL.md`
- Scripts: `skills/hacienda-maker/scripts/` (validate_plugin.py, run_evals.py, grader.py, score.py)
- Agents: `skills/hacienda-maker/agents/` (analyzer.md, grader.md, eval-generator.md, cowork-converter.md)
- Configuration: `hacienda-maker.json` in working directory (created by `/collect`)

**cowork-plugin-management** (`C:\Users\NMarchitecte\Documents\cc-cowork\cowork-plugin-management\`):
- `skills/create-cowork-plugin/SKILL.md` — guided plugin creation (discovery → design → package)
- `skills/cowork-plugin-customizer/SKILL.md` — org-specific customization with MCP setup
- References: `component-schemas.md`, `example-plugins.md`, `mcp-servers.md`, `search-strategies.md`

### Problem

Users need two separate plugins to cover the full plugin lifecycle:
1. **Creation** — `create-cowork-plugin` scaffolds new plugins
2. **Optimization** — `hacienda-maker optimize` improves quality
3. **Customization** — `cowork-plugin-customizer` tailors for org/MCP setup

This creates friction and installation overhead.

### Solution

Merge cowork-plugin-management capabilities into hacienda-maker, providing a single plugin for the complete lifecycle: **create → optimize → customize**.

## Goal

Deliver a unified `hacienda-maker` plugin that handles:
1. **Creation** — guided scaffolding OR evals-based scaffolding
2. **Optimization** — autonomous quality improvement loop (unchanged)
3. **Customization** — org-specific setup with MCP connectors

### Acceptance Criteria

| # | Capability | Acceptance | Verification |
|---|------------|------------|--------------|
| 1 | `/build` with evals | Creates skeleton from `hacienda-maker.json`, runs baseline, initializes TSV log | Test 1: assert plugin.json, SKILL.md, TSV exist |
| 2 | `/build` without evals | Runs guided discovery workflow, outputs `.plugin` file | Test 2: assert `.plugin` file created |
| 3 | `/build` malformed config | Aborts with helpful error message | Test 3: assert error output contains "malformed" or "run /collect" |
| 4 | `/customize` generic setup | Detects `~~` placeholders, replaces ALL with user values | Test 4: assert no `~~` tokens remain, assert replacement values present |
| 5 | `/customize` scoped | Focuses only on requested section | Test 5: assert output mentions only requested topic |
| 6 | `/customize` general | Searches knowledge MCPs, asks questions, updates plugin | Test 6: assert MCP search called |
| 7 | MCP connection | Updates `.mcp.json` with valid schema | Test 4/5: assert `.mcp.json` has `mcpServers` object |
| 8 | Packaging | Creates `.plugin` file in `./outputs/` directory | Tests 2, 4: assert `.plugin` file exists |
| 9 | Existing tests | All pass without modification | Test 7: `pytest tests/` returns exit code 0 |

## Architecture

### Command Dispatch Model

The plugin uses **slash commands** as entrypoints, not skill triggers:

| Command | File | Triggered by |
|---------|------|--------------|
| `/hacienda-maker` | `commands/hacienda-maker.md` | User types `/hacienda-maker` |
| `/hacienda-maker:build` | `commands/hacienda-maker/build.md` | User types `/hacienda-maker:build` |
| `/hacienda-maker:customize` | `commands/hacienda-maker/customize.md` | User types `/hacienda-maker:customize` |

**SKILL.md frontmatter triggers** are for the *skill* to be invoked conversationally (e.g., "customize my plugin"). The commands are explicit slash command entrypoints that bypass skill triggers.

### Command Structure

```
/hacienda-maker              # Full pipeline or resume
/hacienda-maker:collect      # Capture use cases, generate evals (unchanged)
/hacienda-maker:build        # Scaffold plugin (ENHANCED)
/hacienda-maker:optimize    # Quality improvement loop (unchanged)
/hacienda-maker:convert      # Claude Code → Cowork (unchanged)
/hacienda-maker:customize    # Org-specific setup + MCP (NEW)
```

### File Changes

**Repository-relative paths with explicit NEW/UPDATE markers:**

```
C:\Users\NMarchitecte\Documents\cc-cowork\hacienda-maker\
│
├── .claude-plugin/
│   └── plugin.json                        # NO CHANGES
│
├── commands/
│   ├── hacienda-maker.md                  # NO CHANGES
│   └── hacienda-maker/
│       ├── collect.md                     # NO CHANGES
│       ├── build.md                       # UPDATE: add guided path branching
│       ├── optimize.md                   # NO CHANGES
│       ├── convert.md                     # NO CHANGES
│       └── customize.md                   # NEW: customize command
│
├── skills/
│   └── hacienda-maker/
│       ├── SKILL.md                       # UPDATE: add customize triggers
│       ├── agents/                        # NO CHANGES
│       ├── scripts/                       # NO CHANGES
│       └── references/
│           ├── build-workflow.md          # UPDATE: add guided workflow branch
│           ├── customize-workflow.md      # NEW: full customize workflow
│           ├── component-schemas.md       # NEW: from cowork-plugin-management
│           ├── example-plugins.md         # NEW: from cowork-plugin-management
│           ├── mcp-servers.md             # NEW: from cowork-plugin-management
│           └── search-strategies.md       # NEW: from cowork-plugin-management
│
└── tests/                                 # NO CHANGES
```

**Configuration location**: `hacienda-maker.json` is created by `/collect` in the working directory where the user runs the command.

**Output directory**: `.plugin` files are written to `./outputs/` relative to the working directory (created if not exists).

## Component Details

### 1. Enhanced `/build` Command

**File**: `commands/hacienda-maker/build.md`

**Current behavior**:
1. Read `hacienda-maker.json` — verify `use_cases` and `evals` exist
2. Create minimal skeleton
3. Run `validate_plugin.py`
4. Run baseline evaluation
5. Initialize TSV log

**Enhanced behavior** — add branching at step 1:

```python
# Pseudocode for decision logic
if file_exists("hacienda-maker.json"):
    data = read_json("hacienda-maker.json")
    if not valid_json(data):
        abort("hacienda-maker.json is malformed. Run /hacienda-maker:collect to regenerate.")
    if data.get("use_cases") and data.get("evals"):
        # Current path: scaffold from evals
        scaffold_from_evals(data)
    elif data.get("use_cases") and not data.get("evals"):
        # Run eval generation first
        run_eval_generator(data["use_cases"])
        scaffold_from_evals(data)
    else:
        # Missing use_cases
        abort("hacienda-maker.json missing use_cases. Run /hacienda-maker:collect first.")
else:
    # NEW: guided workflow
    run_guided_workflow()
```

**Guided workflow steps** (from `create-cowork-plugin`):
1. **Discovery** — ask about purpose, users, integrations
2. **Component Planning** — determine skills/agents/hooks/MCP needed
3. **Design** — clarify each component with targeted questions
4. **Implementation** — create plugin files per `component-schemas.md`
5. **Package** — run validation, create `.plugin` file in `./outputs/`

**Error handling**:

| Condition | Behavior | User Message |
|-----------|----------|--------------|
| `hacienda-maker.json` malformed (invalid JSON) | Abort | "hacienda-maker.json is malformed. Run /hacienda-maker:collect to regenerate." |
| `use_cases` empty array or missing | Abort | "No use cases defined. Run /hacienda-maker:collect first." |
| `evals` empty array | Auto-generate from use cases | (proceed silently) |
| User skips all discovery questions | Create minimal plugin with placeholder skill | "Creating minimal plugin with default skill." |
| Validation fails after scaffolding | Print errors, do not proceed | (show validation errors) |

### 2. New `/customize` Command

**File**: `commands/hacienda-maker/customize.md`

**Purpose**: Tailor a plugin for a specific organization with MCP connector setup.

**Command arguments**:
```
/hacienda-maker:customize [plugin-name] [--focus=<section>]
```
- `plugin-name`: Optional. Name or path to plugin directory. If omitted, searches for single plugin in `mnt/.local-plugins` and `mnt/.plugins`.
- `--focus`: Optional. Restricts customization to specific section (e.g., `--focus=connectors`).

**Entrypoint logic**:

```python
# Pseudocode
# Step 1: Locate plugin
if plugin_name_arg:
    plugin_dir = resolve_plugin_path(plugin_name_arg)
else:
    plugin_dir = find_plugin_in_cowork_dirs()

if not plugin_dir:
    abort("Plugin not found. Customize requires Cowork desktop app with plugins in mnt/.local-plugins or mnt/.plugins.")

# Step 2: Detect mode
if focus_arg:
    mode = "scoped"
    focus_section = focus_arg
else:
    placeholders = grep_for_placeholders(plugin_dir)
    if placeholders:
        mode = "generic_setup"
    else:
        mode = "general"
```

**Placeholder detection regex** (Python):
```python
import re
# Match ~~word but not \~~word (escaped)
pattern = r'(?<!\\)~~[\w-]+'
placeholders = set(re.findall(pattern, file_content))
```

**Platform note**: On Windows, use Python's `re` module instead of `sed`. All file modifications use the `Edit` tool or `Write` tool, not shell commands.

### Mode Workflows

#### Generic Setup Mode

**Trigger**: `~~` placeholders detected, no `--focus` argument

**Steps**:
1. Find all placeholders across plugin files using regex
2. Group by category (e.g., `~~chat`, `~~project-tracker`)
3. Build replacement map:
   ```
   {
     "~~chat": {"category": "chat", "value": null},
     "~~project-tracker": {"category": "project-management", "value": null}
   }
   ```
4. For each placeholder, ask user via `AskUserQuestion`
5. Apply replacements using `Edit` tool with `replace_all=true`
6. Update `CONNECTORS.md` if present
7. Proceed to MCP connection (Phase 4)

**Replacement data structure**:
```python
replacements = {
    "~~chat": "Slack",
    "~~project-tracker": "Linear",
    "~~status-channel": "#eng-updates"
}
```

#### Scoped Mode

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
5. Proceed to MCP connection if connector-related

#### General Mode

**Trigger**: No placeholders, no `--focus` argument

**Steps**:
1. Read all plugin files to understand current state
2. Ask: "What would you like to change about this plugin?"
3. Search knowledge MCPs for org context (if available)
4. Create todo list from response
5. Complete items using context or `AskUserQuestion`
6. Proceed to MCP connection (Phase 4)

### MCP Connection Workflow

**Reference**: `references/mcp-servers.md`

**Available tools**:
- `search_mcp_registry(keywords=["slack", "chat"])` → returns MCP entries with `name`, `url`, `directoryUuid`, `connected`
- `suggest_connectors(directoryUuids=["uuid1"])` → renders Connect buttons

**Steps**:

1. **Identify tool categories** from customization changes
2. **Search MCP registry** with category keywords:
   ```python
   results = search_mcp_registry(keywords=["slack", "chat", "messaging"])
   ```
3. **If results found**: Present to user, let them choose
4. **If user chooses an MCP**: Call `suggest_connectors` if not already connected
5. **Update `.mcp.json`**:
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

### Packaging

**Output directory**: `./outputs/` (relative to working directory, created if not exists)

**Naming**: `{plugin-name}.plugin` where `plugin-name` comes from `plugin.json` `name` field

**Steps**:
1. Validate plugin: `python scripts/validate_plugin.py <plugin-dir>`
2. Create outputs directory: `mkdir -p ./outputs`
3. Create zip:
   ```bash
   cd <plugin-dir> && zip -r ./outputs/<plugin-name>.plugin . -x "*.DS_Store" -x "setup/*"
   ```
4. Present file to user

**Error handling**:
- If validation fails: print errors, do not package
- If zip fails: print error, suggest manual packaging

### 3. Updated SKILL.md

**File**: `skills/hacienda-maker/SKILL.md`

**Changes**:

1. Add to frontmatter description:
```yaml
description: >
  Use this skill when the user wants to build, evaluate, improve, or customize a Claude Cowork plugin.
  Trigger phrases: "build a plugin", "evaluate my plugin", "improve plugin quality",
  "optimize plugin", "convert plugin to cowork", "run plugin evals", "start hacienda-maker",
  "plugin eval loop", "plugin score", "plugin benchmark", "customize plugin",
  "set up plugin connectors", "configure plugin MCP", "tailor plugin",
  "adjust plugin settings".
```

2. Add to Commands section:
```markdown
- `/hacienda-maker:customize` — org-specific setup with MCP connector configuration
```

### 4. Reference Files to Create

**New files to create** (with exact paths):

| File | Source | Content |
|------|--------|---------|
| `hacienda-maker/skills/hacienda-maker/references/component-schemas.md` | Copy from `cowork-plugin-management/skills/create-cowork-plugin/references/component-schemas.md` | Unchanged |
| `hacienda-maker/skills/hacienda-maker/references/example-plugins.md` | Copy from `cowork-plugin-management/skills/create-cowork-plugin/references/example-plugins.md` | Unchanged |
| `hacienda-maker/skills/hacienda-maker/references/mcp-servers.md` | Copy from `cowork-plugin-management/skills/cowork-plugin-customizer/references/mcp-servers.md` | Unchanged |
| `hacienda-maker/skills/hacienda-maker/references/search-strategies.md` | Copy from `cowork-plugin-management/skills/cowork-plugin-customizer/references/search-strategies.md` | Unchanged |
| `hacienda-maker/skills/hacienda-maker/references/customize-workflow.md` | NEW | Full customize workflow (see below) |

**customize-workflow.md content outline**:
```markdown
# Customize Workflow

## Mode Detection
- Generic setup: ~~ placeholders exist
- Scoped: --focus argument provided
- General: no placeholders, no focus

## Placeholder Replacement
- Regex: `(?<!\\)~~[\w-]+`
- Use Edit tool with replace_all=true
- Track all replacements for summary

## MCP Connection
- Search registry with category keywords
- Update .mcp.json per mcp-servers.md schema

## Packaging
- Validate then zip to ./outputs/
```

### 5. Unchanged Components

- `/collect` — capture use cases, generate evals
- `/optimize` — autonomous quality improvement loop
- `/convert` — Claude Code → Cowork format conversion
- All scripts in `skills/hacienda-maker/scripts/`
- All agents in `skills/hacienda-maker/agents/`
- All tests in `tests/`
- `plugin.json` manifest

## Data Flow

```
User runs /hacienda-maker
         │
         ├──────────────────────────────────────┐
         │                                      │
         ▼                                      ▼
    /collect (unchanged)              /build (enhanced)
         │                                      │
         ▼                                      ▼
    creates:                          ┌────────────────────┐
    hacienda-maker.json               │ hacienda-maker.json │
    evals/*.json                      │     exists?        │
         │                            └─────────┬──────────┘
         │                            ┌─────────┴─────────┐
         │                            ▼                   ▼
         │                          Yes                  No
         │                            │                   │
         │                            ▼                   ▼
         │                     ┌──────────────┐    Guided workflow
         │                     │ use_cases +  │    (discovery →
         │                     │ evals exist? │     design → package)
         │                     └──────┬───────┘
         │                     ┌──────┴──────┐
         │                     ▼             ▼
         │                   Yes           No
         │                     │             │
         │                     │             ▼
         │                     │      Generate evals
         │                     │      from use_cases
         │                     │             │
         └─────────────────────┴─────────────┘
                                    │
                                    ▼
                            Scaffold plugin
                                    │
                                    ▼
                          validate_plugin.py
                                    │
                                    ▼
                          Baseline evaluation
                                    │
                                    ▼
                      Initialize TSV log
                                    │
                                    ▼
                            /optimize (unchanged)
                                    │
                                    ▼
                          Quality loop runs
                                    │
                                    ▼
                            /customize (NEW)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              Generic          Scoped         General
              setup          (--focus=ARG)   customize
           (~~ placeholders      │               │
              detected)          │               │
                    │               │         Search MCPs
                    │               │               │
                    └───────────────┴───────────────┘
                                    │
                                    ▼
                            Replace values /
                            Update content
                                    │
                                    ▼
                            Connect MCPs
                            (update .mcp.json)
                                    │
                                    ▼
                            Validate + Package
                                    │
                                    ▼
                        ./outputs/{name}.plugin
```

## Implementation Steps

### Step 1: Copy Reference Files

```bash
# From cc-cowork root
cp cowork-plugin-management/skills/create-cowork-plugin/references/component-schemas.md \
   hacienda-maker/skills/hacienda-maker/references/

cp cowork-plugin-management/skills/create-cowork-plugin/references/example-plugins.md \
   hacienda-maker/skills/hacienda-maker/references/

cp cowork-plugin-management/skills/cowork-plugin-customizer/references/mcp-servers.md \
   hacienda-maker/skills/hacienda-maker/references/

cp cowork-plugin-management/skills/cowork-plugin-customizer/references/search-strategies.md \
   hacienda-maker/skills/hacienda-maker/references/
```

### Step 2: Create customize-workflow.md

Create `hacienda-maker/skills/hacienda-maker/references/customize-workflow.md` with:
- Mode detection logic
- Placeholder regex and replacement workflow
- Keyword-to-file mapping for scoped mode
- MCP connection steps
- Packaging steps

### Step 3: Create customize.md Command

Create `hacienda-maker/commands/hacienda-maker/customize.md`:
- YAML frontmatter with description
- Command signature: `/hacienda-maker:customize [plugin-name] [--focus=<section>]`
- Summary: "Read `references/customize-workflow.md` for the full protocol."

### Step 4: Update build.md Command

Update `hacienda-maker/commands/hacienda-maker/build.md`:
- Add branching logic for guided vs evals-based
- Add error handling for malformed config
- Reference `references/component-schemas.md` for guided workflow

### Step 5: Update build-workflow.md

Update `hacienda-maker/skills/hacienda-maker/references/build-workflow.md`:
- Add guided workflow branch
- Add eval generation step when evals missing
- Add error handling table

### Step 6: Update SKILL.md

Update `hacienda-maker/skills/hacienda-maker/SKILL.md`:
- Add customize trigger phrases to frontmatter
- Add `/hacienda-maker:customize` to Commands section

### Step 7: Test

Run all tests (see Verification section).

## Verification

### Test 1: `/build` with valid evals

```bash
cd C:\Users\NMarchitecte\Documents\cc-cowork\hacienda-maker

# Setup
cat > hacienda-maker.json << 'EOF'
{
  "plugin_name": "test-plugin",
  "use_cases": [{"description": "format code", "category": "formatting"}],
  "evals": [{"id": "e1", "prompt": "format this", "expected_trigger": true}]
}
EOF

# Run
claude -p "/hacienda-maker:build" --cwd .

# Assertions
test -f .claude-plugin/plugin.json && echo "PASS: plugin.json" || echo "FAIL: plugin.json"
test -f skills/test-plugin/SKILL.md && echo "PASS: SKILL.md" || echo "FAIL: SKILL.md"
test -f hacienda-maker-results.tsv && echo "PASS: TSV" || echo "FAIL: TSV"
head -1 hacienda-maker-results.tsv | grep -q "iteration" && echo "PASS: TSV header" || echo "FAIL: TSV header"
```

### Test 2: `/build` without evals → guided workflow

```bash
cd C:\Users\NMarchitecte\Documents\cc-cowork\hacienda-maker
rm -f hacienda-maker.json

# Run guided workflow
claude -p "build a plugin that formats Python code" --cwd . --max-tokens 10000

# Assertions
test -f .claude-plugin/plugin.json && echo "PASS: plugin.json created" || echo "FAIL: no plugin"
test -f ./outputs/*.plugin && echo "PASS: .plugin file packaged" || echo "FAIL: no .plugin file"
```

### Test 3: `/build` with malformed config

```bash
cd C:\Users\NMarchitecte\Documents\cc-cowork\hacienda-maker
echo "{ invalid json" > hacienda-maker.json

output=$(claude -p "/hacienda-maker:build" --cwd . 2>&1)
echo "$output" | grep -qi "malformed\|invalid\|run /collect" && echo "PASS: error handled" || echo "FAIL: no error"
```

### Test 4: `/customize` generic setup

```bash
cd C:\Users\NMarchitecte\Documents\cc-cowork

# Setup: create plugin with placeholders
mkdir -p test-placeholder/.claude-plugin
echo '{"name": "test-placeholder"}' > test-placeholder/.claude-plugin/plugin.json
mkdir -p test-placeholder/skills/test-skill
cat > test-placeholder/skills/test-skill/SKILL.md << 'EOF'
---
name: test-skill
description: Test
---
Post to ~~chat and ~~status-channel.
EOF

# Run customize (simulate user answering "Slack" and "#eng-updates")
claude -p "/hacienda-maker:customize test-placeholder" --cwd . --max-tokens 10000

# Assertions
grep -q "~~chat" test-placeholder/skills/test-skill/SKILL.md && echo "FAIL: placeholder not replaced" || echo "PASS: ~~chat replaced"
grep -q "~~status-channel" test-placeholder/skills/test-skill/SKILL.md && echo "FAIL: placeholder not replaced" || echo "PASS: ~~status-channel replaced"
grep -q "Slack\|#eng-updates" test-placeholder/skills/test-skill/SKILL.md && echo "PASS: replacement values present" || echo "FAIL: no replacement values"
test -f test-placeholder/.mcp.json && echo "PASS: .mcp.json exists" || echo "WARN: no .mcp.json (may not be connected)"
```

### Test 5: `/customize` scoped

```bash
cd C:\Users\NMarchitecte\Documents\cc-cowork

# Run with focus
claude -p "/hacienda-maker:customize test-placeholder --focus=connectors" --cwd . --max-tokens 5000

# Assertion: output should mention connectors/MCP, not skill content
# (Manual check or parse output for keyword presence)
```

### Test 6: MCP connection behavior

```bash
# This test requires Cowork desktop app with MCP registry available
# Manual verification: check that suggest_connectors is called with correct UUIDs
```

### Test 7: Existing test suite

```bash
cd C:\Users\NMarchitecte\Documents\cc-cowork\hacienda-maker
pytest tests/ -v

# Exit code should be 0
echo $?  # Should print 0
```

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Code duplication between build and create logic | Medium | Medium | **Shared references/**: Both workflows use the same `component-schemas.md` and `example-plugins.md` for schemas. No duplicate code. |
| Customizer requires Cowork desktop app | High | Low | **Runtime check**: Detect both `mnt/.local-plugins` AND `mnt/.plugins` existence. If neither exists, abort with message: "Customizing plugins requires the Cowork desktop app with mounted plugin directories." |
| MCP registry tools unavailable | Medium | Low | **Graceful fallback**: Print manual `.mcp.json` template with placeholder values, document in `customize-workflow.md`. |
| Placeholder edge cases (escaped `\~~`) | Low | Low | **Regex excludes**: Pattern `(?<!\\)~~[\w-]+` uses negative lookbehind to skip escaped placeholders. Documented in `customize-workflow.md`. |
| Windows vs Unix file operations | Medium | Low | **Use Claude tools**: All file edits use `Edit` and `Write` tools (cross-platform), not shell `sed`. Packaging uses `zip` command available in Git Bash on Windows. |
| User skips all customization questions | Medium | Low | **Leave unchanged**: If user skips, `~~` placeholders remain. Print warning: "Some placeholders were not replaced." |

## Success Criteria

| # | Criterion | Measurable Check |
|---|-----------|------------------|
| 1 | Single plugin installation | After install, `/hacienda-maker:customize` command available |
| 2 | `/build` with evals works | Test 1 assertions all pass |
| 3 | `/build` without evals triggers guided workflow | Test 2 assertions: `.plugin` file created |
| 4 | `/build` handles malformed config | Test 3: error message contains expected text |
| 5 | `/customize` detects placeholders | Test 4: no `~~` tokens remain after replacement |
| 6 | `/customize` replaces all placeholders | Test 4: replacement values present in file |
| 7 | `/customize` scoped focuses correctly | Test 5: output mentions only requested topic |
| 8 | Existing tests pass | Test 7: `pytest tests/` exits with code 0 |
| 9 | New functionality documented | SKILL.md contains "customize plugin" trigger phrase |
| 10 | Reference files present | All 5 new reference files exist in `references/` |
