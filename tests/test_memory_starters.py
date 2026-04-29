from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


class TestMemoryStarterFiles:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        variables = make_variables(memory_stack="obsidian-only", lightrag="")
        scaffold(tmp_target, preset, variables)

    def test_project_context_exists(self):
        assert (self.target / ".claude" / "memory" / "project_context.md").is_file()

    def test_user_role_exists(self):
        assert (self.target / ".claude" / "memory" / "user_role.md").is_file()

    def test_feedback_conventions_exists(self):
        assert (self.target / ".claude" / "memory" / "feedback_conventions.md").is_file()

    def test_schema_exists(self):
        assert (self.target / ".claude" / "memory" / "SCHEMA.md").is_file()

    def test_schema_defines_all_types(self):
        content = (self.target / ".claude" / "memory" / "SCHEMA.md").read_text()
        for t in ("user", "feedback", "project", "reference"):
            assert t in content

    def test_starter_files_have_valid_frontmatter(self):
        fm_re = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
        for name in ("project_context.md", "user_role.md", "feedback_conventions.md"):
            content = (self.target / ".claude" / "memory" / name).read_text()
            match = fm_re.match(content)
            assert match, f"{name}: no YAML frontmatter"
            fm = match.group(1)
            for field in ("name:", "description:", "type:"):
                assert field in fm, f"{name}: missing {field}"

    def test_starter_types_are_valid(self):
        fm_re = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
        valid_types = {"user", "feedback", "project", "reference"}
        for name in ("project_context.md", "user_role.md", "feedback_conventions.md"):
            content = (self.target / ".claude" / "memory" / name).read_text()
            match = fm_re.match(content)
            type_line = [line for line in match.group(1).splitlines() if line.startswith("type:")]
            assert type_line, f"{name}: no type field"
            type_val = type_line[0].split(":", 1)[1].strip()
            assert type_val in valid_types, f"{name}: invalid type '{type_val}'"

    def test_memory_index_references_all_starters(self):
        content = (self.target / ".claude" / "memory" / "MEMORY.md").read_text()
        assert "project_context.md" in content
        assert "user_role.md" in content
        assert "feedback_conventions.md" in content

    def test_project_context_renders_project_name(self):
        content = (self.target / ".claude" / "memory" / "project_context.md").read_text()
        assert "my-project" in content
        assert "{{project_name}}" not in content

    def test_readme_references_schema(self):
        content = (self.target / ".claude" / "memory" / "README.md").read_text()
        assert "SCHEMA.md" in content


class TestVaultStarterContent:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        variables = make_variables(memory_stack="obsidian-only", lightrag="")
        scaffold(tmp_target, preset, variables)

    def test_log_md_exists(self):
        assert (self.target / ".claude" / "vault" / "log.md").is_file()

    def test_log_md_has_header(self):
        content = (self.target / ".claude" / "vault" / "log.md").read_text()
        assert "Operational Log" in content

    def test_adr_000_exists(self):
        adr = self.target / ".claude" / "vault" / "decisions" / "adr-000-project-setup.md"
        assert adr.is_file()

    def test_adr_000_renders_variables(self):
        content = (
            self.target / ".claude" / "vault" / "decisions" / "adr-000-project-setup.md"
        ).read_text()
        assert "{{created_date}}" not in content
        assert "{{memory_stack}}" not in content
        assert "obsidian-only" in content

    def test_templater_templates_exist(self):
        templates = self.target / ".claude" / "vault" / "templates"
        for name in ("decision.md", "session-note.md", "knowledge-note.md", "design-note.md"):
            assert (templates / name).is_file(), f"missing template: {name}"

    def test_templater_templates_use_tp_syntax(self):
        templates = self.target / ".claude" / "vault" / "templates"
        for name in ("decision.md", "session-note.md", "knowledge-note.md", "design-note.md"):
            content = (templates / name).read_text()
            assert "tp." in content, f"{name}: should use Templater tp. syntax"

    def test_templater_templates_no_scaffold_placeholders(self):
        placeholder_re = re.compile(r"(?<!\$)\{\{[^}]+\}\}")
        templates = self.target / ".claude" / "vault" / "templates"
        for name in ("decision.md", "session-note.md", "knowledge-note.md", "design-note.md"):
            content = (templates / name).read_text()
            matches = placeholder_re.findall(content)
            assert not matches, f"{name}: scaffold placeholders found: {matches}"


