"""PI-139: the justfile is the canonical command interface per language.

Recipes must be thin wrappers matching the preset's toolchain, hooks and CI
must call recipes instead of inline commands, and language=none scaffolds
get no justfile at all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECIPES = ("setup", "lint", "format", "test", "docs", "ci", "scan")


# Mirrors _LANGUAGE_COMMANDS in __main__.py: empty commands for language=none.
_COMMANDS = {
    "python": ("uv run ruff check .", "uv run ruff format .", "uv run pytest"),
    "node": ("bunx eslint .", "bunx @biomejs/biome format --write .", "bun test"),
    "go": ("golangci-lint run", "golangci-lint fmt", "go test ./..."),
    "rust": (
        "cargo clippy -- -D warnings -D clippy::pedantic",
        "cargo fmt",
        "cargo test",
    ),
}


def _scaffold_language(target: Path, language: str) -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    lint, fmt, test = _COMMANDS.get(language, ("", "", ""))
    variables = fallback_variables(
        language=language, lint_command=lint, format_command=fmt, test_command=test, **flags
    )
    scaffold(target, fallback_preset(), variables)
    return target


def _recipe_body(justfile_text: str, name: str) -> str:
    match = re.search(rf"^{name}:.*\n((?:[ \t]+.*\n?)*)", justfile_text, re.MULTILINE)
    assert match, f"recipe {name!r} not found"
    return match.group(1)


class TestJustfilePerLanguage:
    @pytest.mark.parametrize(
        ("language", "lint_cmd", "test_cmd"),
        [
            ("python", "uv run ruff check .", "pytest -n auto"),
            ("node", "bunx eslint .", "bun test"),
            ("go", "golangci-lint run", "go test ./..."),
            ("rust", "cargo clippy", "cargo test"),
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
        """`ci: lint typecheck test-cov audit` — recipes referencing recipes,
        no duplicated commands. `test-cov`, not `test` (PI-569): CI must
        always run the coverage-gated variant. `audit` (PI-568): CI must
        always run the dependency vulnerability scan too."""
        target = _scaffold_language(tmp_path / "p", "python")
        text = (target / "justfile").read_text()
        assert re.search(r"^ci: lint typecheck test-cov audit\s*$", text, re.MULTILINE)

    def test_node_ci_recipe_includes_typecheck(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "n", "node")
        text = (target / "justfile").read_text()
        assert re.search(r"^ci: lint typecheck test audit\s*$", text, re.MULTILINE)
        assert "tsc --noEmit" in _recipe_body(text, "typecheck")
        assert "bun audit" in _recipe_body(text, "audit")

    def test_python_typecheck_tolerates_missing_src(self, tmp_path: Path):
        """A fresh scaffold has no src/ yet — `mypy src/` errors on a missing
        path (not a "0 files, pass" no-op), so `just typecheck`/`ci` would
        fail on day one unless the recipe guards for it."""
        target = _scaffold_language(tmp_path / "p", "python")
        body = _recipe_body((target / "justfile").read_text(), "typecheck")
        assert "if [ -d src ]" in body
        assert "mypy src/" in body

    def test_python_coverage_recipe(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "p", "python")
        text = (target / "justfile").read_text()
        assert "--cov-fail-under" in _recipe_body(text, "test-cov")

    def test_go_ci_recipe_uses_coverage_variant(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "g", "go")
        text = (target / "justfile").read_text()
        assert re.search(r"^ci: lint test-cov audit\s*$", text, re.MULTILINE)
        assert "go tool cover -func" in _recipe_body(text, "test-cov")
        assert "govulncheck ./..." in _recipe_body(text, "audit")

    def test_rust_ci_recipe_uses_coverage_variant(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "r", "rust")
        text = (target / "justfile").read_text()
        assert re.search(r"^ci: lint test-cov audit\s*$", text, re.MULTILINE)
        assert "cargo llvm-cov --fail-under-lines" in _recipe_body(text, "test-cov")
        assert "cargo audit" in _recipe_body(text, "audit")

    def test_python_test_recipe_is_self_contained(self, tmp_path: Path):
        """PI-180: `-n auto` needs pytest-xdist; pull it in on demand so a
        freshly scaffolded project that never declared it can still run tests."""
        target = _scaffold_language(tmp_path / "p", "python")
        text = (target / "justfile").read_text()
        for recipe in ("test", "test-cov"):
            body = _recipe_body(text, recipe)
            assert "-n auto" in body
            assert "--with pytest-xdist" in body, f"{recipe} must not require a declared xdist"

    def test_python_coverage_recipe_still_runs_tests_without_src(self, tmp_path: Path):
        """PI-569 review fix: a project can have tests/ before src/ exists —
        the missing-src/ guard must drop only the coverage flags, not skip
        pytest entirely (that would let a real test failure through `just
        ci`/`test-cov` silently)."""
        target = _scaffold_language(tmp_path / "p", "python")
        body = _recipe_body((target / "justfile").read_text(), "test-cov")
        assert "if [ -d src ]" in body
        else_branch = body.split("else", 1)[1]
        assert "pytest" in else_branch, "the no-src/ branch must still invoke pytest"

    def test_python_setup_uses_dependency_group(self, tmp_path: Path):
        """PI-209: dev deps live in [dependency-groups] (what `uv add --dev`
        writes), so `setup` must `uv sync --group dev`, not `--extra dev`."""
        target = _scaffold_language(tmp_path / "p", "python")
        body = _recipe_body((target / "justfile").read_text(), "setup")
        assert "uv sync --group dev" in body
        assert "--extra dev" not in body

    def test_node_recipes_do_not_rely_on_package_json_scripts(self, tmp_path: Path):
        """PI-180: `bun run lint`/`format` fail ("Script not found") with no
        package.json; recipes must call the tools directly instead."""
        target = _scaffold_language(tmp_path / "n", "node")
        text = (target / "justfile").read_text()
        assert "bunx eslint" in _recipe_body(text, "lint")
        assert "biome format" in _recipe_body(text, "format")
        assert "bun run" not in text, "node recipes must not indirect through package.json scripts"

    def test_node_setup_installs_lint_toolchain(self, tmp_path: Path):
        """PI-180 (review): `bunx eslint .` needs the config's imported plugins,
        so `setup` must install the gate toolchain or lint fails out of the box."""
        target = _scaffold_language(tmp_path / "n", "node")
        body = _recipe_body((target / "justfile").read_text(), "setup")
        assert "bun add" in body
        for pkg in ("eslint", "typescript", "typescript-eslint", "@biomejs/biome"):
            assert pkg in body, f"setup must install {pkg}"

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

    def test_rust_ci_calls_just(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "r", "rust")
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
        # CLAUDE.md is a redirect (PI-136); the canonical AGENTS.md carries
        # the command-discovery pointer.
        for name in ("AGENTS.md",):
            assert "just --list" in (target / name).read_text(), f"{name} missing just --list"

    def test_no_just_reference_for_language_none(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "n", "none")
        for name in ("CLAUDE.md", "AGENTS.md"):
            assert "just --list" not in (target / name).read_text(), name


class TestDogfoodJustfile:
    def test_repo_has_justfile_with_core_recipes(self):
        text = (_REPO_ROOT / "justfile").read_text()
        for recipe in ("setup", "lint", "format", "test", "docs", "ci"):
            assert re.search(rf"^{recipe}:", text, re.MULTILINE), f"{recipe} missing"
        assert "uv run ruff check ." in text
        assert "uv run pytest" in text
