from __future__ import annotations

import json
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

    def test_validate_pr_checks_issue_readiness(self):
        content = (self.target / ".github" / "workflows" / "validate-pr.yml").read_text()
        assert "status:needs-info" in content
        assert "<type>/<PROJECT>-<issue-number>-<slug>" in content
        assert "Linked issue is closed" in content

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

    def test_script_documents_missing_label_fallback(self):
        content = self.script.read_text()
        assert "label missing" in content.lower() or "missing label" in content.lower()


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

    def test_skill_index_references_create_issue_skill(self):
        content = (self.target / ".claude" / "skills" / "INDEX.md").read_text()
        assert ".claude/skills/create-issue/SKILL.md" in content

    def test_start_task_delegates_issue_creation_to_skill(self):
        content = (
            self.target / ".claude" / "skills" / "start-task" / "SKILL.md"
        ).read_text()
        assert ".claude/skills/create-issue/SKILL.md" in content


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
