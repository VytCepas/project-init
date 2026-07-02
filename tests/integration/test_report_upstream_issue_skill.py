"""The default-on report-upstream-issue skill (routes tooling bugs to project-init).

The skill classifies a bug as project-specific vs shared scaffolding/tooling and
routes tooling-level reports upstream to the project-init repo (resolved from the
scaffold record, never hardcoded) so the same defect is fixed once for every
project. It ships to every scaffolded project, on both the Claude and Codex
surfaces, enabled by default.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import fallback_preset, fallback_variables, make_variables


class TestReportUpstreamIssueSkill:
    def test_present_and_default_on_no_plugin(self, tmp_target: Path):
        """--no-plugin copies the skill in as a real .claude/skills file, on by
        default (no opt-in flag), with the required frontmatter."""
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        skill = (
            tmp_target
            / ".claude"
            / "skills"
            / "report_upstream_issue"
            / "SKILL.md"
        )
        content = skill.read_text()
        assert "name: report_upstream_issue" in content
        assert "when_to_use:" in content
        # User-invocable so `/report_upstream_issue` works; on by default.
        assert "user-invocable: true" in content

    def test_present_on_codex_surface(self, tmp_path: Path):
        """The skill also ships to the Codex surface (.agents/skills)."""
        preset = load_preset("obsidian-only")
        preset = {**preset, "layers": [*preset["layers"], "codex"]}
        target = tmp_path / "proj"
        scaffold(
            target,
            preset,
            make_variables(
                plugin_mode="true",
                no_plugin="",
                codex="true",
                multi_agent="true",
                agents="claude,codex",
            ),
        )
        skill = target / ".agents" / "skills" / "report_upstream_issue" / "SKILL.md"
        assert skill.exists()
        assert "name: report_upstream_issue" in skill.read_text()

    def test_body_classifies_and_routes_upstream(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        content = (
            tmp_target
            / ".claude"
            / "skills"
            / "report_upstream_issue"
            / "SKILL.md"
        ).read_text()
        # Classification: project-level vs tooling/scaffolding.
        assert "Classify" in content
        assert "project-level" in content.lower()
        assert "tooling" in content.lower()
        # Upstream target resolved from the scaffold record — never hardcoded.
        assert "scaffold.variables.project_init_repo" in content
        assert "hardcode" in content.lower()
        # Default method is a prefilled github.com "new issue" link.
        assert "issues/new?title=" in content
        # Direct create is the secondary, scope-gated path.
        assert "gh issue create" in content
        # Conform to the UPSTREAM repo's own conventions, not this template.
        assert "conventional-commit" in content.lower()
        assert "gh issue list" in content
        # Project-level bugs are filed locally (via the create_issue skill).
        assert "create_issue" in content
        # Confirm target + title/body before filing.
        assert "confirm" in content.lower()

    def test_listed_in_skill_tables(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        index = (tmp_target / ".claude" / "skills" / "INDEX.md").read_text()
        assert "report_upstream_issue" in index
        readme = (tmp_target / ".claude" / "skills" / "README.md").read_text()
        assert "report_upstream_issue" in readme
        project_init = (tmp_target / ".claude" / "project-init.md").read_text()
        assert "report_upstream_issue" in project_init
