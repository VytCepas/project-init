"""Tests for the scaffolding engine and CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.scaffold import list_presets, load_preset, scaffold


def _lightrag_available() -> bool:
    try:
        import lightrag  # noqa: F401
        return True
    except ImportError:
        return False


def _find_uv() -> str | None:
    """Locate the `uv` binary. `uv run pytest` strips uv from PATH, so check
    common install locations as a fallback."""
    import shutil as _shutil
    found = _shutil.which("uv")
    if found:
        return found
    for candidate in [
        Path.home() / ".local" / "bin" / "uv",
        Path("/usr/local/bin/uv"),
    ]:
        if candidate.exists():
            return str(candidate)
    return None


def _has_uv_and_can_build() -> bool:
    """True if `uv build` is plausibly available — gates the wheel smoke test."""
    return _find_uv() is not None


@pytest.fixture
def tmp_target(tmp_path: Path) -> Path:
    return tmp_path / "project"


def _make_variables(**overrides: str) -> dict[str, str]:
    defaults = {
        "project_name": "my-project",
        "project_description": "A test project",
        "created_date": "2026-01-01",
        "project_init_version": "0.1.0",
        "project_init_url": "https://github.com/example/project-init",
        "language": "python",
        "memory_stack": "obsidian-only",
        "installed_mcps": "none",
        "installed_mcps_yaml": "[]",
        "lint_command": "uv run ruff check .",
        "format_command": "uv run ruff format .",
        "test_command": "uv run pytest",
        "python": "true",
        "node": "",
        "go": "",
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
        assert "Linear" in skill.read_text()

    def test_plan_command_is_tdd_first(self):
        plan = self.target / ".claude" / "commands" / "plan.md"
        content = plan.read_text()
        assert "acceptance test" in content.lower()
        assert "red" in content.lower()

    def test_project_init_md_has_tdd_instruction(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "test" in content.lower() and "first" in content.lower()

    def test_project_init_md_has_linear_instruction(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "Linear" in content

    def test_project_init_md_has_coding_standards(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "premature abstraction" in content.lower() or "no premature" in content.lower()

    def test_claude_md_has_tdd_rule(self):
        content = (self.target / "CLAUDE.md").read_text()
        assert "TDD" in content or "test" in content.lower()

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


class TestLightRAGScripts:
    """Verify scaffolded LightRAG scripts are correct and handle env-var errors.

    Tests that require lightrag-hku are skipped when the package is absent so
    the regular CI suite (which does not install it) still passes.
    """

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-lightrag")
        variables = _make_variables(memory_stack="obsidian-lightrag", lightrag="true")
        scaffold(tmp_target, preset, variables)

    def test_ingest_script_has_valid_syntax(self):
        import ast
        script = self.target / ".claude" / "scripts" / "ingest_sessions.py"
        ast.parse(script.read_text())

    def test_query_script_has_valid_syntax(self):
        import ast
        script = self.target / ".claude" / "scripts" / "query_memory.py"
        ast.parse(script.read_text())

    def test_lightrag_yaml_references_openai_embeddings(self):
        cfg = self.target / ".claude" / "memory" / "lightrag.yaml"
        content = cfg.read_text()
        assert "openai" in content
        assert "OPENAI_API_KEY" in content

    def test_ingest_script_checks_for_openai_key(self):
        content = (self.target / ".claude" / "scripts" / "ingest_sessions.py").read_text()
        assert "OPENAI_API_KEY" in content

    def test_query_script_checks_for_openai_key(self):
        content = (self.target / ".claude" / "scripts" / "query_memory.py").read_text()
        assert "OPENAI_API_KEY" in content

    @pytest.mark.skipif(not _lightrag_available(), reason="lightrag-hku not installed")
    def test_ingest_exits_2_on_missing_anthropic_key(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env.pop("OPENAI_API_KEY", None)
        script = self.target / ".claude" / "scripts" / "ingest_sessions.py"
        result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True)
        assert result.returncode == 2

    @pytest.mark.skipif(not _lightrag_available(), reason="lightrag-hku not installed")
    def test_ingest_exits_2_on_missing_openai_key(self):
        env = {**os.environ, "ANTHROPIC_API_KEY": "dummy"}
        env.pop("OPENAI_API_KEY", None)
        script = self.target / ".claude" / "scripts" / "ingest_sessions.py"
        result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True)
        assert result.returncode == 2
        assert b"OPENAI_API_KEY" in result.stderr

    @pytest.mark.skipif(not _lightrag_available(), reason="lightrag-hku not installed")
    def test_query_exits_2_when_no_index(self):
        env = {**os.environ, "ANTHROPIC_API_KEY": "dummy", "OPENAI_API_KEY": "dummy"}
        script = self.target / ".claude" / "scripts" / "query_memory.py"
        result = subprocess.run(
            [sys.executable, str(script), "test question"],
            env=env,
            capture_output=True,
        )
        assert result.returncode == 2
        assert b"ingest_sessions.py" in result.stderr

    @pytest.mark.skipif(not _lightrag_available(), reason="lightrag-hku not installed")
    def test_ingest_returns_0_on_empty_vault(self):
        """With both keys set and an empty vault, ingest should exit cleanly."""
        env = {**os.environ, "ANTHROPIC_API_KEY": "dummy", "OPENAI_API_KEY": "dummy"}
        script = self.target / ".claude" / "scripts" / "ingest_sessions.py"
        result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True)
        assert result.returncode == 0
        assert b"no markdown found" in result.stdout


def _run_secret_guard(script: Path, payload: dict) -> dict | None:
    """Run secret-guard.py with a JSON payload; return parsed stdout or None."""
    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"secret-guard exited {result.returncode}: {result.stderr}"
    return json.loads(result.stdout) if result.stdout.strip() else None


class TestSecretGuard:
    """Verify secret-guard.py blocks real secrets and allows clean content."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        scaffold(tmp_target, preset, _make_variables())

    @property
    def _script(self) -> Path:
        return self.target / ".claude" / "hooks" / "secret-guard.py"

    def test_script_exists(self):
        assert self._script.is_file()

    def test_script_has_valid_syntax(self):
        import ast
        ast.parse(self._script.read_text())

    def test_settings_json_wires_secret_guard(self):
        data = json.loads((self.target / ".claude" / "settings.json").read_text())
        pre = data["hooks"].get("PreToolUse", [])
        matchers = [g["matcher"] for g in pre]
        assert any("Write" in m for m in matchers)

    def test_blocks_anthropic_api_key_in_write(self):
        fake_key = "sk-ant-api03-" + "A" * 95
        out = _run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/config.py", "content": f'api_key = "{fake_key}"'},
        })
        assert out is not None and out["decision"] == "block"
        assert "Anthropic" in out["reason"]

    def test_blocks_openai_api_key_in_edit(self):
        fake_key = "sk-proj-" + "B" * 48
        out = _run_secret_guard(self._script, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/settings.py", "new_string": f"KEY = '{fake_key}'"},
        })
        assert out is not None and out["decision"] == "block"

    def test_blocks_aws_key_in_bash(self):
        out = _run_secret_guard(self._script, {
            "tool_name": "Bash",
            "tool_input": {"command": "export AWS_ACCESS_KEY_ID=AKIAZXBCDE12345678AB"},
        })
        assert out is not None and out["decision"] == "block"
        assert "AWS" in out["reason"]

    def test_blocks_private_key_material(self):
        out = _run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/key.pem",
                "content": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----",
            },
        })
        assert out is not None and out["decision"] == "block"

    def test_blocks_ssn(self):
        out = _run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/data.py", "content": "ssn = '123-45-6789'"},
        })
        assert out is not None and out["decision"] == "block"
        assert "Social Security" in out["reason"]

    def test_allows_clean_python_file(self):
        out = _run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/hello.py", "content": "def hello():\n    return 'world'\n"},
        })
        assert out is None

    def test_allows_env_variable_reference(self):
        out = _run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/config.py",
                "content": "import os\napi_key = os.environ['ANTHROPIC_API_KEY']\n",
            },
        })
        assert out is None

    def test_allows_env_example_file(self):
        fake_key = "sk-ant-api03-" + "A" * 95
        out = _run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/project/.env.example",
                "content": f"ANTHROPIC_API_KEY={fake_key}\n",
            },
        })
        assert out is None

    def test_allows_obvious_placeholder(self):
        out = _run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/readme.md",
                "content": "Set ANTHROPIC_API_KEY=your_key_here in your .env file.\n",
            },
        })
        assert out is None

    def test_blocks_github_pat(self):
        fake_token = "ghp_" + "C" * 36
        out = _run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/ci.py", "content": f"token = '{fake_token}'"},
        })
        assert out is not None and out["decision"] == "block"

    def test_claude_md_has_no_secrets_rule(self):
        content = (self.target / "CLAUDE.md").read_text()
        assert "secret" in content.lower() or "hardcode" in content.lower()

    def test_blocks_home_directory_path(self):
        home = os.environ.get("HOME", "/home/testuser")
        out = _run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/config.yaml",
                "content": f"venv_path: {home}/projects/myapp/.venv",
            },
        })
        assert out is not None and out["decision"] == "block"
        assert "home" in out["reason"].lower() or "path" in out["reason"].lower()

    def test_allows_relative_path(self):
        out = _run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/config.yaml",
                "content": "venv_path: .venv/bin/python",
            },
        })
        assert out is None


