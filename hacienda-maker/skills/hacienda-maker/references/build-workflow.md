# Build Workflow

## Purpose

Scaffold a plugin skeleton from collected evals or through guided discovery, then run baseline evaluation or package.

## Mode Detection

At the start of the workflow:

1. Check if `hm.json` exists in working directory
2. If exists: validate and check for `use_cases` and `evals`
3. If missing: run guided workflow

## Evals-Based Workflow

**Trigger**: `hm.json` exists with valid `use_cases` and `evals` fields

### Steps

1. Read `hm.json` — verify `use_cases` and `evals` fields exist
2. Determine plugin name from `hm.json` or ask user
3. Create minimal skeleton:
   - `.claude-plugin/plugin.json` with `{"name": "<plugin-name>", "version": "0.1.0"}`
   - `skills/<plugin-name>/SKILL.md` with frontmatter synthesized from use cases
4. Run structural validation:
   - Check `.claude-plugin/plugin.json` exists and has `name` field
   - Check `skills/*/SKILL.md` exists with valid frontmatter
   - If fails: print error and stop. User must fix before continuing.
5. Run inline baseline evaluation:
   - Read `references/inline-evaluation.md` for protocol
   - Run trigger evaluation: match trigger-eval.json queries against SKILL.md
   - Run functional evaluation: execute evals.json prompts, check expectations
   - Compute combined score
   - Write `evals/last-run.json`
6. Initialize TSV log: write header row to `hm-results.tsv`:
   ```
   iteration\tcombined_score\ttrigger_score\tfunctional_score\tdelta\tis_improvement\tcommit_sha\ttimestamp
   ```
   Then append baseline row (iteration=0).

## Guided Workflow

**Trigger**: `hm.json` does not exist OR has no evals

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
   - Validate: check plugin.json and SKILL.md structure
   - Create outputs directory: `mkdir -p ./outputs`
   - Package: `cd <plugin-dir> && zip -r ../outputs/<name>.plugin . -x "*.DS_Store"`
   - Present `.plugin` file to user

## Error Handling

| Condition | Behavior | User Message |
|----------|----------|--------------|
| `hm.json` malformed (invalid JSON) | Abort | "hm.json is malformed. Run /hm:collect to regenerate." |
| `use_cases` empty array or missing | Abort | "No use cases defined. Run /hm:collect first." |
| `evals` empty array | Auto-generate from use cases | (proceed silently) |
| User skips all discovery questions | Create minimal plugin | "Creating minimal plugin with default skill." |
| Validation fails after scaffolding | Print errors, stop | (show validation errors) |

## SKILL.md Description Synthesis

Generate description from use cases:
- Lead with: "Use this skill when the user wants to..."
- Include 3–5 exact phrasings from use case descriptions
- Keep under 500 characters
- No angle brackets
