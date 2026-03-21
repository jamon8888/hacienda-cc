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
|---|---|
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
|---|---|
| Plugin directory not found | Abort: "Plugin not found. Customize requires Cowork desktop app with plugins in mnt/.local-plugins or mnt/.plugins." |
| MCP registry unavailable | Print manual instructions, continue packaging |
| User skips all questions | Leave `~~` placeholders unchanged, print warning |
| Validation fails | Print errors, do not package |