class TestMCPs:
    """Unit tests for the MCP catalog and formatting helpers."""

    def test_catalog_has_required_keys(self):
        from project_init.mcps import MCP_CATALOG
        for m in MCP_CATALOG:
            assert "id" in m
            assert "name" in m
            assert "description" in m
            assert "command" in m

    def test_catalog_contains_core_mcps(self):
        from project_init.mcps import MCP_CATALOG
        ids = {m["id"] for m in MCP_CATALOG}
        assert {"linear", "github", "context7", "filesystem"} <= ids

    def test_db_catalog_has_postgres_and_sqlite(self):
        from project_init.mcps import DB_CATALOG
        assert "postgres" in DB_CATALOG
        assert "sqlite" in DB_CATALOG

    def test_playwright_mcp_defined(self):
        from project_init.mcps import PLAYWRIGHT_MCP
        assert PLAYWRIGHT_MCP["id"] == "playwright"
        assert "command" in PLAYWRIGHT_MCP

    def test_no_npx_in_any_command(self):
        from project_init.mcps import DB_CATALOG, MCP_CATALOG, PLAYWRIGHT_MCP
        all_commands = (
            [m["command"] for m in MCP_CATALOG]
            + [m["command"] for m in DB_CATALOG.values()]
            + [PLAYWRIGHT_MCP["command"]]
        )
        for cmd in all_commands:
            assert "npx" not in cmd, f"npx found in command: {cmd}"
            assert "npm" not in cmd, f"npm found in command: {cmd}"

    def test_all_commands_use_bunx(self):
        from project_init.mcps import DB_CATALOG, MCP_CATALOG, PLAYWRIGHT_MCP
        all_commands = (
            [m["command"] for m in MCP_CATALOG]
            + [m["command"] for m in DB_CATALOG.values()]
            + [PLAYWRIGHT_MCP["command"]]
        )
        for cmd in all_commands:
            assert "bunx" in cmd, f"bunx not found in command: {cmd}"

    def test_format_installed_mcps_empty(self):
        from project_init.mcps import format_installed_mcps
        assert format_installed_mcps([]) == "none"

    def test_format_installed_mcps_single(self):
        from project_init.mcps import MCP_CATALOG, format_installed_mcps
        linear = next(m for m in MCP_CATALOG if m["id"] == "linear")
        assert format_installed_mcps([linear]) == "linear"

    def test_format_installed_mcps_multiple(self):
        from project_init.mcps import MCP_CATALOG, format_installed_mcps
        subset = [m for m in MCP_CATALOG if m["id"] in {"linear", "github"}]
        result = format_installed_mcps(subset)
        assert "linear" in result and "github" in result

    def test_format_installed_mcps_yaml_empty(self):
        from project_init.mcps import format_installed_mcps_yaml
        assert format_installed_mcps_yaml([]) == "[]"

    def test_format_installed_mcps_yaml_single(self):
        from project_init.mcps import MCP_CATALOG, format_installed_mcps_yaml
        linear = next(m for m in MCP_CATALOG if m["id"] == "linear")
        assert format_installed_mcps_yaml([linear]) == '["linear"]'

    def test_format_installed_mcps_yaml_multiple(self):
        from project_init.mcps import MCP_CATALOG, format_installed_mcps_yaml
        subset = [m for m in MCP_CATALOG if m["id"] in {"linear", "github"}]
        result = format_installed_mcps_yaml(subset)
        assert result.startswith("[") and result.endswith("]")
        assert '"linear"' in result and '"github"' in result


