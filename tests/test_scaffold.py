"""Tests for the scaffolding engine and CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import list_presets, load_preset, scaffold


@pytest.fixture
def tmp_target(tmp_path: Path) -> Path:
    return tmp_path / "project"


def _make_variables(**overrides: str) -> dict[str, str]:
    defaults = {
        "project_name": "my-project",
        "project_description": "A test project",
        "created_date": "2026-01-01",
        "project_init_version": "0.1.0",
        "language": "python",
        "memory_stack": "obsidian-only",
        "installed_mcps": "none",
        "installed_mcps_yaml": "[]",
        "python_linter": "ruff",
        "test_framework": "pytest",
        "python": "true",
        "lightrag": "",
        "obsidian": "true",
    }
    defaults.update(overrides)
    return defaults


class TestListPresets:
    def test_returns_both_presets(self):
        presets = list_presets()
        names = {p["name"] for p in presets}
        assert "obsidian-only" in names
        assert "obsidian-lightrag" in names

    def test_presets_have_required_keys(self):
        for p in list_presets():
            assert "name" in p
            assert "description" in p
            assert "layers" in p


class TestLoadPreset:
    def test_load_known_preset(self):
        p = load_preset("obsidian-only")
        assert p["name"] == "obsidian-only"
        assert "base" in p["layers"]

    def test_load_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            load_preset("nonexistent")


class TestScaffoldObsidianOnly:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        variables = _make_variables(memory_stack="obsidian-only", lightrag="")
        self.created = scaffold(tmp_target, preset, variables)

    def test_creates_claude_dir(self):
        assert (self.target / ".claude").is_dir()

    def test_creates_claude_md(self):
        assert (self.target / "CLAUDE.md").is_file()

    def test_creates_agents_md(self):
        assert (self.target / "AGENTS.md").is_file()

    def test_creates_gitignore(self):
        assert (self.target / ".gitignore").is_file()

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

    def test_no_lightrag_files(self):
        assert not (self.target / ".claude" / "scripts" / "ingest_sessions.py").exists()
        assert not (self.target / ".claude" / "scripts" / "query_memory.py").exists()

    def test_lightrag_conditional_excluded(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "LightRAG" not in content

    def test_python_conditional_included(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "uv sync" in content


class TestScaffoldLightRAG:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-lightrag")
        variables = _make_variables(
            memory_stack="obsidian-lightrag",
            lightrag="true",
        )
        self.created = scaffold(tmp_target, preset, variables)

    def test_has_lightrag_scripts(self):
        assert (self.target / ".claude" / "scripts" / "ingest_sessions.py").is_file()
        assert (self.target / ".claude" / "scripts" / "query_memory.py").is_file()

    def test_has_lightrag_config(self):
        assert (self.target / ".claude" / "memory" / "lightrag.yaml").is_file()

    def test_lightrag_conditional_included(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "LightRAG" in content

    def test_settings_json_has_stop_hook(self):
        import json

        settings = self.target / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        assert "Stop" in data["hooks"]

    def test_more_files_than_obsidian_only(self):
        preset_small = load_preset("obsidian-only")
        variables = _make_variables(lightrag="")
        small = scaffold(self.target.parent / "small", preset_small, variables)
        assert len(self.created) > len(small)


class TestIdempotency:
    def test_preserves_user_memory_files(self, tmp_target: Path):
        preset = load_preset("obsidian-only")
        variables = _make_variables()

        scaffold(tmp_target, preset, variables)

        # Simulate user adding a custom memory file.
        custom = tmp_target / ".claude" / "memory" / "my_note.md"
        custom.write_text("user content")

        # Re-scaffold.
        scaffold(tmp_target, preset, variables)

        assert custom.read_text() == "user content"

    def test_preserves_user_vault_files(self, tmp_target: Path):
        preset = load_preset("obsidian-only")
        variables = _make_variables()

        scaffold(tmp_target, preset, variables)

        custom = tmp_target / ".claude" / "vault" / "decisions" / "adr-001.md"
        custom.write_text("my decision")

        scaffold(tmp_target, preset, variables)

        assert custom.read_text() == "my decision"

    def test_overwrites_config_on_rerun(self, tmp_target: Path):
        preset = load_preset("obsidian-only")
        variables = _make_variables(project_name="first")
        scaffold(tmp_target, preset, variables)

        variables2 = _make_variables(project_name="second")
        scaffold(tmp_target, preset, variables2)

        content = (tmp_target / ".claude" / "config.yaml").read_text()
        assert "second" in content
        assert "first" not in content


class TestCLI:
    def test_non_interactive_obsidian_only(self, tmp_target: Path):
        from project_init.__main__ import main

        rc = main([
            str(tmp_target),
            "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "cli-test",
            "--description", "testing cli",
            "--language", "python",
        ])
        assert rc == 0
        assert (tmp_target / ".claude" / "config.yaml").is_file()

    def test_non_interactive_lightrag(self, tmp_target: Path):
        from project_init.__main__ import main

        rc = main([
            str(tmp_target),
            "--non-interactive",
            "--preset", "obsidian-lightrag",
            "--name", "cli-lr",
            "--description", "testing lightrag",
            "--language", "python",
        ])
        assert rc == 0
        assert (tmp_target / ".claude" / "scripts" / "ingest_sessions.py").is_file()

    def test_non_interactive_requires_flags(self):
        from project_init.__main__ import main

        with pytest.raises(SystemExit):
            main(["--non-interactive"])
