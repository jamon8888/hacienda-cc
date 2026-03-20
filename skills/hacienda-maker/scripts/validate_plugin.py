#!/usr/bin/env python3
"""validate_plugin.py — validates plugin structure against 6 rules.
Usage: python validate_plugin.py <plugin_dir>
Exits 0 on success, 1 on failure. Prints failing rule name + offending path.
"""
import json
import re
import sys
from pathlib import Path

KEBAB_RE = re.compile(r'^[a-z][a-z0-9-]*[a-z0-9]$')
SCAN_EXTS = {'.md', '.json', '.yaml', '.toml'}


def fail(rule: str, detail: str):
    print(f"FAIL {rule}: {detail}")
    sys.exit(1)


def read_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from markdown. Returns {} if none found."""
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return {}
    try:
        import yaml
        return yaml.safe_load(match.group(1)) or {}
    except ImportError:
        # Fallback: simple key: value parsing without yaml library
        result = {}
        for line in match.group(1).split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                result[key.strip()] = val.strip()
        return result
    except Exception:
        return {}


def scan_files(plugin_dir: Path):
    for path in plugin_dir.rglob('*'):
        if path.is_file() and path.suffix in SCAN_EXTS:
            if 'node_modules' not in path.parts:
                yield path


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_plugin.py <plugin_dir>")
        sys.exit(1)
    plugin_dir = Path(sys.argv[1]).resolve()

    # Rule 1: .claude-plugin/plugin.json exists with valid kebab-case name
    plugin_json = plugin_dir / '.claude-plugin/plugin.json'
    if not plugin_json.exists():
        fail("Rule 1", f".claude-plugin/plugin.json not found in {plugin_dir}")
    try:
        manifest = json.loads(plugin_json.read_text())
        name = manifest.get('name', '')
    except Exception as e:
        fail("Rule 1", f"Cannot parse plugin.json: {e}")
    if not KEBAB_RE.match(name):
        fail("Rule 1", f"name '{name}' does not match kebab-case pattern ^[a-z][a-z0-9-]*[a-z0-9]$")

    # Rule 2: every skills/*/SKILL.md has name: matching its parent dir
    for skill_md in plugin_dir.glob('skills/*/SKILL.md'):
        parent_name = skill_md.parent.name
        fm = read_frontmatter(skill_md.read_text())
        skill_name = fm.get('name', '')
        if skill_name != parent_name:
            fail("Rule 2", f"{skill_md}: name '{skill_name}' != parent dir '{parent_name}'")

    # Rule 3: every description: in frontmatter is < 1024 chars, no < or >
    for path in scan_files(plugin_dir):
        if path.suffix == '.md':
            fm = read_frontmatter(path.read_text())
            desc = fm.get('description', '')
            if desc:
                if len(str(desc)) >= 1024:
                    fail("Rule 3", f"{path}: description is {len(str(desc))} chars (max 1023)")
                if '<' in str(desc) or '>' in str(desc):
                    fail("Rule 3", f"{path}: description contains < or >")

    # Rule 4: every agent file's tools: field is a YAML sequence (not comma string)
    for path in scan_files(plugin_dir):
        if path.suffix == '.md' and 'agents' in path.parts:
            fm = read_frontmatter(path.read_text())
            tools = fm.get('tools')
            if tools is not None and isinstance(tools, str):
                fail("Rule 4", f"{path}: tools: is a comma-separated string, must be YAML sequence")

    # Rule 5: no absolute paths in any scanned file (hooks/hooks.json is handled by Rule 6)
    hooks_json_path = plugin_dir / 'hooks/hooks.json'
    for path in scan_files(plugin_dir):
        if path.resolve() == hooks_json_path.resolve():
            continue
        content = path.read_text(errors='replace')
        for line_num, line in enumerate(content.splitlines(), 1):
            if re.search(r'/Users/|/home/|/root/', line) or re.search(r'C:\\', line):
                fail("Rule 5", f"{path}:{line_num}: absolute path detected")

    # Rule 6: if hooks/hooks.json exists, command paths must use ${CLAUDE_PLUGIN_ROOT}
    hooks_file = plugin_dir / 'hooks/hooks.json'
    if hooks_file.exists():
        try:
            hooks = json.loads(hooks_file.read_text())
        except Exception as e:
            fail("Rule 6", f"Cannot parse hooks/hooks.json: {e}")
        for i, hook in enumerate(hooks if isinstance(hooks, list) else []):
            cmd = hook.get('command', '')
            if (cmd.startswith('/') or re.match(r'[A-Za-z]:\\', cmd)) and '${CLAUDE_PLUGIN_ROOT}' not in cmd:
                fail("Rule 6", f"hooks/hooks.json[{i}].command '{cmd}' uses absolute path without ${{CLAUDE_PLUGIN_ROOT}}")

    print("OK: all rules passed")
    sys.exit(0)


if __name__ == '__main__':
    main()