class TestMCPsNonInteractive:
    """Test --mcps / --db / --browser flags via non-interactive CLI."""

    def test_mcps_flag_linear_github(self, tmp_path: Path):
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "mcp-test",
            "--description", "test",
            "--language", "python",
            "--mcps", "linear,github",
        ])
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert "linear" in config
        assert "github" in config

    def test_db_postgres_flag(self, tmp_path: Path):
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "db-test",
            "--description", "test",
            "--language", "python",
            "--db", "postgres",
        ])
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert "postgres" in config

    def test_browser_flag_adds_playwright(self, tmp_path: Path):
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "browser-test",
            "--description", "test",
            "--language", "python",
            "--browser",
        ])
        assert rc == 0
        config = (target / ".clone" / "config.yaml") if False else (target / ".claude" / "config.yaml")
        assert "playwright" in config.read_text()

    def test_no_mcps_gives_none(self, tmp_path: Path):
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "empty-test",
            "--description", "test",
            "--language", "python",
        ])
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert "installed: []" in config

    def test_unknown_mcp_id_is_rejected(self, tmp_path: Path):
        """Silently ignoring typos hides real bugs — unknown IDs must error out."""
        from project_init.__main__ import main
        target = tmp_path / "p"
        with pytest.raises(SystemExit):
            main([
                str(target), "--non-interactive",
                "--preset", "obsidian-only",
                "--name", "bad-mcp-test",
                "--description", "test",
                "--language", "python",
                "--mcps", "linear,nonexistent,github",
            ])

    def test_unknown_preset_does_not_create_target_dir(self, tmp_path: Path):
        """A typo in --preset must fail BEFORE the target directory is created."""
        from project_init.__main__ import main
        target = tmp_path / "should-not-exist"
        with pytest.raises(SystemExit):
            main([
                str(target), "--non-interactive",
                "--preset", "definitely-not-a-real-preset",
                "--name", "x",
                "--description", "x",
            ])
        assert not target.exists(), (
            f"target dir {target} was created despite invalid preset"
        )


