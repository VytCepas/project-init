from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


class TestScaffoldObsidianOnly:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        variables = make_variables(memory_stack="obsidian-only", lightrag="")
        self.created = scaffold(tmp_target, preset, variables)

    def test_creates_claude_dir(self):
        assert (self.target / ".claude").is_dir()

    def test_creates_claude_md(self):
        assert (self.target / "CLAUDE.md").is_file()

    def test_creates_agents_md(self):
        assert (self.target / "AGENTS.md").is_file()

    def test_creates_gitignore(self):
        assert (self.target / ".gitignore").is_file()

    def test_gitignore_excludes_local_agent_state(self):
        content = (self.target / ".gitignore").read_text()
        assert ".codex" in content
        assert ".claude/scheduled_tasks.lock" in content
        assert ".claude/settings.local.json" in content

    def test_dot_rename_applied(self):
        # dot_claude/ should become .claude/, no dot_claude/ should exist.
        assert not (self.target / "dot_claude").exists()

    def test_tmpl_extension_stripped(self):
        assert (self.target / ".claude" / "config.yaml").is_file()
        assert not (self.target / ".claude" / "config.yaml.tmpl").exists()

    def test_variables_rendered_in_config(self):
        content = (self.target / ".claude" / "config.yaml").read_text()
        assert "my-project" in content
        assert "{{project_name}}" not in content

    def test_session_end_hook_exists(self):
        hook = self.target / ".claude" / "hooks" / "session-end.sh"
        assert hook.is_file()

    def test_slash_commands_created(self):
        cmds = self.target / ".claude" / "commands"
        assert (cmds / "status.md").is_file()
        assert (cmds / "review.md").is_file()
        assert (cmds / "save-memory.md").is_file()
        assert (cmds / "plan.md").is_file()

    def test_agents_created(self):
        agents = self.target / ".claude" / "agents"
        assert (agents / "reviewer.md").is_file()
        assert (agents / "researcher.md").is_file()

    def test_skill_created(self):
        skill = self.target / ".claude" / "skills" / "session-summary" / "SKILL.md"
        assert skill.is_file()
        content = skill.read_text()
        assert "session-summary" in content

    def test_post_edit_lint_hook(self):
        hook = self.target / ".claude" / "hooks" / "post-edit-lint.sh"
        assert hook.is_file()
        assert hook.stat().st_mode & 0o111  # executable

    def test_settings_json_has_hooks(self):
        import json

        settings = self.target / ".claude" / "settings.json"
        assert settings.is_file()
        data = json.loads(settings.read_text())
        assert "hooks" in data

    def test_settings_json_has_pretooluse_bash(self):
        import json

        data = json.loads((self.target / ".claude" / "settings.json").read_text())
        matchers = [g["matcher"] for g in data["hooks"].get("PreToolUse", [])]
        assert any("Bash" in m for m in matchers)

    def test_settings_json_post_edit_includes_multiedit(self):
        import json

        data = json.loads((self.target / ".claude" / "settings.json").read_text())
        matchers = [g["matcher"] for g in data["hooks"].get("PostToolUse", [])]
        assert any("MultiEdit" in m for m in matchers)

    def test_pre_commit_gate_hook_exists(self):
        hook = self.target / ".claude" / "hooks" / "pre-commit-gate.sh"
        assert hook.is_file()
        assert hook.stat().st_mode & 0o111

    def test_bash_safety_guard_hook_exists(self):
        hook = self.target / ".claude" / "hooks" / "bash-safety-guard.sh"
        assert hook.is_file()
        assert hook.stat().st_mode & 0o111

    def test_post_edit_lint_outputs_additional_context(self):
        content = (self.target / ".claude" / "hooks" / "post-edit-lint.sh").read_text()
        assert "additionalContext" in content
        assert "ruff format" in content

    def test_start_task_skill_exists(self):
        skill = self.target / ".claude" / "skills" / "start-task" / "SKILL.md"
        assert skill.is_file()
        assert "gh issue" in skill.read_text()

    def test_create_issue_script_created(self):
        assert (self.target / ".claude" / "scripts" / "create-issue.sh").is_file()

    def test_start_issue_script_created(self):
        assert (self.target / ".claude" / "scripts" / "start-issue.sh").is_file()

    def test_promote_review_script_created(self):
        assert (self.target / ".claude" / "scripts" / "promote-review.sh").is_file()

    def test_push_branch_script_created(self):
        assert (self.target / ".claude" / "scripts" / "push-branch.sh").is_file()

    def test_lifecycle_scripts_are_executable(self):
        for name in (
            "create-issue.sh",
            "create-nojira-pr.sh",
            "start-issue.sh",
            "promote-review.sh",
            "install-hooks.sh",
            "push-branch.sh",
        ):
            path = self.target / ".claude" / "scripts" / name
            assert path.stat().st_mode & 0o111, f"{name} must be executable"

    def test_monitor_pr_sh_has_merge_flag(self):
        content = (self.target / ".claude" / "scripts" / "monitor-pr.sh").read_text()
        assert "--merge" in content
        assert "gh pr checks" in content
        assert "--json" in content  # suppresses per-refresh noise; only prints failures
        assert "--yes" not in content
        assert "GH_PROMPT_DISABLED=1" in content

    def test_push_branch_sh_verifies_remote_sha(self):
        content = (self.target / ".claude" / "scripts" / "push-branch.sh").read_text()
        assert "git ls-remote" in content
        assert "EXPECTED_SHA" in content
        assert "MAX_RETRIES" in content

    def test_start_issue_sh_uses_project_key_branch_format(self):
        content = (self.target / ".claude" / "scripts" / "start-issue.sh").read_text()
        assert "derive_project_key" in content
        assert 'ISSUE_REF="${PROJECT_KEY}-${ISSUE_NUMBER}"' in content
        assert 'BRANCH="${TYPE}/${PREFIX}${SLUG}"' in content
        assert "<issue_type>/<project_abbr>-<issue_number>-<kebab-slug>" in content

    def test_project_init_md_has_script_commands(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "create-issue.sh" in content
        assert "create-nojira-pr.sh" in content
        assert "start-issue.sh" in content
        assert "promote-review.sh" in content

    def test_start_task_skill_delegates_to_scripts(self):
        content = (self.target / ".claude" / "skills" / "start-task" / "SKILL.md").read_text()
        assert "create-issue.sh" in content
        assert "start-issue.sh" in content

    def test_docs_layer_exists(self):
        """PI-27: .claude/docs/ scaffold with ADRs and guides."""
        docs = self.target / ".claude" / "docs"
        assert (docs / "README.md").is_file()
        assert (docs / "adr" / "adr-001-memory-stack.md").is_file()
        assert (docs / "adr" / "adr-002-mcp-choices.md").is_file()
        assert (docs / "development" / "conventions.md").is_file()
        assert (docs / "development" / "testing.md").is_file()
        assert (docs / "guides" / "using-memory.md").is_file()

    def test_plan_command_is_tdd_first(self):
        plan = self.target / ".claude" / "commands" / "plan.md"
        content = plan.read_text()
        assert "acceptance test" in content.lower()
        assert "red" in content.lower()

    def test_project_init_md_has_tdd_instruction(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "test" in content.lower() and "first" in content.lower()

    def test_project_init_md_has_github_instruction(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "GitHub" in content

    def test_project_init_md_has_coding_standards(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "premature abstraction" in content.lower() or "no premature" in content.lower()

    def test_claude_md_has_tdd_rule(self):
        content = (self.target / "CLAUDE.md").read_text()
        assert "TDD" in content or "test" in content.lower()

    def test_no_lightrag_files(self):
        assert not (self.target / ".claude" / "scripts" / "ingest_sessions.py").exists()
        assert not (self.target / ".claude" / "scripts" / "query_memory.py").exists()

    def test_lightrag_rule_excluded(self):
        # LightRAG rule file ships with the lightrag overlay only
        assert not (self.target / ".claude" / "rules" / "lightrag.md").exists()

    def test_python_rule_file_present(self):
        rule = self.target / ".claude" / "rules" / "python.md"
        assert rule.exists()
        content = rule.read_text()
        assert "uv sync" in content
        assert "globs" in content

    def test_all_language_rule_files_present(self):
        rules = self.target / ".claude" / "rules"
        assert (rules / "python.md").exists()
        assert (rules / "node.md").exists()
        assert (rules / "go.md").exists()
        assert (rules / "hooks.md").exists()

    def test_add_hook_skill_exists(self):
        skill = self.target / ".claude" / "skills" / "add-hook" / "SKILL.md"
        assert skill.is_file()
        content = skill.read_text()
        assert "settings.json" in content
        assert "PreToolUse" in content

    def test_add_command_skill_exists(self):
        skill = self.target / ".claude" / "skills" / "add-command" / "SKILL.md"
        assert skill.is_file()
        assert "$ARGUMENTS" in skill.read_text()

    def test_settings_json_has_autocompact(self):
        import json
        settings = self.target / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        assert data.get("env", {}).get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE") == "70"


class TestIdempotency:
    def test_preserves_user_memory_files(self, tmp_target: Path):
        preset = load_preset("obsidian-only")
        variables = make_variables()

        scaffold(tmp_target, preset, variables)

        # Simulate user adding a custom memory file.
        custom = tmp_target / ".claude" / "memory" / "my_note.md"
        custom.write_text("user content")

        # Re-scaffold.
        scaffold(tmp_target, preset, variables)

        assert custom.read_text() == "user content"

    def test_preserves_user_vault_files(self, tmp_target: Path):
        preset = load_preset("obsidian-only")
        variables = make_variables()

        scaffold(tmp_target, preset, variables)

        custom = tmp_target / ".claude" / "vault" / "decisions" / "adr-001.md"
        custom.write_text("my decision")

        scaffold(tmp_target, preset, variables)

        assert custom.read_text() == "my decision"

    def test_overwrites_config_on_rerun(self, tmp_target: Path):
        preset = load_preset("obsidian-only")
        variables = make_variables(project_name="first")
        scaffold(tmp_target, preset, variables)

        variables2 = make_variables(project_name="second")
        scaffold(tmp_target, preset, variables2)

        content = (tmp_target / ".claude" / "config.yaml").read_text()
        assert "second" in content
        assert "first" not in content
