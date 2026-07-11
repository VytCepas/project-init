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

    @pytest.mark.parametrize(
        ("language", "quick_cmd"),
        [
            ("python", "pytest -x -q --tb=short"),
            ("node", "bun test --bail"),
            ("go", "go test -failfast ./..."),
            ("rust", "cargo test -q"),
        ],
    )
    def test_quick_recipe_is_fail_fast(self, tmp_path: Path, language, quick_cmd):
        """PI-647 (epic #641): every language gets a fail-fast/quiet `test-quick`
        for the edit-test loop so agents ingest one failure, not the suite's."""
        target = _scaffold_language(tmp_path / language, language)
        text = (target / "justfile").read_text()
        assert quick_cmd in _recipe_body(text, "test-quick")

    def test_ci_recipe_is_pure_dependency(self, tmp_path: Path):
        """`ci` is recipe-only and day-one self-contained.

        `setup` first seeds whatever dependency/toolchain files exist, then
        `test-cov` (not `test`, PI-569) and `audit` (PI-568) run through their
        guarded recipes.
        """
        target = _scaffold_language(tmp_path / "p", "python")
        text = (target / "justfile").read_text()
        assert re.search(r"^ci: setup lint typecheck test-cov audit\s*$", text, re.MULTILINE)

    @pytest.mark.parametrize("language", ["python", "node", "go", "rust"])
    def test_fast_check_is_lighter_than_ci(self, tmp_path: Path, language):
        """PI-759: every language ships a `fast-check: lint test` recipe for the
        pre-push hook — the fast local gate. It must be strictly lighter than
        `ci` (no typecheck/audit/coverage), so pushing stays fast while CI runs
        the full gate. The pre-push hook invokes exactly this recipe.
        """
        target = _scaffold_language(tmp_path / language, language)
        text = (target / "justfile").read_text()
        assert re.search(r"^fast-check: lint test\s*$", text, re.MULTILINE)
        # Guard against silently promoting it back to the heavy gate — on the
        # header line...
        assert not re.search(r"^fast-check:.*\b(typecheck|audit|test-cov)\b", text, re.MULTILINE)
        # ...and in a body: `fast-check` must stay dependency-only, so a stray
        # `just typecheck`/`audit` line can't sneak the heavy gate back in
        # while the header still reads `lint test` (Copilot review, PR #760).
        assert _recipe_body(text, "fast-check").strip() == ""

    def test_node_ci_recipe_includes_typecheck(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "n", "node")
        text = (target / "justfile").read_text()
        assert re.search(r"^ci: setup lint typecheck test audit\s*$", text, re.MULTILINE)
        assert "tsc --noEmit" in _recipe_body(text, "typecheck")
        assert "bun audit" in _recipe_body(text, "audit")

    def test_python_typecheck_tolerates_missing_src(self, tmp_path: Path):
        """A fresh scaffold has no src/ yet — `mypy src/` errors on a missing
        path (not a "0 files, pass" no-op), so `just typecheck`/`ci` would
        fail on day one unless the recipe guards for it."""
        target = _scaffold_language(tmp_path / "p", "python")
        body = _recipe_body((target / "justfile").read_text(), "typecheck")
        assert "if [ -d src ]" in body
        assert "mypy" in body and "src/" in body

    def test_python_typecheck_installs_dependency_stubs(self, tmp_path: Path):
        """#592: `uv run --with mypy` supplies runtime deps but not their stub
        packages, so any untyped dep (PyYAML → types-PyYAML) fails the strict
        gate with import-untyped on a fresh scaffold. The recipe must let mypy
        fetch stubs itself — and must pull in pip, which mypy's
        --install-types shells out to but uv-managed environments omit."""
        target = _scaffold_language(tmp_path / "p", "python")
        body = _recipe_body((target / "justfile").read_text(), "typecheck")
        assert "--install-types" in body
        assert "--non-interactive" in body
        assert "--with pip" in body, "mypy --install-types needs pip in the uv environment"

    def test_node_typecheck_tolerates_missing_sources(self, tmp_path: Path):
        """The #592-adjacent day-one gap: `tsc --noEmit` fails with TS18003
        ("No inputs were found"), not a pass, when no .ts sources exist yet."""
        target = _scaffold_language(tmp_path / "n", "node")
        body = _recipe_body((target / "justfile").read_text(), "typecheck")
        assert "tsc --noEmit" in body
        assert "No TypeScript sources yet" in body
        # Prune node_modules at any depth (monorepos vendor .ts under nested
        # node_modules) — a top-level-only "./node_modules/*" would falsely
        # detect vendored sources and run tsc (PR #594 review).
        assert "*/node_modules/*" in body
        assert '"./node_modules/*"' not in body

    def test_python_setup_tolerates_missing_pyproject(self, tmp_path: Path):
        """`uv sync --group dev` hard-fails with no pyproject.toml (fresh
        scaffold) or no [dependency-groups] table — CI's first step must not
        die before the day-one guards in typecheck/test-cov can run."""
        target = _scaffold_language(tmp_path / "p", "python")
        body = _recipe_body((target / "justfile").read_text(), "setup")
        assert "pyproject.toml" in body
        assert "uv sync --group dev" in body

    def test_go_test_cov_guards_fresh_module_and_fails_closed(self, tmp_path: Path):
        """`go test ./...` errors on a module with no .go files (like the
        guarded license/fuzz recipes), and the coverage gate must be
        fail-closed: zero awk input (cover tool failed) fails the recipe
        instead of returning awk's 0."""
        target = _scaffold_language(tmp_path / "g", "go")
        body = _recipe_body((target / "justfile").read_text(), "test-cov")
        assert "No Go sources yet" in body
        assert "NR == 0" in body, "coverage gate must fail on empty cover output"

    def test_python_coverage_recipe(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "p", "python")
        text = (target / "justfile").read_text()
        assert "--cov-fail-under" in _recipe_body(text, "test-cov")

    def test_go_ci_recipe_uses_coverage_variant(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "g", "go")
        text = (target / "justfile").read_text()
        assert re.search(r"^ci: lint typecheck test-cov audit\s*$", text, re.MULTILINE)
        assert "go tool cover -func" in _recipe_body(text, "test-cov")
        assert "govulncheck ./..." in _recipe_body(text, "audit")

    def test_rust_ci_recipe_uses_coverage_variant(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "r", "rust")
        text = (target / "justfile").read_text()
        assert re.search(r"^ci: lint typecheck test-cov audit\s*$", text, re.MULTILINE)
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
        ci`/`test-cov` silently). If neither src/ nor tests/ exists yet, it
        skips cleanly so a fresh scaffold's first `just ci` is green."""
        target = _scaffold_language(tmp_path / "p", "python")
        body = _recipe_body((target / "justfile").read_text(), "test-cov")
        assert "if [ -d src ]" in body
        assert "elif find tests" in body
        assert "pytest" in body, "the tests-present branch must still invoke pytest"
        assert "No src/ or test files yet" in body

    def test_python_test_recipe_tolerates_zero_tests(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "p", "python")
        body = _recipe_body((target / "justfile").read_text(), "test")
        assert "find tests" in body
        assert "No test files yet" in body

    def test_python_audit_tolerates_missing_manifest(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "p", "python")
        body = _recipe_body((target / "justfile").read_text(), "audit")
        assert "pyproject.toml" in body
        assert "No Python dependency manifest yet" in body

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

    def test_node_ci_runs_setup_before_lint(self, tmp_path: Path):
        """A fresh node scaffold has package.json but no node_modules. `just ci`
        must seed the eslint import deps before `bunx eslint .` runs."""
        target = _scaffold_language(tmp_path / "n", "node")
        text = (target / "justfile").read_text()
        assert re.search(r"^ci: setup lint typecheck test audit\s*$", text, re.MULTILINE)

    def test_node_audit_tolerates_missing_manifest(self, tmp_path: Path):
        target = _scaffold_language(tmp_path / "n", "node")
        body = _recipe_body((target / "justfile").read_text(), "audit")
        assert "package.json" in body
        assert "No Node dependency manifest yet" in body

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
        assert re.search(r"extractions/setup-just@[0-9a-f]{40} # v4\b", ci)
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
        hook = (target / ".agents" / "hooks" / "pre_commit_gate.sh").read_text()
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