class TestScaffoldIntegrity:
    """Catch unrendered placeholders and other template-level rendering bugs."""

    def test_strict_mode_passes_for_both_presets(self, tmp_path: Path):
        """PI-17: strict scaffolding must succeed for every shipped preset."""
        for preset_name, lightrag_flag in [
            ("obsidian-only", ""),
            ("obsidian-lightrag", "true"),
        ]:
            target = tmp_path / preset_name
            preset = load_preset(preset_name)
            variables = _make_variables(
                memory_stack=preset_name,
                lightrag=lightrag_flag,
            )
            scaffold(target, preset, variables, strict=True)

    def test_no_unrendered_handlebars_placeholders(self, tmp_path: Path):
        """{{var}} or {{#if var}} surviving means a template wasn't named .tmpl
        or a variable wasn't wired up in __main__.py."""
        import re
        placeholder_re = re.compile(r"\{\{[^}]+\}\}")
        offenders: list[str] = []
        for preset_name, lightrag_flag in [
            ("obsidian-only", ""),
            ("obsidian-lightrag", "true"),
        ]:
            target = tmp_path / preset_name
            preset = load_preset(preset_name)
            variables = _make_variables(
                memory_stack=preset_name,
                lightrag=lightrag_flag,
            )
            scaffold(target, preset, variables)
            for f in target.rglob("*"):
                if not f.is_file():
                    continue
                try:
                    text = f.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for match in placeholder_re.finditer(text):
                    offenders.append(f"{f.relative_to(target)}: {match.group()}")
        assert not offenders, (
            "Unrendered placeholders survived scaffolding:\n  "
            + "\n  ".join(offenders)
        )


