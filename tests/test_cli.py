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
