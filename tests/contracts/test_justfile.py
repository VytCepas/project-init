"""PI-139: the justfile is the canonical command interface per language.

Recipes must be thin wrappers matching the preset's toolchain, hooks and CI
must call recipes instead of inline commands, and language=none scaffolds
get no justfile at all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECIPES = ("setup", "lint", "format", "test", "docs", "ci", "scan")


# Mirrors _LANGUAGE_COMMANDS in __main__.py: empty commands for language=none.
_COMMANDS = {
    "python": ("uv run ruff check .", "uv run ruff format .", "uv run pytest"),
    "node": ("bun run lint", "bun run format", "bun test"),
    "go": ("golangci-lint run", "gofmt -w .", "go test ./..."),
}


def _scaffold_language(target: Path, language: str) -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go")}
    lint, fmt, test = _COMMANDS.get(language, ("", "", ""))
    variables = make_variables(
        language=language, lint_command=lint, format_command=fmt, test_command=test, **flags
    )
    scaffold(target, load_preset("obsidian-only"), variables)
    return target


def _recipe_body(justfile_text: str, name: str) -> str:
    match = re.search(rf"^{name}:.*\n((?:[ \t]+.*\n?)*)", justfile_text, re.MULTILINE)
    assert match, f"recipe {name!r} not found"
    return match.group(1)


class TestJustfilePerLanguage:
    @pytest.mark.parametrize(
        ("language", "lint_cmd", "test_cmd"),
        [
            ("python", "uv run ruff check .", "uv run pytest"),
            ("node", "bun run lint", "bun test"),
            ("go", "golangci-lint run", "go test ./..."),
        ],
    )
    def test_recipes_match_toolchain(self, tmp_path: Path, language, lint_cmd, test_cmd):
        target = _scaffold_language(tmp_path / language, language)
        text = (target / "justfile").read_text()
        for recipe in _RECIPES:
            assert re.search(rf"^{recipe}:", text, re.MULTILINE), f"{recipe} missing ({language})"
        assert lint_cmd in _recipe_body(text, "lint")
        assert test_cmd in _recipe_body(text, "test")
        assert "gitleaks git --pre-commit" in _recipe_body(text, "scan")

    def test_ci_recipe_is_pure_dependency(self, tmp_path: Path):
        """`ci: lint test` — recipes referencing recipes, no duplicated commands."""
        target = _scaffold_language(tmp_path / "p", "python")
        text = (target / "justfile").read_text()
        assert re.search(r"^ci: lint test\s*$", text, re.MULTILINE)

    def test_python_coverage_recipe(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "p", "python")
        text = (target / "justfile").read_text()
        assert "--cov-fail-under" in _recipe_body(text, "test-cov")

    def test_no_justfile_for_language_none(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "n", "none")
        assert not (target / "justfile").exists()

    def test_no_just_interpolation_braces(self, tmp_path: Path):
        """Recipes stay parameterless: just's own {{...}} interpolation would
        collide with the template engine and trip strict mode."""
        target = _scaffold_language(tmp_path / "p", "python")
        assert "{{" not in (target / "justfile").read_text()


class TestRecipesAreTheSingleCallsite:
    def test_ci_workflow_calls_just(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "p", "python")
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "extractions/setup-just@v4" in ci
        assert "just lint" in ci
        assert "just test-cov" in ci

    def test_node_ci_calls_just(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "n", "node")
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just lint" in ci
        assert "just test" in ci

    def test_pre_commit_gate_uses_just_lint(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "p", "python")
        hook = (target / ".claude" / "hooks" / "pre_commit_gate.sh").read_text()
        assert "just lint" in hook
        assert "command -v just" in hook, "must fall back when just is not installed"
        assert "just --show lint" in hook, (
            "must fall back when a pre-existing justfile has no lint recipe"
        )

    def test_instruction_files_reference_just_list(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "p", "python")
        # CLAUDE.md is a redirect (PI-136); the canonical and Gemini entry
        # points carry the command-discovery pointer.
        for name in ("AGENTS.md", "GEMINI.md"):
            assert "just --list" in (target / name).read_text(), f"{name} missing just --list"

    def test_no_just_reference_for_language_none(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "n", "none")
        for name in ("CLAUDE.md", "AGENTS.md", "GEMINI.md"):
            assert "just --list" not in (target / name).read_text(), name


class TestDogfoodJustfile:
    def test_repo_has_justfile_with_core_recipes(self):
        text = (_REPO_ROOT / "justfile").read_text()
        for recipe in ("setup", "lint", "format", "test", "docs", "ci"):
            assert re.search(rf"^{recipe}:", text, re.MULTILINE), f"{recipe} missing"
        assert "uv run ruff check ." in text
        assert "uv run pytest" in text