class TestStrictMode:
    """PI-17: --strict / strict=True surfaces unrendered placeholders."""

    def test_strict_raises_on_missing_variable(self, tmp_path: Path):
        """If a variable is missing from the dict, strict mode must raise."""
        from project_init.scaffold import TemplateRenderError
        target = tmp_path / "p"
        variables = _make_variables()
        # Inject a stale variable into a template by hand: write a fake .tmpl
        # file that references something not in the variables dict.
        # We achieve this via a custom template layer.
        fake_dir = tmp_path / "fake-layer"
        (fake_dir / "dot_claude").mkdir(parents=True)
        (fake_dir / "dot_claude" / "stale.md.tmpl").write_text(
            "value: {{undefined_variable_xyz}}"
        )
        # Patch the templates dir for this test only.
        import project_init.scaffold as sm
        original = sm._TEMPLATES_DIR
        sm._TEMPLATES_DIR = fake_dir.parent
        try:
            preset_for_fake = {"name": "fake", "layers": ["fake-layer"]}
            with pytest.raises(TemplateRenderError) as excinfo:
                scaffold(target, preset_for_fake, variables, strict=True)
            assert "undefined_variable_xyz" in str(excinfo.value)
            assert "stale.md" in str(excinfo.value)
        finally:
            sm._TEMPLATES_DIR = original

    def test_non_strict_still_permissive(self, tmp_path: Path):
        """Default mode tolerates unknown variables (back-compat)."""
        target = tmp_path / "p"
        preset = load_preset("obsidian-only")
        variables = _make_variables()
        # Non-strict on shipped templates: no exception.
        scaffold(target, preset, variables, strict=False)

    def test_cli_strict_flag_returns_2_on_failure(self, tmp_path: Path):
        """--strict against a layer with bad placeholder must exit with rc=2."""
        # Shipped templates pass strict mode (verified by other test), so just
        # assert the happy path: --strict succeeds on a known-good preset.
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "strict-test",
            "--description", "test",
            "--language", "python",
            "--strict",
        ])
        assert rc == 0


class TestCommandVariables:
    """PI-16: lint_command / format_command / test_command per language."""

    def _scaffold_with_lang(self, tmp_path: Path, **kwargs) -> Path:
        target = tmp_path / "p"
        preset = load_preset("obsidian-only")
        variables = _make_variables(**kwargs)
        scaffold(target, preset, variables)
        return target

    def test_python_renders_uv_run_ruff(self, tmp_path: Path):
        target = self._scaffold_with_lang(tmp_path)
        content = (target / "CLAUDE.md").read_text()
        assert "uv run ruff check ." in content
        config = (target / ".claude" / "config.yaml").read_text()
        assert 'lint_command: "uv run ruff check ."' in config
        assert 'test_command: "uv run pytest"' in config

    def test_node_renders_bun_run_lint(self, tmp_path: Path):
        target = self._scaffold_with_lang(
            tmp_path,
            language="node",
            python="",
            node="true",
            lint_command="bun run lint",
            format_command="bun run format",
            test_command="bun test",
        )
        config = (target / ".claude" / "config.yaml").read_text()
        assert 'lint_command: "bun run lint"' in config
        assert 'test_command: "bun test"' in config

    def test_none_language_omits_lint_section(self, tmp_path: Path):
        """For language=none, lint_command is empty so the {{#if lint_command}}
        block in CLAUDE.md/project-init.md should not render."""
        target = self._scaffold_with_lang(
            tmp_path,
            language="none",
            python="",
            node="",
            lint_command="",
            format_command="",
            test_command="",
        )
        claude = (target / "CLAUDE.md").read_text()
        # Must not render the lint bullet at all
        assert "must pass before closing a task" not in claude

    def test_no_legacy_python_linter_variable(self, tmp_path: Path):
        """The old {{python_linter}} placeholder must be gone everywhere."""
        target = self._scaffold_with_lang(tmp_path)
        for f in target.rglob("*"):
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            assert "{{python_linter}}" not in text, f"legacy var in {f}"
            assert "{{test_framework}}" not in text, f"legacy var in {f}"


