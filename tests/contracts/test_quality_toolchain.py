"""PI-138: quality and documentation toolchain contracts.

Each language preset must ship its doc + complexity lint config, the docs
toolchain, and nothing belonging to another language — language-gated
template files render empty and are skipped by the engine.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


def _scaffold_language(target: Path, language: str) -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    scaffold(target, fallback_preset(), fallback_variables(language=language, **flags))
    return target


class TestPythonToolchain:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = _scaffold_language(tmp_target, "python")

    def test_ruff_config_rendered_and_parseable(self):
        config = tomllib.loads((self.target / "ruff.toml").read_text())
        select = config["lint"]["select"]
        for rule in (
            "D",
            "C901",
            "PLR0912",
            "PLR0913",
            "PLR0915",
            "RUF",
            "PERF",
            "PTH",
            "RET",
            "ARG",
            "A",
            "S",
            "BLE",
        ):
            assert rule in select, f"{rule} missing from scaffolded ruff select"
        assert config["lint"]["pydocstyle"]["convention"] == "google"
        assert config["lint"]["mccabe"]["max-complexity"] == 10

    def test_ruff_exempts_tests_and_agent_infra(self):
        config = tomllib.loads((self.target / "ruff.toml").read_text())
        ignores = config["lint"]["per-file-ignores"]
        assert "D" in ignores["tests/**"]
        assert "S" in ignores["tests/**"], "plain assert must not be flagged as insecure"
        assert "C901" in ignores[".claude/**"]

    def test_mypy_config_rendered_and_parseable(self):
        import configparser

        config = configparser.ConfigParser()
        config.read_string((self.target / "mypy.ini").read_text())
        assert config.getboolean("mypy", "strict") is True
        assert config["mypy"]["python_version"] == "3.11"
        # Deliberately excluded (PI-570): verified noisy against legitimate
        # `Any` usage (JSON parsing, generic callable wrappers).
        assert "disallow_any_explicit" not in config["mypy"]

    def test_typecheck_recipe_and_ci_wired(self):
        justfile = (self.target / "justfile").read_text()
        assert "typecheck:" in justfile
        assert "mypy" in justfile
        assert "ci: lint typecheck test" in justfile

        ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just typecheck" in ci

    def test_mkdocs_config_rendered(self):
        content = (self.target / "mkdocs.yml").read_text()
        assert "name: material" in content
        assert "mkdocstrings" in content
        assert "docstring_style: google" in content
        assert "Zensical" in content, "migration note for mkdocs-material maintenance mode"

    def test_no_pages_deploy_workflow(self):
        """No published docs site — github.com renders Markdown and mkdocs.yml
        stays for local `mkdocs serve` preview (PI-343)."""
        assert not (self.target / ".github" / "workflows" / "docs.yml").exists()

    def test_no_other_language_configs(self):
        assert not (self.target / "eslint.config.mjs").exists()
        assert not (self.target / ".golangci.yml").exists()
        assert not (self.target / "typedoc.json").exists()
        assert not (self.target / "clippy.toml").exists()
        assert not (self.target / "tsconfig.base.json").exists()
        assert not (self.target / "bunfig.toml").exists()


class TestNodeToolchain:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = _scaffold_language(tmp_target, "node")

    def test_eslint_config_rendered(self):
        content = (self.target / "eslint.config.mjs").read_text()
        assert "typescript-eslint" in content
        assert "eslint-plugin-jsdoc" in content
        assert "eslint-plugin-tsdoc" in content
        assert 'complexity: ["error", 10]' in content
        assert "tseslint.configs.strictTypeChecked" in content
        assert "tseslint.configs.stylisticTypeChecked" in content

    def test_eslint_wires_type_aware_linting(self):
        """PI-570: strictTypeChecked needs parserOptions.project — verify it
        points at the scaffolded tsconfig.json, not left dangling."""
        content = (self.target / "eslint.config.mjs").read_text()
        assert 'project: "./tsconfig.json"' in content

    def test_tsconfig_base_rendered_and_parseable(self):
        config = json.loads((self.target / "tsconfig.base.json").read_text())
        options = config["compilerOptions"]
        assert options["strict"] is True
        assert options["noUncheckedIndexedAccess"] is True
        assert options["exactOptionalPropertyTypes"] is True
        assert options["noImplicitOverride"] is True
        assert options["noPropertyAccessFromIndexSignature"] is True
        assert options["noFallthroughCasesInSwitch"] is True
        assert options["noImplicitReturns"] is True
        assert options["allowUnreachableCode"] is False

    def test_tsconfig_extends_base(self):
        config = json.loads((self.target / "tsconfig.json").read_text())
        assert config["extends"] == "./tsconfig.base.json"

    def test_typecheck_recipe_and_ci_wired(self):
        justfile = (self.target / "justfile").read_text()
        assert "typecheck:" in justfile
        assert "tsc --noEmit" in justfile
        assert "ci: lint typecheck test" in justfile

        ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just typecheck" in ci

    def test_typedoc_config_rendered_and_parseable(self):
        raw = (self.target / "typedoc.json").read_text()
        uncommented = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)
        config = json.loads(uncommented)
        assert config["entryPoints"]
        assert config["validation"]["notDocumented"] is True

    def test_no_pages_deploy_workflow(self):
        """No published docs site — typedoc.json stays for local API-doc
        generation, but nothing is auto-published to Pages (PI-343)."""
        assert not (self.target / ".github" / "workflows" / "docs.yml").exists()

    def test_no_other_language_configs(self):
        assert not (self.target / "ruff.toml").exists()
        assert not (self.target / "mkdocs.yml").exists()
        assert not (self.target / ".golangci.yml").exists()
        assert not (self.target / "mypy.ini").exists()
        assert not (self.target / "clippy.toml").exists()

    def test_bunfig_coverage_gate_rendered(self):
        """PI-569: `bun test` picks up bunfig.toml automatically — no extra
        CLI flag needed anywhere (justfile, CI, or a developer's terminal)."""
        config = tomllib.loads((self.target / "bunfig.toml").read_text())
        assert config["test"]["coverage"] is True
        assert config["test"]["coverageThreshold"] == 0.7


class TestGoToolchain:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = _scaffold_language(tmp_target, "go")

    def test_golangci_config_rendered(self):
        content = (self.target / ".golangci.yml").read_text()
        assert 'version: "2"' in content
        for linter in (
            "revive",
            "godoclint",
            "gocognit",
            "cyclop",
            "dupl",
            "errcheck",
            "govet",
            "staticcheck",
            "gosec",
        ):
            assert linter in content, f"{linter} missing from .golangci.yml"
        assert "gofumpt" in content

    def test_golangci_complexity_cap_mirrors_ruff(self):
        content = (self.target / ".golangci.yml").read_text()
        assert "max-complexity: 10" in content, (
            "cyclop cap must mirror ruff's mccabe max-complexity = 10"
        )

    def test_no_docs_workflow(self):
        """Go needs no docs site — pkg.go.dev renders doc comments."""
        assert not (self.target / ".github" / "workflows" / "docs.yml").exists()

    def test_no_other_language_configs(self):
        assert not (self.target / "ruff.toml").exists()
        assert not (self.target / "eslint.config.mjs").exists()
        assert not (self.target / "typedoc.json").exists()
        assert not (self.target / "mypy.ini").exists()
        assert not (self.target / "clippy.toml").exists()
        assert not (self.target / "tsconfig.base.json").exists()
        assert not (self.target / "bunfig.toml").exists()

    def test_coverage_gate_wired(self):
        """PI-569: blocking, not conditional — go tool cover ships with the
        Go toolchain, nothing extra to provision."""
        justfile = (self.target / "justfile").read_text()
        assert "test-cov:" in justfile
        assert "go tool cover -func" in justfile
        assert "ci: lint test-cov" in justfile

        ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just test-cov" in ci


class TestRustToolchain:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = _scaffold_language(tmp_target, "rust")

    def test_cargo_config_rendered(self):
        config = tomllib.loads((self.target / ".cargo" / "config.toml").read_text())
        assert config["build"]["rustflags"] == ["-D", "warnings"]

    def test_clippy_config_rendered(self):
        config = tomllib.loads((self.target / "clippy.toml").read_text())
        assert config["cognitive-complexity-threshold"] == 10

    def test_rustfmt_config_rendered(self):
        content = (self.target / "rustfmt.toml").read_text()
        assert "edition" in content

    def test_no_docs_workflow(self):
        """Rust needs no docs site — docs.rs renders published crate docs."""
        assert not (self.target / ".github" / "workflows" / "docs.yml").exists()

    def test_no_other_language_configs(self):
        assert not (self.target / "ruff.toml").exists()
        assert not (self.target / "eslint.config.mjs").exists()
        assert not (self.target / "typedoc.json").exists()
        assert not (self.target / "mypy.ini").exists()
        assert not (self.target / ".golangci.yml").exists()
        assert not (self.target / "tsconfig.base.json").exists()
        assert not (self.target / "bunfig.toml").exists()

    def test_coverage_gate_wired(self):
        """PI-569: blocking, not conditional — CI installs cargo-llvm-cov as
        a prebuilt binary (taiki-e/install-action), no source compile."""
        justfile = (self.target / "justfile").read_text()
        assert "test-cov:" in justfile
        assert "cargo llvm-cov --fail-under-lines" in justfile
        assert "ci: lint test-cov" in justfile

        ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just test-cov" in ci
        assert "taiki-e/install-action" in ci
        assert "cargo-llvm-cov" in ci
        assert "llvm-tools-preview" in ci


class TestNoLanguage:
    """language=none gets no toolchain config files at all (empty-render skip)."""

    def test_no_language_configs(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "none")
        for name in (
            "ruff.toml",
            "eslint.config.mjs",
            ".golangci.yml",
            "mkdocs.yml",
            "typedoc.json",
            "mypy.ini",
            "clippy.toml",
            "rustfmt.toml",
            ".cargo/config.toml",
            "tsconfig.base.json",
            "tsconfig.json",
            "bunfig.toml",
            ".github/workflows/docs.yml",
        ):
            assert not (target / name).exists(), f"{name} must not render for language=none"

    def test_strict_mode_skips_empty_renders(self, tmp_target: Path):
        """Strict mode must not trip over language-gated files rendering empty."""
        flags = {lang: "" for lang in ("python", "node", "go", "rust")}
        created = scaffold(
            tmp_target,
            fallback_preset(),
            fallback_variables(language="none", **flags),
            strict=True,
        )
        assert Path("ruff.toml") not in created


class TestDiataxisDocs:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = _scaffold_language(tmp_target, "python")

    def test_skeleton_scaffolded(self):
        for section in ("tutorials", "how-to", "reference", "explanation"):
            index = self.target / "docs" / section / "index.md"
            assert index.is_file(), f"docs/{section}/index.md missing"

    def test_index_rendered_with_project_name(self):
        content = (self.target / "docs" / "index.md").read_text()
        assert "my-project" in content
        assert "diataxis.fr" in content
        assert "deepwiki.com" in content


class TestAdrToolchain:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = _scaffold_language(tmp_target, "python")

    def test_madr_template_scaffolded(self):
        content = (self.target / ".claude" / "docs" / "adr" / "adr-template.md").read_text()
        for section in (
            "Context and Problem Statement",
            "Considered Options",
            "Decision Outcome",
            "Consequences",
        ):
            assert section in content

    def test_add_adr_skill_scaffolded_and_indexed(self):
        skill = self.target / ".claude" / "skills" / "add_adr" / "SKILL.md"
        assert skill.is_file()
        assert "adr-template.md" in skill.read_text()
        index = (self.target / ".claude" / "skills" / "INDEX.md").read_text()
        assert "add_adr" in index


class TestCiQualityGates:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = _scaffold_language(tmp_target, "python")
        self.ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()

    def test_coverage_gate_present(self):
        """PI-569: unconditional, not gated on pytest-cov happening to be a
        persisted dev dependency — `--with pytest-cov` ephemeral-installs it
        the same way mypy/mutmut are ephemeral-installed."""
        assert "just test-cov" in self.ci
        assert "if uv run python -c" not in self.ci, "coverage gate must not be conditional"

        justfile = (self.target / "justfile").read_text()
        assert "--cov-fail-under" in justfile
        assert "--cov=src" in justfile

    def test_mutmut_job_active_and_non_blocking(self):
        """PI-563: mutmut graduated from a commented placeholder to a real,
        active job — but it must stay non-blocking (schedule-only, excluded
        from ci-gate's needs) until a baseline mutation score is established."""
        assert "mutation-tests:" in self.ci
        assert "mutmut run" in self.ci
        assert "export-cicd-stats" in self.ci
        assert "if: github.event_name == 'schedule'" in self.ci

        gate_start = self.ci.index("ci-gate:")
        gate_needs_line = next(
            line for line in self.ci[gate_start:].splitlines() if line.lstrip().startswith("needs:")
        )
        assert "mutation-tests" not in gate_needs_line, "mutation-tests must stay non-blocking"

    def test_mutmut_schedule_present_for_python(self):
        assert "cron:" in self.ci

    @pytest.mark.parametrize("language", ["node", "go", "rust"])
    def test_mutmut_schedule_absent_for_other_languages(self, tmp_target: Path, language):
        target = _scaffold_language(tmp_target, language)
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "cron:" not in ci, f"schedule trigger must not render for {language}"
        assert "mutation-tests:" not in ci


class TestBashLintGate:
    """PI-562: shellcheck + shfmt gate .claude/**/*.sh regardless of language —
    bash agent infra always ships, so the gate isn't tied to any one language."""

    @pytest.mark.parametrize("language", ["python", "node", "go", "rust"])
    def test_lint_recipe_runs_shellcheck_and_shfmt(self, tmp_target: Path, language):
        target = _scaffold_language(tmp_target, language)
        justfile = (target / "justfile").read_text()
        assert "shellcheck -S error -x" in justfile
        assert "shfmt -d -i 2" in justfile

    @pytest.mark.parametrize("language", ["python", "node", "go", "rust"])
    def test_ci_installs_shfmt(self, tmp_target: Path, language):
        target = _scaffold_language(tmp_target, language)
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "Install shfmt" in ci

    def test_go_ci_runs_shell_gate_explicitly(self, tmp_target: Path):
        """Go's CI lint step calls the golangci-lint action directly (not `just
        lint`), so the shell gate needs its own explicit step."""
        target = _scaffold_language(tmp_target, "go")
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "shellcheck -S error -x" in ci
        assert "shfmt -d -i 2" in ci


class TestSemgrepGate:
    """PI-565: semantic security backstop, always-on (like secret-scan), with
    a per-language ruleset and no-language still getting secrets/OWASP."""

    @pytest.mark.parametrize("language", ["python", "node", "go", "none"])
    def test_semgrep_job_present_and_non_blocking(self, tmp_target: Path, language):
        target = _scaffold_language(tmp_target, language)
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "semgrep:" in ci
        assert "p/secrets" in ci
        assert "p/owasp-top-ten" in ci
        assert "--baseline-commit" in ci

        gate_start = ci.index("ci-gate:")
        gate_needs_line = next(
            line for line in ci[gate_start:].splitlines() if line.lstrip().startswith("needs:")
        )
        assert "semgrep" not in gate_needs_line, "semgrep must stay non-blocking initially"

    def test_python_ruleset_selected(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "python")
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "p/python" in ci
        assert "p/typescript" not in ci
        assert "p/golang" not in ci

    def test_node_ruleset_selected(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "node")
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "p/typescript" in ci
        assert "p/python" not in ci
        assert "p/golang" not in ci

    def test_go_ruleset_selected(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "go")
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "p/golang" in ci
        assert "p/python" not in ci
        assert "p/typescript" not in ci

    def test_rust_ruleset_selected(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "rust")
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "p/rust" in ci
        assert "p/python" not in ci
        assert "p/golang" not in ci


class TestQualityPlugins:
    def test_pr_review_toolkit_enabled(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "python")
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        assert settings["enabledPlugins"]["pr-review-toolkit@claude-plugins-official"] is True

    def test_agents_md_recommends_review_plugins(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "python")
        content = (target / "AGENTS.md").read_text()
        assert "pr-review-toolkit" in content
        assert "code-review@claude-plugins-official" in content
