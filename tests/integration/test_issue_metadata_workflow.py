from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


class TestIssueMetadataScaffold:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        scaffold(tmp_target, preset, make_variables())

    def test_issue_template_config_disables_blank_issues(self):
        content = (
            self.target / ".github" / "ISSUE_TEMPLATE" / "config.yml"
        ).read_text()
        assert "blank_issues_enabled: false" in content

    def test_issue_forms_have_shared_metadata_fields(self):
        required = [
            "Priority",
            "Area",
            "Size",
            "References",
            "Dependencies",
            "Acceptance criteria",
            "Definition of Ready",
            "Definition of Done",
        ]
        templates = self.target / ".github" / "ISSUE_TEMPLATE"
        for name in ("bug.yml", "feature.yml", "chore.yml", "docs.yml", "test.yml"):
            content = (templates / name).read_text()
            for label in required:
                assert label in content, f"{name} missing {label}"

    def test_issue_validation_workflow_created(self):
        workflow = self.target / ".github" / "workflows" / "issue-validation.yml"
        content = workflow.read_text()
        assert "runs-on: ubuntu-24.04" in content
        assert "status:needs-info" in content
        assert "issues:" in content
        assert "labeled, unlabeled" in content
        assert "priority label" in content
        assert "gh label create \"status:needs-info\"" in content
        assert "unset" in content

    def test_board_automation_syncs_metadata_fields(self):
        content = (
            self.target / ".github" / "workflows" / "board-automation.yml"
        ).read_text()
        assert "PROJECT_TOKEN" in content
        assert "addProjectV2ItemById" in content
        assert "updateProjectV2ItemFieldValue" in content
        assert "Priority" in content
        assert "Area" in content
        assert "Size" in content
        assert "Skipping missing project field" in content
        assert "organization(login: $owner)" in content
        assert "parse_area()" in content
        assert "metadata" in content
        assert "(.items.nodes // [])[]" in content

    def test_validate_pr_checks_issue_readiness(self):
        content = (self.target / ".github" / "workflows" / "validate-pr.yml").read_text()
        assert "status:needs-info" in content
        assert "<type>/<PROJECT>-<issue-number>-<slug>" in content
        assert "Linked issue is closed" in content
        assert "ISSUE_REF_REGEX" in content
        assert "any(.labels[].name" in content

    def test_issue_metadata_docs_created(self):
        doc = self.target / ".claude" / "docs" / "guides" / "issue-metadata.md"
        content = doc.read_text()
        assert "GitHub labels" in content
        assert "markdown body" in content

    def test_setup_github_script_created(self):
        script = self.target / ".claude" / "scripts" / "setup-github.sh"
        content = script.read_text()
        assert "branches/main/protection" in content
        assert "Copilot code review" in content
        assert "Validate PR / Check PR title, branch, and linked issue" in content

    def test_project_init_references_github_setup(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert ".claude/scripts/setup-github.sh" in content


class TestCreateIssueScript:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        scaffold(tmp_target, preset, make_variables())
        self.script = self.target / ".claude" / "scripts" / "create-issue.sh"

    def test_help_documents_metadata_flags(self):
        result = subprocess.run(
            [str(self.script), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        help_text = result.stdout
        for flag in (
            "--priority",
            "--area",
            "--size",
            "--reference",
            "--dependency",
            "--acceptance",
            "--assignee",
            "--milestone",
            "--body-file",
        ):
            assert flag in help_text

    def test_script_generates_metadata_body_sections(self):
        content = self.script.read_text()
        for section in (
            "## Metadata",
            "## References",
            "## Dependencies",
            "## Acceptance criteria",
            "## Definition of Ready",
            "## Definition of Done",
        ):
            assert section in content
        assert "Acceptance criteria are clear enough to verify" in content
        assert "Relevant checks, tests, or manual validation" in content

    def test_script_documents_missing_label_fallback(self):
        content = self.script.read_text()
        assert "label missing" in content.lower() or "missing label" in content.lower()

    def test_script_reports_missing_option_value(self):
        result = subprocess.run(
            [str(self.script), "feat", "Example", "--priority"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "missing value for '--priority'" in result.stderr


class TestCreateIssueSkill:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        scaffold(tmp_target, preset, make_variables())

    def test_create_issue_skill_scaffolded(self):
        skill = self.target / ".claude" / "skills" / "create-issue" / "SKILL.md"
        content = skill.read_text()
        assert "priority" in content.lower()
        assert ".claude/scripts/create-issue.sh" in content
        assert "Definition of Ready/Done defaults" in content

    def test_skill_index_references_create_issue_skill(self):
        content = (self.target / ".claude" / "skills" / "INDEX.md").read_text()
        assert ".claude/skills/create-issue/SKILL.md" in content

    def test_start_task_delegates_issue_creation_to_skill(self):
        content = (
            self.target / ".claude" / "skills" / "start-task" / "SKILL.md"
        ).read_text()
        assert ".claude/skills/create-issue/SKILL.md" in content

    def test_nojira_pr_script_scaffolded(self):
        script = self.target / ".claude" / "scripts" / "create-nojira-pr.sh"
        content = script.read_text()
        assert script.stat().st_mode & 0o111, "create-nojira-pr.sh must be executable"
        assert "[nojira]" in content
        assert "push-branch.sh" in content
        assert "gh pr create" in content


class TestGitHubWorkflowHooks:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        scaffold(tmp_target, preset, make_variables())

    def _run_hook(self, name: str, command: str) -> dict[str, str] | None:
        hook = self.target / ".claude" / "hooks" / name
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        result = subprocess.run(
            [str(hook)],
            input=payload,
            capture_output=True,
            text=True,
            check=True,
            cwd=self.target,
        )
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)

    def test_github_command_guard_blocks_raw_issue_create(self):
        out = self._run_hook("github-command-guard.sh", "gh issue create --title X")
        assert out is not None and out["decision"] == "block"

    def test_github_command_guard_blocks_raw_pr_merge(self):
        out = self._run_hook("github-command-guard.sh", "gh pr merge 42 --squash")
        assert out is not None and out["decision"] == "block"

    def test_github_command_guard_blocks_raw_pr_merge_auto(self):
        out = self._run_hook("github-command-guard.sh", "gh pr merge 42 --auto")
        assert out is not None and out["decision"] == "block"

    def test_github_command_guard_blocks_raw_pr_create(self):
        out = self._run_hook(
            "github-command-guard.sh",
            'gh pr create --title "[PI-42][fix] Example" --body "Closes #42"',
        )
        assert out is not None and out["decision"] == "block"
        assert "create-nojira-pr.sh" in out["reason"]

    def test_github_command_guard_blocks_raw_pr_ready(self):
        out = self._run_hook("github-command-guard.sh", "gh pr ready 42")
        assert out is not None and out["decision"] == "block"

    def test_github_command_guard_blocks_raw_git_push(self):
        out = self._run_hook("github-command-guard.sh", "git push -u origin fix/PI-42-example")
        assert out is not None and out["decision"] == "block"

    def test_github_command_guard_blocks_pr_checks_watch(self):
        out = self._run_hook("github-command-guard.sh", "gh pr checks 42 --watch")
        assert out is not None and out["decision"] == "block"

    def test_github_command_guard_allows_monitor_pr_merge(self):
        out = self._run_hook(
            "github-command-guard.sh",
            ".claude/scripts/monitor-pr.sh 42 --merge",
        )
        assert out is None

    def test_settings_wire_workflow_hooks(self):
        data = json.loads((self.target / ".claude" / "settings.json").read_text())
        pre_commands = [
            hook["command"]
            for group in data["hooks"]["PreToolUse"]
            for hook in group["hooks"]
        ]
        assert any("github-command-guard.sh" in command for command in pre_commands)
        assert "UserPromptSubmit" in data["hooks"]

    def test_monitor_pr_queries_review_decision_directly(self):
        content = (self.target / ".claude" / "scripts" / "monitor-pr.sh").read_text()
        assert "reviewDecision" in content
        assert "_get_review_decision" in content
        assert "Waiting for reviewer" in content
        assert "could not fetch reviewDecision" in content
        assert "MAX_REVIEW_CYCLES=1" in content
        assert "REVIEW_TIMEOUT=360" in content
        assert "skipping reviewer wait" in content
        assert "_run_gh" in content
        assert "ERROR: admin merge failed" in content

    def test_github_workflow_skill_documents_nonzero_monitor_exit(self):
        content = (
            self.target / ".claude" / "skills" / "github-workflow" / "SKILL.md"
        ).read_text()
        assert "exits **1** for CI or merge failures" in content
        assert "Do not report a PR as merged unless the script exits 0" in content

    def test_monitor_pr_exits_nonzero_when_merge_fails(self, tmp_path: Path):
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        fake_gh = fake_bin / "gh"
        fake_gh.write_text(
            """#!/usr/bin/env bash
if [ "$1 $2" = "pr checks" ]; then
  echo '[]'
  exit 0
fi
if [ "$1 $2" = "pr view" ]; then
  case "$*" in
    *reviewDecision*) echo 'APPROVED'; exit 0 ;;
    *mergeStateStatus*) echo 'CLEAN'; exit 0 ;;
    *url*) echo 'https://example.invalid/pr/42'; exit 0 ;;
  esac
fi
if [ "$1 $2" = "pr merge" ]; then
  echo 'merge failed from fake gh' >&2
  exit 7
fi
exit 2
""",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)

        script = self.target / ".claude" / "scripts" / "monitor-pr.sh"
        env = {"PATH": f"{fake_bin}:{os.environ['PATH']}"}
        result = subprocess.run(
            [str(script), "42", "--merge"],
            capture_output=True,
            text=True,
            cwd=self.target,
            env=env,
        )

        assert result.returncode == 1
        assert "merge failed from fake gh" in result.stdout
        assert "ERROR: merge failed for PR #42" in result.stderr
        assert "Merged PR #42" not in result.stdout

    def test_workflow_state_reminder_reads_prompt_stdin(self):
        hook = self.target / ".claude" / "hooks" / "workflow-state-reminder.sh"
        payload = json.dumps({"prompt": "please finish this PR"})
        result = subprocess.run(
            [str(hook)],
            input=payload,
            capture_output=True,
            text=True,
            check=True,
            cwd=self.target,
        )
        out = json.loads(result.stdout)
        assert "additionalContext" in out