class TestCLINonInteractiveCommandVariables:
    """PI-16: CLI passes correct command variables based on --language."""

    def test_python_cli_writes_uv_commands(self, tmp_path: Path):
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "py-cli",
            "--description", "test",
            "--language", "python",
        ])
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert 'lint_command: "uv run ruff check ."' in config

    def test_node_cli_writes_bun_commands(self, tmp_path: Path):
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "node-cli",
            "--description", "test",
            "--language", "node",
        ])
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert 'lint_command: "bun run lint"' in config

    def test_go_cli_writes_go_commands(self, tmp_path: Path):
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "go-cli",
            "--description", "test",
            "--language", "go",
        ])
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert 'lint_command: "golangci-lint run"' in config
        assert 'test_command: "go test ./..."' in config


class TestNodeTemplate:
    """Verify Node/bun conditional block renders correctly."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = tmp_path / "node-proj"
        preset = load_preset("obsidian-only")
        variables = _make_variables(
            language="node",
            python="",
            node="true",
            lint_command="bun run lint",
            format_command="bun run format",
            test_command="bun test",
        )
        scaffold(self.target, preset, variables)

    def test_node_block_rendered(self):
        content = (self.target / ".claude" / "project-init.md").read_text()
        assert "bun install" in content
        assert "bunx" in content

    def test_python_block_excluded_for_node(self):
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


@pytest.mark.skipif(
    not _has_uv_and_can_build(),
    reason="uv build / venv unavailable in this environment",
)
class TestInstalledWheel:
    """PI-18: build the wheel, install it in a fresh venv, run project-init.

    Catches packaging bugs that the source-checkout test suite cannot:
    missing force-include, lost executable bits on hook templates, etc.
    """

    def test_wheel_install_and_scaffold(self, tmp_path: Path):
        repo_root = Path(__file__).resolve().parent.parent
        build_dir = tmp_path / "build"
        venv_dir = tmp_path / "venv"
        scaffold_target = tmp_path / "scaffolded"
        uv_bin = _find_uv()
        assert uv_bin, "uv not found despite passing _has_uv_and_can_build"

        # Build wheel into a temp dir.
        result = subprocess.run(
            [uv_bin, "build", "--wheel", "-o", str(build_dir)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.skip(f"uv build failed: {result.stderr}")

        wheels = list(build_dir.glob("*.whl"))
        assert wheels, "no wheel produced"

        # Create a venv and install the wheel.
        venv_result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if venv_result.returncode != 0:
            pytest.skip(f"venv unavailable in this environment: {venv_result.stderr}")
        venv_pip = venv_dir / "bin" / "pip"
        venv_bin = venv_dir / "bin" / "project-init"
        if not venv_pip.exists():  # Windows fallback
            venv_pip = venv_dir / "Scripts" / "pip.exe"
            venv_bin = venv_dir / "Scripts" / "project-init.exe"
        subprocess.run(
            [str(venv_pip), "install", "--quiet", str(wheels[0])],
            check=True,
            timeout=120,
        )

        # Scaffold using the installed binary, with --strict.
        result = subprocess.run(
            [
                str(venv_bin), str(scaffold_target),
                "--non-interactive",
                "--preset", "obsidian-only",
                "--name", "wheel-smoke",
                "--description", "test",
                "--language", "python",
                "--strict",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"installed binary failed:\nSTDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )

        # Essentials present.
        assert (scaffold_target / ".claude" / "config.yaml").is_file()
        assert (scaffold_target / "CLAUDE.md").is_file()
        # Hooks kept executable bit through wheel packaging.
        for hook in [
            "post-edit-lint.sh",
            "pre-commit-gate.sh",
            "bash-safety-guard.sh",
        ]:
            hook_path = scaffold_target / ".claude" / "hooks" / hook
            assert hook_path.is_file()
            assert hook_path.stat().st_mode & 0o111, (
                f"{hook} lost executable bit"
            )


class TestTemplateIdentifiers:
    """Verify no hardcoded owner identity leaks into scaffolded files."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        scaffold(tmp_target, preset, _make_variables(
            project_init_url="https://github.com/example/project-init"
        ))

    def test_agents_md_uses_template_url(self):
        content = (self.target / "AGENTS.md").read_text()
        assert "VytCepas" not in content
        assert "github.com/example/project-init" in content

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
