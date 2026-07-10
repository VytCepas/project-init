from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / "templates" / "fallback" / "dot_agents" / "skills"
# INDEX.md became a template (#476) so its lifecycle skill rows can be gated.
_INDEX_PATH = _SKILLS_DIR / "INDEX.md.tmpl"


class TestSkillIndex:
    """Verify INDEX.md exists and covers every skill directory."""

    def test_index_file_exists(self):
        assert _INDEX_PATH.exists(), "templates/fallback/dot_agents/skills/INDEX.md.tmpl missing"

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

    def test_this_repos_own_index_covers_every_skill_dir(self):
        """PI-686: the template INDEX was guarded; this repo's own INDEX was not.

        `_INDEX_PATH` above points at `templates/fallback/...INDEX.md.tmpl`, so a
        skill added under this repo's `.agents/skills/` and forgotten in its
        INDEX passed CI. Only `test_wiki_skill.py` touched the own-repo INDEX, and
        only to assert the literal string "wiki".

        Matches the *link*, not the bare directory name (PR #724 review): "wiki"
        appearing in prose — or as a substring of a longer word — would satisfy a
        name-only check while the skill went unindexed.
        """
        own_skills = _REPO_ROOT / ".agents" / "skills"
        own_index = own_skills / "INDEX.md"
        assert own_index.exists(), ".agents/skills/INDEX.md missing"
        index_text = own_index.read_text(encoding="utf-8")
        missing = [
            d.name
            for d in sorted(own_skills.iterdir())
            if d.is_dir() and f".agents/skills/{d.name}/SKILL.md" not in index_text
        ]
        assert not missing, (
            "skill directories not linked from .agents/skills/INDEX.md "
            "(expected `.agents/skills/<dir>/SKILL.md`): " + ", ".join(missing)
        )

    def test_index_scaffolded_into_project(self, tmp_path: Path):
        target = tmp_path / "proj"
        preset = fallback_preset()
        scaffold(target, preset, fallback_variables())
        index = target / ".agents" / "skills" / "INDEX.md"
        assert index.exists(), ".agents/skills/INDEX.md not scaffolded into project"

    def test_index_content_in_scaffolded_project(self, tmp_path: Path):
        target = tmp_path / "proj"
        preset = fallback_preset()
        scaffold(target, preset, fallback_variables())
        content = (target / ".agents" / "skills" / "INDEX.md").read_text()
        assert "start_task" in content
        assert "session_summary" in content
        assert "add_hook" in content
        assert "add_command" in content
        assert "github_workflow" in content

    def test_github_workflow_skill_scaffolded(self, tmp_path: Path):
        target = tmp_path / "proj"
        preset = fallback_preset()
        scaffold(target, preset, fallback_variables())
        skill = target / ".agents" / "skills" / "github_workflow" / "SKILL.md"
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
    _SKILL_ROOTS = (_SKILLS_DIR, _REPO_ROOT / ".agents" / "skills")

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
        audit = _REPO_ROOT / "templates" / "lifecycle_fallback" / "dot_agents" / "skills" / "audit"
        fm = self._frontmatter(audit / "SKILL.md")
        assert fm.get("context") == "fork"


class TestCodeMapStaleness:
    """PI-686: the scaffolded CODE_MAP had a generator but no staleness check.

    `gen_code_map.py` was wired only to a manual `just code-map` recipe — absent
    from the scaffolded ci.yml, pre-push hook, install_hooks.sh, and pre-commit
    config. The file whose header says "read this before grepping" rotted freely
    in every scaffolded project.
    """

    def _ci(self, tmp_path: Path, language: str) -> str:
        target = tmp_path / f"proj-{language}"
        scaffold(target, fallback_preset(), fallback_variables(**{language: "true"}))
        return (target / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    def test_python_ci_checks_the_code_map(self, tmp_path: Path):
        ci = self._ci(tmp_path, "python")
        assert "CODE_MAP is current" in ci
        # Compares, never rewrites the committed file.
        assert "cmp -s" in ci
        assert "run 'just code-map' and commit" in ci

    def test_missing_generator_fails_rather_than_skipping(self, tmp_path: Path):
        """PR #724 review: a broken scaffold must not pass a check that can't run.

        A missing map means "not generated yet" (skip); a missing generator means
        the scaffold is broken (fail). The first guard conflated them.
        """
        ci = self._ci(tmp_path, "python")
        step = ci.split("name: CODE_MAP is current", 1)[1].split("- name:", 1)[0]
        assert "the CODE_MAP staleness check cannot run" in step
        assert 'if [ ! -f "$gen" ]; then' in step
        assert 'if [ ! -f "$map" ]; then' in step
        # The two conditions are no longer OR-ed into one skip.
        assert '[ ! -f "$map" ] || [ ! -f "$gen" ]' not in step

    def test_non_python_ci_omits_the_check(self, tmp_path: Path):
        """The generator is a Python AST walker; there is nothing to map."""
        target = tmp_path / "proj-go"
        variables = fallback_variables(python="", go="true", language="go")
        scaffold(target, fallback_preset(), variables)
        ci = (target / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "CODE_MAP is current" not in ci
