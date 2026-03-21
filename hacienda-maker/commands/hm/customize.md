---
description: >
  Use when the user runs /hm:customize. Tailors a plugin for a specific
  organization with placeholder replacement and MCP connector setup.
---

# /hm:customize

Tailor a plugin for a specific organization with MCP connector setup.

**Usage**: `/hm:customize [plugin-name] [--focus=<section>]`

- `plugin-name`: Optional. Name or path to plugin directory. If omitted, searches for plugin in `mnt/.local-plugins` and `mnt/.plugins`.
- `--focus`: Optional. Restricts customization to specific section (e.g., `--focus=connectors`).

Read `references/customize-workflow.md` for the full protocol.

Summary:
1. Locate plugin directory (Cowork mounts or provided path)
2. Detect mode: scoped (--focus), generic setup (~~ placeholders), or general
3. Apply customizations based on mode
4. Connect MCPs for identified tools
5. Validate and package as `.plugin` file
