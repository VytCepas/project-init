"""#579: dependency license compliance scanning.

A non-blocking license-scan CI job flags copyleft (GPL/AGPL) dependencies, with
a per-language tool and a tunable deny-list, plus a `just license` recipe. Rust
uses cargo-deny driven by a scaffolded deny.toml (allow-list model). Introduced
non-blocking (not in ci-gate's needs), the same rollout semgrep/scorecard used.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, language: str = "python", **overrides: str) -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    scaffold(
        target, load_preset("obsidian-only"), make_variables(language=language, **flags, **overrides), strict=True
    )
    return target


def _ci(target: Path) -> str:
    return (target / ".github" / "workflows" / "ci.yml").read_text()


def _justfile(target: Path) -> str:
    return (target / "justfile").read_text()


class TestLicenseScanJob:
    @pytest.mark.parametrize("language", ["python", "node", "go", "rust"])
    def test_job_present(self, tmp_path: Path, language: str):
        ci = _ci(_scaffold(tmp_path / language, language))
        assert "license-scan:" in ci

    def test_non_blocking_not_in_ci_gate_needs(self, tmp_path: Path):
        ci = _ci(_scaffold(tmp_path / "p", "python"))
        gate_start = ci.index("ci-gate:")
        needs_line = next(
            line for line in ci[gate_start:].splitlines() if line.lstrip().startswith("needs:")
        )
        assert "license-scan" not in needs_line, "license-scan must stay non-blocking initially"

    @pytest.mark.parametrize(
        "language,tool",
        [
            ("python", "pip-licenses"),
            ("node", "license-checker"),
            ("go", "go-licenses"),
            ("rust", "cargo-deny"),
        ],
    )
    def test_per_language_tool_wired(self, tmp_path: Path, language: str, tool: str):
        ci = _ci(_scaffold(tmp_path / language, language))
        assert tool in ci
        assert "just license" in ci

    def test_renders_cleanly(self, tmp_path: Path):
        ci = _ci(_scaffold(tmp_path / "p", "rust"))
        assert "{{#if" not in ci and "{{/if" not in ci


class TestLicenseRecipe:
    @pytest.mark.parametrize(
        "language,needle",
        [
            ("python", 'pip-licenses --from=mixed --fail-on "GPL;AGPL" --partial-match'),
            ("node", 'license-checker --production --failOn "GPL'),
            ("go", "go-licenses check ./... --disallowed_types=forbidden,restricted"),
            ("rust", "cargo deny check licenses"),
        ],
    )
    def test_recipe_uses_expected_deny_list(self, tmp_path: Path, language: str, needle: str):
        justfile = _justfile(_scaffold(tmp_path / language, language))
        assert "license:" in justfile
        assert needle in justfile


class TestRustDenyToml:
    def test_deny_toml_rendered_for_rust(self, tmp_path: Path):
        deny = (_scaffold(tmp_path / "rust", "rust") / "deny.toml").read_text()
        assert "[licenses]" in deny
        assert "version = 2" in deny
        # Allow-list model; unused entries must not error.
        assert "unused-allowed-license" in deny
        assert '"MIT"' in deny and '"Apache-2.0"' in deny

    @pytest.mark.parametrize("language", ["python", "node", "go"])
    def test_deny_toml_absent_for_non_rust(self, tmp_path: Path, language: str):
        assert not (_scaffold(tmp_path / language, language) / "deny.toml").exists()


class TestLicenseDocumented:
    @pytest.mark.parametrize(
        "language,rules_file",
        [("python", "python.md"), ("node", "node.md"), ("go", "go.md"), ("rust", "rust.md")],
    )
    def test_rules_mention_license(self, tmp_path: Path, language: str, rules_file: str):
        rules = (_scaffold(tmp_path / language, language) / ".claude" / "rules" / rules_file).read_text()
        assert "license" in rules.lower()
