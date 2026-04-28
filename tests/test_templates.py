from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


class TestNodeTemplate:
    """Verify Node/bun conditional block renders correctly."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = tmp_path / "node-proj"
        preset = load_preset("obsidian-only")
        variables = make_variables(
            language="node",
            python="",
            node="true",
            lint_command="bun run lint",
            format_command="bun run format",
            test_command="bun test",
        )
        scaffold(self.target, preset, variables)

    def test_node_rule_file_present(self):
        rule = self.target / ".claude" / "rules" / "node.md"
        assert rule.exists()
        content = rule.read_text()
        assert "bun install" in content
        assert "bunx" in content

    def test_node_rule_has_globs(self):
        content = (self.target / ".claude" / "rules" / "node.md").read_text()
        assert "globs" in content
        assert "package.json" in content

    def test_python_rule_not_contaminated_in_node(self):
        # python rule file still ships (it's in base), but project-init.md has no uv sync
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "uv sync" not in content

    def test_no_npm_commands_in_node_template(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        # "npm" may appear in a "don't use npm" note — that's fine.
        # What must NOT appear are npm invocations as commands.
        assert "npm install" not in content
        assert "npm run" not in content
        assert "npx " not in content

    def test_hooks_use_bunx_not_node_modules(self):
        for hook in ["post-edit-lint.sh", "pre-commit-gate.sh"]:
            content = (self.target / ".claude" / "hooks" / hook).read_text()
            assert "node_modules/.bin/eslint" not in content
            assert "bunx eslint" in content


class TestTemplateIdentifiers:
    """Verify no hardcoded owner identity leaks into scaffolded files."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        scaffold(tmp_target, preset, make_variables(
            project_init_url="https://github.com/example/project-init"
        ))

    def test_agents_md_redirects_to_claude(self):
        content = (self.target / "AGENTS.md").read_text()
        assert "VytCepas" not in content
        assert "CLAUDE.md" in content
        assert "source of truth" in content

    def test_claude_md_uses_template_url(self):
        content = (self.target / "CLAUDE.md").read_text()
        assert "VytCepas" not in content
        assert "github.com/example/project-init" in content

    def test_project_init_md_uses_template_url(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "VytCepas" not in content
        assert "github.com/example/project-init" in content

    def test_no_hardcoded_owner_in_any_template_file(self):
        for f in self.target.rglob("*"):
            if f.is_file():
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    assert "VytCepas" not in text, f"VytCepas found in {f}"
                except OSError:
                    pass


class TestScaffoldGitHubFiles:
    """Verify .github/ and agent-instruction files are scaffolded correctly."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        variables = make_variables()
        scaffold(tmp_target, preset, variables)

    def test_issue_template_bug_created(self):
        assert (self.target / ".github" / "ISSUE_TEMPLATE" / "bug.yml").is_file()

    def test_issue_template_feature_created(self):
        assert (self.target / ".github" / "ISSUE_TEMPLATE" / "feature.yml").is_file()

    def test_issue_template_chore_created(self):
        assert (self.target / ".github" / "ISSUE_TEMPLATE" / "chore.yml").is_file()

    def test_issue_template_docs_created(self):
        assert (self.target / ".github" / "ISSUE_TEMPLATE" / "docs.yml").is_file()

    def test_issue_template_test_created(self):
        assert (self.target / ".github" / "ISSUE_TEMPLATE" / "test.yml").is_file()

    def test_validate_pr_workflow_created(self):
        assert (self.target / ".github" / "workflows" / "validate-pr.yml").is_file()

    def test_board_automation_workflow_created(self):
        assert (self.target / ".github" / "workflows" / "board-automation.yml").is_file()

    def test_review_status_workflow_created(self):
        assert (self.target / ".github" / "workflows" / "review-status.yml").is_file()

    def test_workflow_runners_are_pinned(self):
        workflows = self.target / ".github" / "workflows"
        for name in ("ci.yml", "validate-pr.yml", "board-automation.yml", "review-status.yml"):
            content = (workflows / name).read_text()
            assert "runs-on: ubuntu-24.04" in content
            assert "runs-on: ubuntu-latest" not in content

    def test_ci_template_pins_uv_version(self):
        content = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert 'version: "0.11.7"' in content

    def test_ci_template_uses_node24_action_versions(self):
        content = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert "actions/checkout@v6" in content
        assert "astral-sh/setup-uv@v8.1.0" in content
        assert "actions/checkout@v4" not in content
        assert "astral-sh/setup-uv@v3" not in content

    def test_pull_request_template_created(self):
        assert (self.target / ".github" / "pull_request_template.md").is_file()

    def test_copilot_instructions_created(self):
        f = self.target / ".github" / "copilot-instructions.md"
        assert f.is_file()
        content = f.read_text()
        assert "GitHub Projects" in content
        assert "CLAUDE.md" in content
        assert "<issue_type>/<project_abbr>-<issue_number>-<slug>" in content
        assert "[PROJECT-123][type] description" in content
        assert "[#N][type] description" not in content
        assert "PR title must start with" not in content
        assert ".claude/scripts/monitor-pr.sh <pr-number> --merge" in content
        assert "fix actionable feedback" in content

    def test_gemini_md_created(self):
        f = self.target / "GEMINI.md"
        assert f.is_file()
        content = f.read_text()
        assert "CLAUDE.md" in content
        assert "source of truth" in content
        assert "GitHub Projects" not in content
        assert "[PROJECT-123][type] description" not in content

    def test_monitor_pr_can_merge_when_clean(self):
        script = self.target / ".claude" / "scripts" / "monitor-pr.sh"
        assert script.is_file()
        content = script.read_text()
        assert "--merge" in content
        assert "gh pr merge" in content
        assert "gh pr checks" in content
        assert "--json" in content  # uses json polling, not --watch, to suppress noise
        assert "--delete-branch" in content

    def test_validate_pr_enforces_project_key_title_format(self):
        """PR title must match [PROJECT-123][type] or [nojira][type] format."""
        content = (self.target / ".github" / "workflows" / "validate-pr.yml").read_text()
        # Check for the new regex pattern with type validation
        assert "[A-Z][A-Z0-9]{1,9}-[0-9]+" in content
        assert "(feat|fix|chore|docs|test)" in content
        assert "nojira" in content
        # Ensure old format is not present (should have been updated)
        assert r"grep -qE '^\[#[0-9]+\]'" not in content

    def test_issue_templates_have_required_fields(self):
        for name in ("bug.yml", "feature.yml", "chore.yml", "docs.yml", "test.yml"):
            content = (self.target / ".github" / "ISSUE_TEMPLATE" / name).read_text()
            assert "name:" in content
            assert "labels:" in content

    def test_no_dot_github_dir_remaining(self):
        assert not (self.target / "dot_github").exists()

    def test_validate_pr_accepts_nojira_prs(self):
        """PRs without issues can use [nojira][type] format."""
        content = (self.target / ".github" / "workflows" / "validate-pr.yml").read_text()
        # Check for nojira skip logic in closes-keyword job
        assert "nojira" in content
        assert "skipping Closes keyword check" in content

    def test_pre_push_hook_created(self):
        """Pre-push hook prevents direct commits to main/master."""
        hook_path = self.target / ".github" / "hooks" / "pre-push"
        assert hook_path.is_file()
        content = hook_path.read_text()
        # Verify the hook prevents pushing to main
        assert "refs/heads/main" in content or "refs/heads/master" in content
        assert "ERROR" in content or "not allowed" in content
        assert "<issue_type>/<project_abbr>-<issue_number>-<slug>" in content

    def test_commit_msg_hook_created(self):
        hook = self.target / ".github" / "hooks" / "commit-msg"
        assert hook.is_file()

    def test_commit_msg_hook_validates_format(self):
        content = (self.target / ".github" / "hooks" / "commit-msg").read_text()
        assert "nojira" in content
        assert "feat|fix|chore|docs|test" in content
        assert "[A-Z]" in content  # accepts any project key (PI-, APP-, etc.)

    def test_commit_msg_hook_is_executable(self):
        hook = self.target / ".github" / "hooks" / "commit-msg"
        assert hook.stat().st_mode & 0o111, "commit-msg hook must be executable"

    def test_gemini_no_unrendered_placeholders(self):
        import re

        placeholder_re = re.compile(r"(?<!\$)\{\{[^}]+\}\}")
        text = (self.target / "GEMINI.md").read_text()
        matches = placeholder_re.findall(text)
        assert not matches, f"Unrendered placeholders in GEMINI.md: {matches}"


def test_project_validate_pr_workflow_accepts_project_keys():
    """The live validate-pr.yml must accept any project key (PI-, APP-, etc.) not just PI-."""
    content = (
        Path(__file__).resolve().parent.parent / ".github" / "workflows" / "validate-pr.yml"
    ).read_text()
    assert "[A-Z]" in content  # generic project key pattern
    assert "nojira" in content
    assert "feat|fix|chore|docs|test" in content
