"""#580: property-based testing / fuzzing wired per language.

Each language gets a `just fuzz` recipe and a documented pattern in its rules
file. Go — whose fuzzing is native to the toolchain — additionally gets a real,
CI-safe (seed-corpus replay) CI job. Everything is scoped as opt-in pattern/
tooling, NOT a blocking gate: the Go fuzz job is not in ci-gate's needs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, language: str = "python") -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    scaffold(target, load_preset("obsidian-only"), make_variables(language=language, **flags), strict=True)
    return target


class TestFuzzRecipe:
    @pytest.mark.parametrize(
        "language,needle",
        [
            ("python", "uv run --with hypothesis"),
            ("node", "bun test"),
            ("go", 'go test -run="Fuzz" ./...'),
            ("rust", "cargo test"),
        ],
    )
    def test_fuzz_recipe_present(self, tmp_path: Path, language: str, needle: str):
        justfile = (_scaffold(tmp_path / language, language) / "justfile").read_text()
        assert "fuzz:" in justfile
        assert needle in justfile


class TestGoFuzzJob:
    def test_job_present_for_go(self, tmp_path: Path):
        ci = (_scaffold(tmp_path / "go", "go") / ".github" / "workflows" / "ci.yml").read_text()
        assert "fuzz:" in ci
        assert "Go fuzz" in ci
        # CI-safe: seed-corpus replay via the recipe, not unbounded generation.
        assert "just fuzz" in ci

    def test_go_fuzz_non_blocking(self, tmp_path: Path):
        ci = (_scaffold(tmp_path / "go", "go") / ".github" / "workflows" / "ci.yml").read_text()
        gate_start = ci.index("ci-gate:")
        needs_line = next(
            line for line in ci[gate_start:].splitlines() if line.lstrip().startswith("needs:")
        )
        assert "fuzz" not in needs_line, "the Go fuzz job must stay non-blocking"

    @pytest.mark.parametrize("language", ["python", "node", "rust"])
    def test_go_fuzz_job_absent_for_non_go(self, tmp_path: Path, language: str):
        ci = (_scaffold(tmp_path / language, language) / ".github" / "workflows" / "ci.yml").read_text()
        assert "Go fuzz" not in ci

    def test_renders_cleanly(self, tmp_path: Path):
        ci = (_scaffold(tmp_path / "go", "go") / ".github" / "workflows" / "ci.yml").read_text()
        assert "{{#if" not in ci and "{{/if" not in ci


class TestFuzzDocumented:
    @pytest.mark.parametrize(
        "language,rules_file,tool",
        [
            ("python", "python.md", "Hypothesis"),
            ("node", "node.md", "fast-check"),
            ("go", "go.md", "go test -fuzz"),
            ("rust", "rust.md", "proptest"),
        ],
    )
    def test_rules_document_pattern(self, tmp_path: Path, language: str, rules_file: str, tool: str):
        rules = (_scaffold(tmp_path / language, language) / ".agents" / "rules" / rules_file).read_text()
        assert tool in rules
        # Explicitly scoped as pattern/tooling, not a blocking gate.
        assert "not** a blocking gate" in rules or "not a blocking gate" in rules
