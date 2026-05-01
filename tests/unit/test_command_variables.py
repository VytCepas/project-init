from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


class TestCommandVariables:
    """PI-16: lint_command / format_command / test_command per language."""

    def _scaffold_with_lang(self, tmp_path: Path, **kwargs) -> Path:
        target = tmp_path / "p"
        preset = load_preset("obsidian-only")
        variables = make_variables(**kwargs)
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
