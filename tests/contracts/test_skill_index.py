from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / "templates" / "fallback" / "dot_claude" / "skills"
# INDEX.md became a template (#476) so its lifecycle skill rows can be gated.
_INDEX_PATH = _SKILLS_DIR / "INDEX.md.tmpl"


class TestSkillIndex:
    """Verify INDEX.md exists and covers every skill directory."""

    def test_index_file_exists(self):
        assert _INDEX_PATH.exists(), "templates/fallback/dot_claude/skills/INDEX.md.tmpl missing"

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
        preset = fallback_preset()
        scaffold(target, preset, fallback_variables())
        index = target / ".claude" / "skills" / "INDEX.md"
        assert index.exists(), ".claude/skills/INDEX.md not scaffolded into project"

    def test_index_content_in_scaffolded_project(self, tmp_path: Path):
        target = tmp_path / "proj"
        preset = fallback_preset()
        scaffold(target, preset, fallback_variables())
        content = (target / ".claude" / "skills" / "INDEX.md").read_text()
        assert "start_task" in content
        assert "session_summary" in content
        assert "add_hook" in content
        assert "add_command" in content
        assert "github_workflow" in content

    def test_github_workflow_skill_scaffolded(self, tmp_path: Path):
        target = tmp_path / "proj"
        preset = fallback_preset()
        scaffold(target, preset, fallback_variables())
        skill = target / ".claude" / "skills" / "github_workflow" / "SKILL.md"
        assert skill.exists(), "github_workflow/SKILL.md not scaffolded"
        content = skill.read_text()
        assert "finish_pr.sh" in content
        assert "monitor_pr.sh" in content
        assert "review-cycle" in content


class TestAgentInstructionFiles:
    """Verify AGENTS.md references the skills index after scaffolding."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = tmp_path / "proj"
        preset = fallback_preset()
        scaffold(self.target, preset, fallback_variables())

    def test_agents_md_references_skills_index(self):
        content = (self.target / "AGENTS.md").read_text()
        assert "INDEX.md" in content or "skills" in content.lower()


class TestSkillFrontmatter:
    """PI-133: every skill carries valid, discovery-friendly frontmatter."""

    def _frontmatter(self, path: Path) -> dict[str, str]:
        lines = path.read_text().splitlines()
        assert lines and lines[0] == "---", f"{path}: missing frontmatter open"
        fields: dict[str, str] = {}
        for line in lines[1:]:
            if line == "---":
                return fields
            if ":" in line and not line.startswith((" ", "\t", "-")):
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        raise AssertionError(f"{path}: frontmatter never closed")

    # Template skills and this repo's own skills both follow the standard.
    _SKILL_ROOTS = (_SKILLS_DIR, _REPO_ROOT / ".claude" / "skills")

    def _skill_files(self):
        for root in self._SKILL_ROOTS:
            for skill_dir in sorted(root.iterdir()):
                if not skill_dir.is_dir():
                    continue
                for name in ("SKILL.md", "SKILL.md.tmpl"):
                    p = skill_dir / name
                    if p.exists():
                        yield p

    def test_all_skills_have_name_and_description(self):
        for path in self._skill_files():
            fm = self._frontmatter(path)
            assert fm.get("name"), f"{path}: frontmatter missing name"
            assert fm.get("description"), f"{path}: frontmatter missing description"

    def test_all_skills_have_when_to_use(self):
        """when_to_use drives discovery for both users and model invocation."""
        for path in self._skill_files():
            fm = self._frontmatter(path)
            assert fm.get("when_to_use"), f"{path}: frontmatter missing when_to_use"

    def test_sub_skills_marked_not_user_invocable(self):
        """Skills documented as indirectly invoked must not be /command-visible."""
        for root in self._SKILL_ROOTS:
            for skill in ("create_issue", "github_workflow"):
                path = root / skill / "SKILL.md"
                if not path.exists():
                    continue
                fm = self._frontmatter(path)
                assert fm.get("user-invocable") == "false", (
                    f"{path}: expected user-invocable: false"
                )

    def test_audit_runs_in_forked_context(self):
        """Heavyweight scan isolates its context; findings land in a GitHub issue."""
        # audit moved to the lifecycle_fallback overlay (#476).
        audit = _REPO_ROOT / "templates" / "lifecycle_fallback" / "dot_claude" / "skills" / "audit"
        fm = self._frontmatter(audit / "SKILL.md")
        assert fm.get("context") == "fork"
