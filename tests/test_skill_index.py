from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_SKILLS_DIR = Path(__file__).parent.parent / "templates" / "base" / "dot_claude" / "skills"
_INDEX_PATH = _SKILLS_DIR / "INDEX.md"


class TestSkillIndex:
    """Verify INDEX.md exists and covers every skill directory."""

    def test_index_file_exists(self):
        assert _INDEX_PATH.exists(), "templates/base/dot_claude/skills/INDEX.md missing"

    def test_every_skill_dir_mentioned_in_index(self):
        index_text = _INDEX_PATH.read_text()
        missing = []
        for skill_dir in _SKILLS_DIR.iterdir():
            if not skill_dir.is_dir():
                continue
            if skill_dir.name not in index_text:
                missing.append(skill_dir.name)
        assert not missing, (
            "Skill directories not referenced in INDEX.md: " + ", ".join(missing)
        )

    def test_index_scaffolded_into_project(self, tmp_path: Path):
        target = tmp_path / "proj"
        preset = load_preset("obsidian-only")
        scaffold(target, preset, make_variables())
        index = target / ".claude" / "skills" / "INDEX.md"
        assert index.exists(), ".claude/skills/INDEX.md not scaffolded into project"

    def test_index_content_in_scaffolded_project(self, tmp_path: Path):
        target = tmp_path / "proj"
        preset = load_preset("obsidian-only")
        scaffold(target, preset, make_variables())
        content = (target / ".claude" / "skills" / "INDEX.md").read_text()
        assert "start-task" in content
        assert "session-summary" in content
        assert "add-hook" in content
        assert "add-command" in content


class TestAgentInstructionFiles:
    """Verify AGENTS.md and GEMINI.md reference the skills index after scaffolding."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = tmp_path / "proj"
        preset = load_preset("obsidian-only")
        scaffold(self.target, preset, make_variables())

    def test_agents_md_references_skills_index(self):
        content = (self.target / "AGENTS.md").read_text()
        assert "INDEX.md" in content or "skills" in content.lower()

    def test_gemini_md_references_skills_index(self):
        content = (self.target / "GEMINI.md").read_text()
        assert "INDEX.md" in content or "skills" in content.lower()
