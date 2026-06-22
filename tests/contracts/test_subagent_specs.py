"""PI-395: the scaffolder ships reusable `.claude/agents/` subagent specs."""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _split_spec(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter dict, body). Asserts the open+close `---` delimiters
    exist so a malformed spec fails clearly rather than with an IndexError."""
    parts = text.split("---\n", 2)
    assert len(parts) == 3 and parts[0] == "", "spec needs YAML frontmatter + body"
    fm: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line and not line.startswith((" ", "#")):
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm, parts[2].strip()


def test_ships_reusable_subagent_specs(tmp_path: Path):
    target = tmp_path / "p"
    scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
    agents = target / ".claude" / "agents"
    for name in ("code-reviewer", "explore"):
        spec = agents / f"{name}.md"
        assert spec.is_file(), f"{name}.md must be scaffolded"
        fm, body = _split_spec(spec.read_text())
        assert fm.get("name") == name, f"{name}.md frontmatter name mismatch"
        assert fm.get("description"), f"{name}.md needs a description"
        # model-agnostic by default so the spec works on any session model
        assert fm.get("model") == "inherit"
        assert body, f"{name}.md needs a system-prompt body"
