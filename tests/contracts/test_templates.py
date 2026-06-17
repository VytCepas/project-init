from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


class TestNodeTemplate:
    """Verify Node/bun conditional block renders correctly."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = tmp_path / "node-proj"
        preset = fallback_preset()
        variables = fallback_variables(
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
        for hook in ["post_edit_lint.sh", "pre_commit_gate.sh"]:
            content = (self.target / ".claude" / "hooks" / hook).read_text()
            assert "node_modules/.bin/eslint" not in content
            assert "bunx eslint" in content


class TestTemplateIdentifiers:
    """Verify no hardcoded owner identity leaks into scaffolded files."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = fallback_preset()
        scaffold(tmp_target, preset, fallback_variables(
            project_init_url="https://github.com/example/project-init"
        ))

    def test_claude_md_redirects_to_agents(self):
        """PI-136: AGENTS.md is canonical; CLAUDE.md is the redirect."""
        content = (self.target / "CLAUDE.md").read_text()
        assert "VytCepas" not in content
        assert "AGENTS.md" in content
        assert "source of truth" in content

    def test_agents_md_is_canonical_and_uses_template_url(self):
        content = (self.target / "AGENTS.md").read_text()
        assert "VytCepas" not in content
        assert "github.com/example/project-init" in content
        assert "Key rules for agents" in content
        assert "Claude Code specifics" in content

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
        preset = fallback_preset()
        variables = fallback_variables()
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

    def test_validate_pr_sets_gh_repo(self):
        """PI-210: `gh issue view` resolves the repo via GH_REPO, no checkout."""
        content = (self.target / ".github" / "workflows" / "validate-pr.yml").read_text()
        # Assert the value is wired to github.repository — not just the key present,
        # and not commented out. A commented line keeps its leading "#" after strip(),
        # so exact-line membership is a real regression guard for PI-210.
        env_lines = {line.strip() for line in content.splitlines()}
        assert "GH_REPO: ${{ github.repository }}" in env_lines

    def test_board_automation_workflow_created(self):
        assert (self.target / ".github" / "workflows" / "board-automation.yml").is_file()

    def test_board_automation_tolerates_personal_accounts(self):
        """PI-207/PI-234: the user+organization project query errors on one path
        (tolerate it so the jq fallback selects whichever applies), and the
        checkout-free job must pin the repo so gh calls work without a remote."""
        content = (self.target / ".github" / "workflows" / "board-automation.yml").read_text()
        lines = content.splitlines()
        # Target the specific PROJECT_DATA assignment instead of matching the
        # error-suppression substring anywhere in the file (brittle to harmless
        # whitespace/formatting changes): locate the multi-line `gh api graphql`
        # command substitution and capture it through the line that closes it.
        starts = [
            i for i, line in enumerate(lines) if line.lstrip().startswith("PROJECT_DATA=")
        ]
        assert starts, "board-automation.yml must assign PROJECT_DATA from a gh query"
        start = starts[0]
        ends = [i for i, line in enumerate(lines[start:], start) if "|| true" in line]
        assert ends, "the PROJECT_DATA assignment must close with an error-tolerant guard"
        assignment = "\n".join(lines[start : ends[0] + 1])
        # The query must hit the Projects API and tolerate the errors path a
        # personal (user-owned) account produces on the organization(...) branch,
        # so the jq fallback can still select whichever path applies. (PI-207)
        assert "gh api graphql" in assignment
        assert "projectV2" in assignment
        assert "2>/dev/null" in assignment
        assert "|| true" in assignment
        assert "GH_REPO:" in content

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

    def test_ci_syncs_dev_dependency_group(self):
        """PI-209: align the CI dev install with `uv add --dev` (PEP 735 groups)."""
        content = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert "uv sync --group dev" in content
        assert "uv sync --extra dev" not in content

    def test_ci_does_not_hardcode_python_version(self):
        """PI-208: a pinned Python version drifts below requires-python; let uv
        resolve the project's interpreter from .python-version/requires-python.

        Version-agnostic (Copilot review): guards against *any* hardcoded pin,
        not just 3.12, so reintroducing 3.13 or `uv python install <x>` also
        fails. A version matrix (list or ${{ matrix.* }} reference) stays
        allowed — neither matches a bare scalar literal.
        """
        import re

        content = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        # No `uv python install <version>` for any version.
        assert not re.search(r"uv python install \d", content), (
            "CI must not run `uv python install <version>` (PI-208)"
        )
        # No literal `python-version:` scalar pin for any version.
        assert not re.search(r"""python-version:\s*["']?\d""", content), (
            "CI must not hard-pin python-version to a literal (PI-208)"
        )

    def test_pull_request_template_created(self):
        assert (self.target / ".github" / "pull_request_template.md").is_file()

    def test_copilot_instructions_created(self):
        f = self.target / ".github" / "copilot-instructions.md"
        assert f.is_file()
        content = f.read_text()
        assert "GitHub Projects" in content
        assert "AGENTS.md" in content
        assert "<issue_type>/<project_abbr>-<issue_number>-<slug>" in content
        assert "type(PROJECT-123): description" in content
        assert "[#N][type] description" not in content
        assert "PR title must start with" not in content
        # Review cycle protocol moved to github_workflow skill — file now points to it
        assert "github_workflow" in content

    def test_gemini_md_created(self):
        f = self.target / "GEMINI.md"
        assert f.is_file()
        content = f.read_text()
        assert "AGENTS.md" in content
        assert "source of truth" in content
        assert "GitHub Projects" not in content
        assert "[PROJECT-123][type] description" not in content

    def test_monitor_pr_can_merge_when_clean(self):
        script = self.target / ".claude" / "scripts" / "monitor_pr.sh"
        assert script.is_file()
        content = script.read_text()
        assert "--merge" in content
        assert "gh pr merge" in content
        assert "gh pr checks" in content
        assert "--json" in content  # uses json polling, not --watch, to suppress noise

    def test_monitor_pr_ci_wait_is_bounded(self):
        """PI-186: the CI-wait loop must time out and fail closed, not hang
        forever on a required check that never registers."""
        content = (self.target / ".claude" / "scripts" / "monitor_pr.sh").read_text()
        assert "CI_TIMEOUT=" in content, "CI_TIMEOUT must be assigned a value"
        # Assert the real bounding logic, not just the variable names — the loop
        # must compare elapsed vs timeout and increment elapsed, so the test fails
        # if the guard is dropped while the declarations linger (PI-186 review).
        assert '[ "$CI_ELAPSED" -ge "$CI_TIMEOUT" ]' in content, "missing timeout guard"
        assert "CI_ELAPSED=$((CI_ELAPSED +" in content, "missing elapsed increment"
        assert "--delete-branch" in content
        assert "reviewDecision" in content
        assert "Waiting for reviewer" in content
        assert "MAX_REVIEW_CYCLES=2" in content
        assert "REVIEW_TIMEOUT=360" in content
        assert "--no-review" in content

    def test_finish_pr_wraps_push_ready_monitor_flow(self):
        # finish_pr.sh is a shim; the chain logic lives in dag_workflow.py.
        script = self.target / ".claude" / "scripts" / "finish_pr.sh"
        assert script.is_file()
        assert script.stat().st_mode & 0o111, "finish_pr.sh must be executable"
        shim = script.read_text()
        assert "dag_workflow.py" in shim and "finish" in shim
        dag = (self.target / ".claude" / "hooks" / "dag_workflow.py").read_text()
        assert "monitor_pr.sh" in dag
        assert "cmd_push" in dag and "cmd_promote" in dag
        assert "--review-cycle" in dag

    def test_create_nojira_pr_wraps_branch_push_pr_flow(self):
        script = self.target / ".claude" / "scripts" / "create_nojira_pr.sh"
        assert script.is_file()
        assert script.stat().st_mode & 0o111, "create_nojira_pr.sh must be executable"
        shim = script.read_text()
        assert "dag_workflow.py" in shim and "create-pr-nojira" in shim
        dag = (self.target / ".claude" / "hooks" / "dag_workflow.py").read_text()
        # ADR-006: no-issue PRs use conventional title without a scope
        assert 'pr_title = f"{type_}: {title}"' in dag
        assert "pr_create" in dag or 'pr", "create"' in dag
        assert "--draft" in dag

    def test_validate_pr_enforces_project_key_title_format(self):
        """PR title must match type(PROJECT-123): (canonical) or legacy bracket format."""
        content = (self.target / ".github" / "workflows" / "validate-pr.yml").read_text()
        # Canonical Conventional Commits regex and legacy transition regex (ADR-006)
        assert "NEW_FORMAT=" in content and "LEGACY_FORMAT=" in content
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
        """Pre-push hook blocks main/master pushes and gates branch naming (ADR-007)."""
        hook_path = self.target / ".github" / "hooks" / "pre-push"
        assert hook_path.is_file()
        content = hook_path.read_text()
        assert '"main"' in content and '"master"' in content
        assert "ERROR" in content or "not allowed" in content
        assert "<issue_type>/<project_abbr>-<issue_number>-<slug>" in content
        # Branch gate uses the same rule as dag_workflow.py's _BRANCH_RE
        assert "(feat|fix|chore|docs|test)/" in content

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
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "validate-pr.yml"
    ).read_text()
    assert "[A-Z]" in content  # generic project key pattern
    assert "nojira" in content
    assert "feat|fix|chore|docs|test" in content
