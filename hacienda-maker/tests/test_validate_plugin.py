# hacienda-maker/tests/test_validate_plugin.py
import json
import subprocess
import sys
import tempfile
from pathlib import Path

VALIDATE_PY = Path(__file__).parent.parent / "skills/hacienda-maker/scripts/validate_plugin.py"

def run_validate(plugin_dir: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(VALIDATE_PY), str(plugin_dir)],
        capture_output=True, text=True
    )
    return result.returncode, result.stdout + result.stderr


def make_valid_plugin(tmp: Path) -> Path:
    """Create a minimal valid plugin for use as a base."""
    (tmp / ".claude-plugin").mkdir()
    (tmp / ".claude-plugin/plugin.json").write_text('{"name": "my-plugin"}')
    skill_dir = tmp / "skills/my-plugin"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: my-plugin\ndescription: test skill\n---\n")
    return tmp

# Rule 1: plugin.json exists with valid kebab-case name
def test_rule1_missing_plugin_json(tmp_path):
    code, out = run_validate(tmp_path)
    assert code != 0
    assert "Rule 1" in out

def test_rule1_invalid_name_uppercase(tmp_path):
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin/plugin.json").write_text('{"name": "MyPlugin"}')
    code, out = run_validate(tmp_path)
    assert code != 0
    assert "Rule 1" in out

def test_rule1_valid_name(tmp_path):
    make_valid_plugin(tmp_path)
    code, _ = run_validate(tmp_path)
    assert code == 0

# Rule 2: SKILL.md name matches directory
def test_rule2_name_mismatch(tmp_path):
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin/plugin.json").write_text('{"name": "my-plugin"}')
    skill_dir = tmp_path / "skills/my-plugin"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: wrong-name\ndescription: test\n---\n")
    code, out = run_validate(tmp_path)
    assert code != 0
    assert "Rule 2" in out

# Rule 3: description under 1024 chars, no < or >
def test_rule3_description_too_long(tmp_path):
    make_valid_plugin(tmp_path)
    skill = tmp_path / "skills/my-plugin/SKILL.md"
    skill.write_text(f"---\nname: my-plugin\ndescription: {'x' * 1025}\n---\n")
    code, out = run_validate(tmp_path)
    assert code != 0
    assert "Rule 3" in out

def test_rule3_description_has_angle_bracket(tmp_path):
    make_valid_plugin(tmp_path)
    skill = tmp_path / "skills/my-plugin/SKILL.md"
    skill.write_text("---\nname: my-plugin\ndescription: use <this> skill\n---\n")
    code, out = run_validate(tmp_path)
    assert code != 0
    assert "Rule 3" in out

# Rule 4: tools: must be YAML sequence, not comma string
def test_rule4_tools_comma_string_fails(tmp_path):
    make_valid_plugin(tmp_path)
    agent = tmp_path / "skills/my-plugin/agents"
    agent.mkdir()
    (agent / "my-agent.md").write_text("---\ntools: Read, Grep\n---\n")
    code, out = run_validate(tmp_path)
    assert code != 0
    assert "Rule 4" in out

def test_rule4_tools_yaml_list_passes(tmp_path):
    make_valid_plugin(tmp_path)
    agent = tmp_path / "skills/my-plugin/agents"
    agent.mkdir()
    (agent / "my-agent.md").write_text("---\ntools:\n  - Read\n  - Grep\n---\n")
    code, _ = run_validate(tmp_path)
    assert code == 0

# Rule 5: no hardcoded absolute paths
def test_rule5_absolute_path_fails(tmp_path):
    make_valid_plugin(tmp_path)
    (tmp_path / "skills/my-plugin/SKILL.md").write_text(
        "---\nname: my-plugin\ndescription: test\n---\nSee /Users/john/scripts/run.sh"
    )
    code, out = run_validate(tmp_path)
    assert code != 0
    assert "Rule 5" in out

# Rule 6: hooks.json absent → silent pass; present → check CLAUDE_PLUGIN_ROOT
def test_rule6_no_hooks_file_passes(tmp_path):
    make_valid_plugin(tmp_path)
    code, _ = run_validate(tmp_path)
    assert code == 0

def test_rule6_hooks_without_plugin_root_fails(tmp_path):
    make_valid_plugin(tmp_path)
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks/hooks.json").write_text(
        '[{"command": "/home/user/scripts/run.sh", "event": "preToolUse"}]'
    )
    code, out = run_validate(tmp_path)
    assert code != 0
    assert "Rule 6" in out

def test_rule6_hooks_with_plugin_root_passes(tmp_path):
    make_valid_plugin(tmp_path)
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks/hooks.json").write_text(
        '[{"command": "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh", "event": "preToolUse"}]'
    )
    code, _ = run_validate(tmp_path)
    assert code == 0
