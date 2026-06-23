from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


class TestScaffoldObsidianOnly:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = fallback_preset()
        variables = fallback_variables(memory_stack="obsidian-only")
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

    def test_skills_created(self):
        skills = self.target / ".claude" / "skills"
        assert (skills / "status" / "SKILL.md").is_file()
        assert (skills / "review" / "SKILL.md").is_file()
        assert (skills / "save_memory" / "SKILL.md").is_file()
        assert (skills / "plan" / "SKILL.md").is_file()  # SKILL.md.tmpl rendered to SKILL.md
        assert (skills / "request_review" / "SKILL.md").is_file()

    def test_agents_dir_exists(self):
        agents = self.target / ".claude" / "agents"
        assert agents.is_dir()
        assert (agents / "README.md").is_file()
        # No example agent files should exist
        assert not (agents / "reviewer.md").exists()
        assert not (agents / "researcher.md").exists()

    def test_skill_created(self):
        skill = self.target / ".claude" / "skills" / "session_summary" / "SKILL.md"
        assert skill.is_file()
        content = skill.read_text()
        assert "session_summary" in content

    def test_post_edit_lint_hook(self):
        hook = self.target / ".claude" / "hooks" / "post_edit_lint.sh"
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
        hook = self.target / ".claude" / "hooks" / "pre_commit_gate.sh"
        assert hook.is_file()
        assert hook.stat().st_mode & 0o111

    def test_pre_commit_gate_quotes_staged_file_paths(self):
        content = (self.target / ".claude" / "hooks" / "pre_commit_gate.sh").read_text()
        # PI-360: staged lists are built with a portable read loop (bash 3.2 has
        # no mapfile), and the expanded arrays stay quoted to handle spaces.
        assert "STAGED_PY+=(" in content
        assert '"${STAGED_PY[@]}"' in content
        assert "STAGED_JS+=(" in content
        assert '"${STAGED_JS[@]}"' in content

    def test_legacy_safety_hooks_not_scaffolded(self):
        """ADR-007: secret-guard.py / bash_safety_guard.sh replaced by
        the security-guidance plugin and git-level enforcement."""
        hooks = self.target / ".claude" / "hooks"
        assert not (hooks / "bash_safety_guard.sh").exists()
        assert not (hooks / "secret-guard.py").exists()

    def test_post_edit_lint_outputs_additional_context(self):
        content = (self.target / ".claude" / "hooks" / "post_edit_lint.sh").read_text()
        assert "additionalContext" in content
        assert "ruff format" in content

    def test_start_task_skill_exists(self):
        skill = self.target / ".claude" / "skills" / "start_task" / "SKILL.md"
        assert skill.is_file()
        assert "gh issue" in skill.read_text()

    def test_create_issue_script_created(self):
        assert (self.target / ".claude" / "scripts" / "create_issue.sh").is_file()

    def test_start_issue_script_created(self):
        assert (self.target / ".claude" / "scripts" / "start_issue.sh").is_file()

    def test_promote_review_script_created(self):
        assert (self.target / ".claude" / "scripts" / "promote_review.sh").is_file()

    def test_push_branch_script_created(self):
        assert (self.target / ".claude" / "scripts" / "push_branch.sh").is_file()

    def test_lifecycle_scripts_are_executable(self):
        for name in (
            "create_issue.sh",
            "create_nojira_pr.sh",
            "start_issue.sh",
            "promote_review.sh",
            "install_hooks.sh",
            "push_branch.sh",
        ):
            path = self.target / ".claude" / "scripts" / name
            assert path.stat().st_mode & 0o111, f"{name} must be executable"

    def test_monitor_pr_sh_has_merge_flag(self):
        content = (self.target / ".claude" / "scripts" / "monitor_pr.sh").read_text()
        assert "--merge" in content
        assert "gh pr checks" in content
        assert "--json" in content  # suppresses per-refresh noise; only prints failures
        assert "--yes" not in content
        assert "GH_PROMPT_DISABLED=1" in content

    def test_push_branch_sh_verifies_remote_sha(self):
        # push_branch.sh is a thin shim that delegates to dag_workflow.py.
        # The SHA-verification logic lives in the Python module.
        shim = (self.target / ".claude" / "scripts" / "push_branch.sh").read_text()
        assert "dag_workflow.py" in shim
        # PI-361: shim execs the interpreter via the _py.sh resolver.
        assert "_py.sh" in shim
        assert "python3" not in shim
        dag = (self.target / ".claude" / "hooks" / "dag_workflow.py").read_text()
        assert "ls-remote" in dag
        assert "expected_sha" in dag
        assert "max_retries" in dag

    def test_start_issue_sh_uses_project_key_branch_format(self):
        content = (self.target / ".claude" / "scripts" / "start_issue.sh").read_text()
        assert "derive_project_key" in content
        assert 'ISSUE_REF="${PROJECT_KEY}-${ISSUE_NUMBER}"' in content
        assert 'BRANCH="${TYPE}/${PREFIX}${SLUG}"' in content
        assert "<issue_type>/<project_abbr>-<issue_number>-<kebab-slug>" in content

    def test_start_issue_sh_handles_empty_slug(self):
        """PI-206: a non-alphanumeric title must not yield a slug-less branch
        like `feat/PI-42-` that gets pushed before validation rejects it."""
        content = (self.target / ".claude" / "scripts" / "start_issue.sh").read_text()
        guard_idx = content.find('-z "$SLUG"')
        branch_idx = content.find('BRANCH="${TYPE}/${PREFIX}${SLUG}"')
        assert guard_idx != -1, "empty-slug fallback missing"
        assert guard_idx < branch_idx, "empty-slug fallback must precede the branch name"

    def test_start_issue_sh_widens_short_project_key(self):
        """#432: a single-word repo name yields a 1-char initials key that the
        branch regex accepts but the commit-msg hook (>=2 chars) then rejects on
        every commit. The script must widen/guard the key to a valid shape
        before it becomes part of ISSUE_REF."""
        content = (self.target / ".claude" / "scripts" / "start_issue.sh").read_text()
        assert '"${#PROJECT_KEY}" -lt 2' in content, "short-key widening missing"
        guard_idx = content.find("^[A-Z][A-Z0-9]{1,9}$")
        ref_idx = content.find('ISSUE_REF="${PROJECT_KEY}-${ISSUE_NUMBER}"')
        assert guard_idx != -1, "shared key-shape guard missing"
        assert guard_idx < ref_idx, "key guard must precede ISSUE_REF"

    def test_start_issue_sh_seeds_empty_commit_before_pr(self):
        """#433: a freshly-created branch has no commits, so `gh pr create`
        fails with 'No commits between main and <branch>'. The script must seed
        a commit before opening the draft PR it promises.

        #446: the seed must be index-isolated (built via commit-tree from HEAD's
        own tree), never a plain `git commit --allow-empty`, which would also
        commit whatever the user happens to have staged."""
        content = (self.target / ".claude" / "scripts" / "start_issue.sh").read_text()
        seed_idx = content.find("git commit-tree")
        pr_idx = content.find("gh pr create")
        assert seed_idx != -1, "index-isolated commit-tree seed missing"
        assert seed_idx < pr_idx, "seed must precede gh pr create"
        # A plain --allow-empty would capture staged work — it must not be
        # invoked (a comment may still reference it to explain the choice).
        command_lines = [
            ln for ln in content.splitlines() if not ln.lstrip().startswith("#")
        ]
        assert not any("git commit --allow-empty" in ln for ln in command_lines), (
            "seed must not use `git commit --allow-empty` (captures staged work)"
        )

    def test_project_init_md_has_script_commands(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "create_issue.sh" in content
        assert "create_nojira_pr.sh" in content
        assert "start_issue.sh" in content
        assert "promote_review.sh" in content

    def test_project_init_md_uses_commit_message_format_hook_accepts(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert 'git commit -m "type(<KEY>-<n>): message"' in content
        assert "[#n][type]" not in content

    def test_start_task_skill_delegates_to_scripts(self):
        content = (self.target / ".claude" / "skills" / "start_task" / "SKILL.md").read_text()
        assert "create_issue.sh" in content
        assert "start_issue.sh" in content

    def test_docs_layer_exists(self):
        """PI-27: .claude/docs/ scaffold with ADRs and guides."""
        docs = self.target / ".claude" / "docs"
        assert (docs / "README.md").is_file()
        assert (docs / "adr" / "adr-001-memory-stack.md").is_file()
        assert (docs / "adr" / "adr-002-mcp-choices.md").is_file()
        assert (docs / "development" / "conventions.md").is_file()
        assert (docs / "development" / "testing.md").is_file()
        assert (docs / "guides" / "using-memory.md").is_file()
        # PI-317 (epic #316): the env/deploy decision guide ships with every scaffold
        # and states the single-trunk + deploy-time-environments model.
        env_guide = docs / "guides" / "environments.md"
        assert env_guide.is_file()
        env_text = env_guide.read_text()
        assert "single-trunk" in env_text
        assert "deploy-time concern" in env_text
        # PI-135: per-developer git hygiene lives in docs, not as scaffolder features
        onboarding = docs / "guides" / "developer-onboarding.md"
        assert onboarding.is_file()
        content = onboarding.read_text()
        assert "core.excludesFile" in content
        assert "Settings Sync" in content

    def test_plan_skill_is_tdd_first(self):
        plan = self.target / ".claude" / "skills" / "plan" / "SKILL.md"
        content = plan.read_text()
        assert "write tests first" in content.lower()

    def test_project_init_md_has_tdd_instruction(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "test" in content.lower() and "first" in content.lower()

    def test_project_init_md_has_github_instruction(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "GitHub" in content

    def test_project_init_md_has_coding_standards(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "premature abstraction" in content.lower() or "no premature" in content.lower()

    def test_agents_md_has_tdd_rule(self):
        content = (self.target / "AGENTS.md").read_text()
        assert "TDD" in content or "test" in content.lower()

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
        skill = self.target / ".claude" / "skills" / "add_hook" / "SKILL.md"
        assert skill.is_file()
        content = skill.read_text()
        assert "settings.json" in content
        assert "PreToolUse" in content

    def test_add_command_skill_exists(self):
        skill = self.target / ".claude" / "skills" / "add_command" / "SKILL.md"
        assert skill.is_file()
        assert "$ARGUMENTS" in skill.read_text()

    def test_settings_json_has_autocompact(self):
        import json
        settings = self.target / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        assert data.get("env", {}).get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE") == "70"


class TestIdempotency:
    def test_preserves_user_memory_files(self, tmp_target: Path):
        preset = fallback_preset()
        variables = fallback_variables()

        scaffold(tmp_target, preset, variables)

        # Simulate user adding a custom memory file.
        custom = tmp_target / ".claude" / "memory" / "my_note.md"
        custom.write_text("user content")

        # Re-scaffold.
        scaffold(tmp_target, preset, variables)

        assert custom.read_text() == "user content"

    def test_preserves_user_vault_files(self, tmp_target: Path):
        preset = fallback_preset()
        variables = fallback_variables()

        scaffold(tmp_target, preset, variables)

        custom = tmp_target / ".claude" / "vault" / "decisions" / "adr-001.md"
        custom.write_text("my decision")

        scaffold(tmp_target, preset, variables)

        assert custom.read_text() == "my decision"

    def test_overwrites_config_on_rerun(self, tmp_target: Path):
        preset = fallback_preset()
        variables = fallback_variables(project_name="first")
        scaffold(tmp_target, preset, variables)

        variables2 = fallback_variables(project_name="second")
        scaffold(tmp_target, preset, variables2)

        content = (tmp_target / ".claude" / "config.yaml").read_text()
        assert "second" in content
        assert "first" not in content