class TestObsidianConfig:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        variables = make_variables(memory_stack="obsidian-only", lightrag="")
        scaffold(tmp_target, preset, variables)

    def test_obsidian_dir_exists(self):
        assert (self.target / ".claude" / "vault" / ".obsidian").is_dir()

    def test_app_json_exists(self):
        f = self.target / ".claude" / "vault" / ".obsidian" / "app.json"
        assert f.is_file()
        import json

        data = json.loads(f.read_text())
        assert data["useMarkdownLinks"] is False

    def test_core_plugins_json_exists(self):
        f = self.target / ".claude" / "vault" / ".obsidian" / "core-plugins.json"
        assert f.is_file()
        import json

        plugins = json.loads(f.read_text())
        assert "backlink" in plugins
        assert "graph" in plugins

    def test_community_plugins_json_exists(self):
        f = self.target / ".claude" / "vault" / ".obsidian" / "community-plugins.json"
        assert f.is_file()
        import json

        plugins = json.loads(f.read_text())
        assert "templater-obsidian" in plugins

    def test_obsidian_readme_exists(self):
        assert (self.target / ".claude" / "vault" / ".obsidian" / "README.md").is_file()

    def test_dot_rename_applied_to_obsidian(self):
        assert not (self.target / ".claude" / "vault" / "dot_obsidian").exists()


class TestLintMemoryScript:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        variables = make_variables(memory_stack="obsidian-only", lightrag="")
        scaffold(tmp_target, preset, variables)

    def test_lint_script_exists(self):
        script = self.target / ".claude" / "scripts" / "lint-memory.sh"
        assert script.is_file()

    def test_lint_script_is_executable(self):
        script = self.target / ".claude" / "scripts" / "lint-memory.sh"
        assert script.stat().st_mode & 0o111

    def test_lint_passes_on_clean_scaffold(self):
        # Initialize a git repo so git rev-parse works
        subprocess.run(["git", "init", str(self.target)], capture_output=True, check=True)
        script = self.target / ".claude" / "scripts" / "lint-memory.sh"
        result = subprocess.run(
            ["bash", str(script)],
            cwd=str(self.target),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"lint failed: {result.stderr}"

    def test_lint_fails_on_missing_index_entry(self):
        subprocess.run(["git", "init", str(self.target)], capture_output=True, check=True)
        # Remove a file from the index but keep the file
        index = self.target / ".claude" / "memory" / "MEMORY.md"
        content = index.read_text()
        index.write_text(content.replace("- [User role](user_role.md)", "").strip() + "\n")

        script = self.target / ".claude" / "scripts" / "lint-memory.sh"
        result = subprocess.run(
            ["bash", str(script)],
            cwd=str(self.target),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "user_role.md" in result.stderr

    def test_lint_fails_on_stale_index_reference(self):
        subprocess.run(["git", "init", str(self.target)], capture_output=True, check=True)
        # Delete a memory file but leave its index entry
        (self.target / ".claude" / "memory" / "user_role.md").unlink()

        script = self.target / ".claude" / "scripts" / "lint-memory.sh"
        result = subprocess.run(
            ["bash", str(script)],
            cwd=str(self.target),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "user_role.md" in result.stderr


class TestSessionEndUpdates:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        variables = make_variables(memory_stack="obsidian-only", lightrag="")
        scaffold(tmp_target, preset, variables)

    def test_session_end_appends_to_log(self):
        content = (self.target / ".claude" / "hooks" / "session-end.sh").read_text()
        assert "vault/log.md" in content

    def test_session_end_runs_lint(self):
        content = (self.target / ".claude" / "hooks" / "session-end.sh").read_text()
        assert "lint-memory.sh" in content


class TestLightRAGIncremental:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-lightrag")
        variables = make_variables(memory_stack="obsidian-lightrag", lightrag="true")
        scaffold(tmp_target, preset, variables)

    def test_ingest_script_has_full_flag(self):
        content = (self.target / ".claude" / "scripts" / "ingest_sessions.py").read_text()
        assert "--full" in content

    def test_ingest_script_has_hash_tracking(self):
        content = (self.target / ".claude" / "scripts" / "ingest_sessions.py").read_text()
        assert "ingested.json" in content
        assert "sha256" in content

    def test_lightrag_adr_000_has_lightrag_note(self):
        content = (
            self.target / ".claude" / "vault" / "decisions" / "adr-000-project-setup.md"
        ).read_text()
        assert "LightRAG" in content
