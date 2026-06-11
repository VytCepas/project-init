from __future__ import annotations

from pathlib import Path

import pytest


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


class TestCLIGovernanceFlags:
    """PI-145: --license and --owner render governance files."""

    def _run(self, target: Path, *extra: str) -> int:
        from project_init.__main__ import main

        return main([
            str(target),
            "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "gov-cli",
            "--description", "test",
            "--language", "python",
            *extra,
        ])

    def test_license_and_owner_render(self, tmp_path: Path):
        from datetime import date

        target = tmp_path / "p"
        assert self._run(target, "--license", "mit", "--owner", "@acme/core") == 0
        license_text = (target / "LICENSE").read_text()
        assert "MIT License" in license_text
        assert f"{date.today().year} @acme/core" in license_text
        assert "*       @acme/core" in (target / ".github" / "CODEOWNERS").read_text()

    def test_no_license_flag_renders_no_file(self, tmp_path: Path):
        target = tmp_path / "p"
        assert self._run(target) == 0
        assert not (target / "LICENSE").exists()
        assert (target / "CONTRIBUTING.md").exists()

    def test_invalid_license_is_rejected(self, tmp_path: Path):
        with pytest.raises(SystemExit):
            self._run(tmp_path / "p", "--license", "gpl-3.0")

    def test_license_holder_falls_back_to_project_name(self, tmp_path: Path):
        target = tmp_path / "p"
        assert self._run(target, "--license", "proprietary") == 0
        assert "gov-cli. All rights reserved." in (target / "LICENSE").read_text()


class TestCLIOverlayFlags:
    """PI-140/PI-146: opt-in overlay flags render their files; defaults stay off."""

    def _run(self, target: Path, *extra: str) -> int:
        from project_init.__main__ import main

        return main([
            str(target),
            "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "overlay-cli",
            "--description", "test",
            "--language", "python",
            *extra,
        ])

    def test_all_overlays_render(self, tmp_path: Path):
        target = tmp_path / "p"
        assert self._run(target, "--mise", "--vscode", "--devcontainer") == 0
        assert (target / "mise.toml").exists()
        assert (target / ".vscode" / "settings.json").exists()
        assert (target / ".devcontainer" / "devcontainer.json").exists()

    def test_default_scaffold_unchanged(self, tmp_path: Path):
        target = tmp_path / "p"
        assert self._run(target) == 0
        assert not (target / "mise.toml").exists()
        assert not (target / ".vscode").exists()
        assert not (target / ".devcontainer").exists()
        assert (target / ".env.example").exists(), "env pattern is always scaffolded"


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


class TestLLMModelFlags:
    """PI-132: --llm-model / --embedding-model flow into lightrag.yaml."""

    def test_model_flags_override_lightrag_yaml(self, tmp_target: Path):
        from project_init.__main__ import main

        rc = main([
            str(tmp_target),
            "--non-interactive",
            "--preset", "obsidian-lightrag",
            "--name", "cli-test",
            "--description", "testing cli",
            "--language", "python",
            "--llm-model", "claude-opus-4-8",
            "--embedding-model", "text-embedding-3-large",
            "--strict",
        ])
        assert rc == 0
        content = (tmp_target / ".claude" / "memory" / "lightrag.yaml").read_text()
        assert "model: claude-opus-4-8" in content
        assert "model: text-embedding-3-large" in content
