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
from tests.workflow import job, load_workflow, needs, steps


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
        assert "C901" in ignores[".agents/**"]

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
        assert "ci: setup lint typecheck test" in justfile

        ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just typecheck" in ci

    def test_ci_uv_sync_guarded_for_fresh_scaffold(self):
        """2026-07 QA: a fresh scaffold ships no pyproject.toml — every CI step
        that runs `uv sync --group dev` (integration tests, nightly mutation)
        must guard on it, or the first PR shows red on jobs that have nothing to
        test yet.

        Guarded structurally, two ways (parse, not a text window — #739): the
        `pyproject.toml` check is either INSIDE the step's own `run:` script
        (integration-tests) or in the step's `if:` referencing a prior
        `Check for pyproject.toml` step (mutation-tests). The old ±12-line text
        window happened to span both; a reformat that pushed the guard further
        away would have silently passed.
        """
        wf = load_workflow(self.target)
        found = 0
        for job_name, spec in (wf.get("jobs") or {}).items():
            for step in steps(spec):
                run = step.get("run") or ""
                if "uv sync --group dev" not in run:
                    continue
                found += 1
                guarded = "pyproject.toml" in run or "pyproject" in str(step.get("if", ""))
                assert guarded, (
                    f"{job_name}: `uv sync --group dev` step has no pyproject.toml "
                    f"guard (run block or step if:)"
                )
        # Both the integration-tests job and the nightly mutation job run it.
        assert found >= 2, f"expected >=2 guarded uv sync steps, found {found}"

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

    def test_eslint_day_one_safe_scoping(self):
        """A fresh scaffold has zero .ts files and this .mjs config sits outside
        tsconfig — type-aware settings must be scoped to *.ts(x) and the config
        files given a disableTypeChecked carve-out, or `eslint .` fails day-one
        (TS18003 / file-not-in-project) and blocks the very first commit."""
        content = (self.target / "eslint.config.mjs").read_text()
        # Type-aware block (the one that sets parserOptions.project) is scoped.
        assert 'files: ["**/*.ts", "**/*.tsx"]' in content
        # Config / tooling files opt out of the type-checked rules.
        assert "tseslint.configs.disableTypeChecked" in content
        assert '["**/*.mjs", "**/*.cjs", "**/*.js"]' in content

    def test_eslint_enforces_public_api_docs(self):
        """Parity with ruff D / revive exported: public-symbol docs are an ERROR,
        not a warning — jsdoc/require-jsdoc at error level on exported symbols."""
        content = (self.target / "eslint.config.mjs").read_text()
        assert '"jsdoc/require-jsdoc"' in content
        assert '"error"' in content
        assert "publicOnly: true" in content

    def test_test_recipe_has_day_one_guard(self):
        """`bun test` exits 1 with zero test files, which would fail `just ci`
        (and the pre-push gate) on a fresh scaffold — the recipe must skip until
        a test file exists, like the go/rust guards."""
        justfile = (self.target / "justfile").read_text()
        # The test recipe checks for test files before invoking bun test.
        assert "*.test.ts" in justfile and "nothing to test" in justfile

    def test_ts_only_policy_documented(self):
        """TypeScript is mandatory; the rule doc must state no plain JS and warn
        against re-opening the hole via allowJs."""
        rule = (self.target / ".agents" / "rules" / "typescript.md").read_text()
        assert "TypeScript only" in rule
        assert "allowJs" in rule

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
        assert "ci: setup lint typecheck test" in justfile

        ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just typecheck" in ci

    def test_ci_install_falls_back_to_just_setup(self):
        """A fresh node scaffold has no package.json — `bun install` errors
        without one. CI must fall back to `just setup`, which seeds the lint
        toolchain eslint.config.mjs imports, so the first CI run passes."""
        ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just setup" in ci, "node CI must fall back to just setup when no package.json"
        assert "package.json" in ci

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
        # PI-569 review fix: explicit, not relying on bun's current default —
        # a *.test.ts file must never count toward the application-code gate.
        assert config["test"]["coverageSkipTestFiles"] is True


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

    def test_ci_uses_golangci_action_v8_or_newer(self):
        """golangci-lint-action must be v8+ to run the shipped v2 config —
        v6 caps the tool at v1.64.8, which rejects `version: "2"`."""
        ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        m = re.search(r"golangci/golangci-lint-action@[0-9a-f]{40} # v(\d+)", ci)
        assert m, "golangci-lint-action must be referenced in Go CI"
        assert int(m.group(1)) >= 8, "must be v8+ for golangci-lint v2 config"

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
        assert "ci: lint typecheck test-cov" in justfile

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

    def test_lint_enforces_complexity_and_docs(self):
        """clippy::cognitive_complexity is a nursery lint that -D pedantic does
        NOT enable, so the clippy.toml threshold is inert without an explicit
        -D; missing_docs gives public-API doc parity with ruff D / go revive.
        Both must be denied on the actual `just lint` clippy invocation."""
        justfile = (self.target / "justfile").read_text()
        assert "-D clippy::cognitive_complexity" in justfile
        assert "-D missing_docs" in justfile

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
        assert "ci: lint typecheck test-cov" in justfile

        ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just test-cov" in ci
        assert "taiki-e/install-action" in ci
        assert "cargo-llvm-cov" in ci
        assert "llvm-tools-preview" in ci


class TestShellLintGate:
    """The lint recipe's shell-hook checks (shellcheck/shfmt) must not fail-close
    when those tools are absent — otherwise the fail-closed pre-commit hook
    blocks every commit on a clone that has `just` but not shellcheck/shfmt."""

    def test_lint_shell_checks_are_fail_open(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "python")
        justfile = (target / "justfile").read_text()
        # Guarded on tool presence rather than an unconditional `find … -exec`.
        assert "command -v shellcheck" in justfile
        assert "command -v shfmt" in justfile
        assert "skipping shell lint" in justfile

    def test_mise_provisions_shell_gate_tools(self, tmp_target: Path):
        """mise pins the gate toolchain so `mise install` yields a complete
        local lint environment (just + shellcheck + shfmt), not just `just`."""
        scaffold(
            tmp_target,
            fallback_preset(),
            fallback_variables(language="python", python="true", mise="true"),
        )
        mise = (tmp_target / "mise.toml").read_text()
        assert "shellcheck" in mise
        assert "shfmt" in mise


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
        content = (self.target / ".agents" / "docs" / "adr" / "adr-template.md").read_text()
        for section in (
            "Context and Problem Statement",
            "Considered Options",
            "Decision Outcome",
            "Consequences",
        ):
            assert section in content

    def test_madr_template_links_diagrams_not_pastes_them(self):
        """PI-683: ADRs must link the diagram-skill folder, not paste a render
        (so the ADR can't drift on re-render), and the example hrefs must be
        written relative to the ADR's own location (.agents/docs/adr/) so a
        reader following them doesn't 404. Assert every load-bearing part, so
        dropping the anti-paste rule, a folder path, or a relative href fails.
        """
        content = (self.target / ".agents" / "docs" / "adr" / "adr-template.md").read_text()
        assert "link that folder" in content  # link, ...
        assert "don't paste" in content  # ... don't paste a render
        # The example hrefs are ADR-relative — a bare repo-root path would
        # resolve under .agents/docs/adr/ and 404.
        assert "../../../docs/diagrams/<slug>/" in content  # non-vault folder
        assert "../../vault/design/<slug>/" in content  # vault folder

    def test_add_adr_skill_scaffolded_and_indexed(self):
        skill = self.target / ".agents" / "skills" / "add_adr" / "SKILL.md"
        assert skill.is_file()
        assert "adr-template.md" in skill.read_text()
        index = (self.target / ".agents" / "skills" / "INDEX.md").read_text()
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
        wf = load_workflow(self.target)
        assert "schedule" in str(job(wf, "mutation-tests").get("if", ""))
        assert "mutation-tests" not in needs(wf, "ci-gate"), "mutation-tests must stay non-blocking"

    def test_mutmut_schedule_present_for_python(self):
        assert "cron:" in self.ci

    @pytest.mark.parametrize("language", ["node", "go", "rust"])
    def test_mutmut_job_absent_for_other_languages(self, tmp_target: Path, language):
        target = _scaffold_language(tmp_target, language)
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        # mutmut is python-only, so the JOB must not render. The nightly cron is
        # NOT a proxy for that any more: #727 made it language-agnostic because
        # the `fuzz` job needs it in every language. Each schedule-gated job now
        # names its own cron via `github.event.schedule`, so a shared cron does
        # not imply a shared job.
        assert "mutation-tests:" not in ci
        # The bare word `mutmut` renders for EVERY language in two prose comments
        # — the `fuzz` job's (explaining the nightly cron's history) and the
        # scorecard job's ("mirroring how semgrep/mutmut were introduced").
        # Assert the command, not the mention.
        assert "mutmut run" not in ci


class TestVulnerabilityScanGate:
    """PI-568: dependency vulnerability (CVE/advisory) scan per language,
    blocking — part of the single `lint-and-test` job so ci-gate's existing
    `needs: [lint-and-test, ...]` covers it with no gate-list change needed."""

    def test_python_audit_wired(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "python")
        justfile = (target / "justfile").read_text()
        assert "audit:" in justfile
        assert "pip-audit" in justfile
        assert "ci: setup lint typecheck test-cov audit" in justfile

        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just audit" in ci

    def test_node_audit_wired(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "node")
        justfile = (target / "justfile").read_text()
        assert "audit:" in justfile
        assert "bun audit" in justfile
        assert "ci: setup lint typecheck test audit" in justfile

        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just audit" in ci

    def test_go_audit_wired(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "go")
        justfile = (target / "justfile").read_text()
        assert "audit:" in justfile
        assert "govulncheck ./..." in justfile
        assert "ci: lint typecheck test-cov audit" in justfile

        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just audit" in ci
        assert "golang.org/x/vuln/cmd/govulncheck" in ci

    def test_rust_audit_wired(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "rust")
        justfile = (target / "justfile").read_text()
        assert "audit:" in justfile
        assert "cargo audit" in justfile
        assert "ci: lint typecheck test-cov audit" in justfile

        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "just audit" in ci
        assert "cargo-audit" in ci

    def test_audit_absent_for_no_language(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "none")
        assert not (target / "justfile").exists()


class TestBashLintGate:
    """PI-562: shellcheck + shfmt gate .agents/**/*.sh regardless of language —
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

        assert "semgrep" not in needs(load_workflow(target), "ci-gate"), (
            "semgrep must stay non-blocking initially"
        )

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
        settings = json.loads((target / ".agents" / "settings.json").read_text())
        assert settings["enabledPlugins"]["pr-review-toolkit@claude-plugins-official"] is True

    def test_agents_md_recommends_review_plugins(self, tmp_target: Path):
        target = _scaffold_language(tmp_target, "python")
        content = (target / "AGENTS.md").read_text()
        assert "pr-review-toolkit" in content
        assert "code-review@claude-plugins-official" in content


class TestFormatGate:
    """PI-726: `just lint` must reject an unformatted file, in every language.

    Every `format` recipe *writes*; none checked. So an unformatted file merged
    green for python, node and rust. Go was the exception all along —
    `.golangci.yml` enables `gofumpt` under `formatters:`, and `golangci-lint
    run` exits 1 on unformatted code (verified against golangci-lint 2.1.6).
    Adding a fourth gate there would be redundant, so Go gets docs, not a check.

    `rust.md` documented `cargo fmt --check` while nothing ran it — a rules file
    promising a gate that did not exist (the map-not-territory failure, #688).
    """

    def _justfile(self, target: Path, language: str) -> str:
        return (_scaffold_language(target, language) / "justfile").read_text(encoding="utf-8")

    def _lint_recipe(self, justfile: str) -> str:
        body = justfile.split("\nlint:", 1)[1]
        return body.split("\n\n", 1)[0]

    def test_python_lint_checks_formatting(self, tmp_target: Path):
        assert "ruff format --check ." in self._lint_recipe(self._justfile(tmp_target, "python"))

    def test_node_lint_checks_formatting(self, tmp_target: Path):
        recipe = self._lint_recipe(self._justfile(tmp_target, "node"))
        assert "@biomejs/biome format ." in recipe
        # Must not WRITE from the lint gate. Verified against biome 2.x:
        # `format .` leaves files byte-identical and exits 1 on a diff, while
        # `--write` mutates. There is no `format --check` flag — biome rejects it
        # with "`--check` is not expected in this context" (PR #728 review).
        assert "--write" not in recipe
        # `biome ci` would also run biome's linter and duplicate eslint.
        assert "biome ci" not in recipe

    def test_rust_lint_checks_formatting(self, tmp_target: Path):
        assert "cargo fmt --check" in self._lint_recipe(self._justfile(tmp_target, "rust"))

    def test_go_relies_on_gofumpt_in_golangci_run(self, tmp_target: Path):
        """Not a missing gate: `run` reports gofumpt findings and exits non-zero."""
        target = _scaffold_language(tmp_target, "go")
        golangci = (target / ".golangci.yml").read_text(encoding="utf-8")
        assert "formatters:" in golangci
        assert "gofumpt" in golangci
        # No redundant `cargo fmt`-style step bolted onto the go lint recipe.
        assert "gofumpt" not in self._lint_recipe((target / "justfile").read_text(encoding="utf-8"))

    def test_format_recipes_still_write(self, tmp_target: Path):
        """The check belongs to `lint`; `format` remains the fixer."""
        for language, writer in (
            ("python", "ruff format ."),
            ("rust", "cargo fmt"),
        ):
            justfile = self._justfile(tmp_target / language, language)
            format_recipe = justfile.split("\nformat:", 1)[1].split("\n\n", 1)[0]
            assert writer in format_recipe

    def test_shipped_python_templates_are_format_clean(self):
        """A fresh scaffold must pass the gate it ships (#698 shipped this bug once).

        `.agents/hooks/dag_workflow.py` was not ruff-format clean, so every new
        python project would have failed `just lint` on day one.
        """
        import subprocess
        import sys

        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "format", "--check", str(root / "templates")],
            capture_output=True,
            text=True,
            check=False,
        )
        # No skip: ruff is a declared dev dependency, so a non-zero exit here is
        # either real drift or a broken invocation. Skipping on rc==2 would let
        # the gate vanish silently — the failure mode this whole PR is about
        # (PR #728 review).
        assert result.returncode == 0, (
            f"ruff format --check exited {result.returncode}\n{result.stdout}{result.stderr}"
        )


class TestTypecheckParity:
    """PI-725: `just typecheck` must mean the same thing in every language.

    Go and rust had no recipe and no CI step. They are not untyped — golangci-lint
    runs go/analysis and clippy drives the compiler front-end — so the fix is a
    uniform command surface, not a new checker.

    The real defect was clippy's SCOPE: without `--all-targets` it checks only
    lib/bin, so a test module with an outright type error passed `just lint` with
    exit 0 (verified against clippy 0.1.97). `-D missing_docs` cannot be combined
    with `--all-targets` — it then demands a crate-level `//!` in every
    integration test file — hence two passes.
    """

    def _justfile(self, target: Path, language: str) -> str:
        return (_scaffold_language(target, language) / "justfile").read_text(encoding="utf-8")

    @staticmethod
    def _recipe_body(justfile: str, name: str) -> str:
        """A missing recipe must FAIL with a clear message, not IndexError out of
        a chained split (PR #734 review). Mirrors tests/contracts/test_justfile.py.
        """
        match = re.search(rf"^{name}:.*\n((?:[ \t]+.*\n?)*)", justfile, re.MULTILINE)
        assert match, f"recipe {name!r} not found in the scaffolded justfile"
        return match.group(1)

    def test_clippy_covers_tests_benches_examples(self, tmp_target: Path):
        justfile = self._justfile(tmp_target, "rust")
        assert "cargo clippy --all-targets --all-features" in justfile

    def test_missing_docs_is_not_applied_to_all_targets(self, tmp_target: Path):
        """It would demand `//!` in every tests/*.rs — a born-red scaffold."""
        justfile = self._justfile(tmp_target, "rust")
        for line in justfile.splitlines():
            if "--all-targets" in line and "clippy" in line:
                assert "missing_docs" not in line, line

    @pytest.mark.parametrize(
        ("language", "command"),
        [
            ("rust", "cargo check --all-targets --all-features"),
            ("go", "go vet ./..."),
        ],
    )
    def test_typecheck_recipe_exists(self, tmp_target: Path, language: str, command: str):
        justfile = self._justfile(tmp_target / language, language)
        assert command in self._recipe_body(justfile, "typecheck")

    @pytest.mark.parametrize("language", ["go", "rust"])
    def test_ci_runs_typecheck(self, tmp_target: Path, language: str):
        target = _scaffold_language(tmp_target / language, language)
        ci = (target / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "just typecheck" in ci

    @pytest.mark.parametrize("language", ["python", "node", "go", "rust"])
    def test_ci_alias_includes_typecheck(self, tmp_target: Path, language: str):
        """`just ci` is documented as "what CI runs". Go and rust omitted
        typecheck, so the local gate diverged from CI the moment CI gained the
        step (PR #734 review).
        """
        justfile = self._justfile(tmp_target / language, language)
        # Assert the alias exists before reading it — a bare `next()` would raise
        # StopIteration and read as a test error, not a contract failure
        # (PR #734 review; same shape as the _recipe_body fix above).
        ci_lines = [ln for ln in justfile.splitlines() if ln.startswith("ci:")]
        assert ci_lines, f"{language}: no `ci:` alias in the scaffolded justfile"
        assert "typecheck" in ci_lines[0], ci_lines[0]

    def test_go_typecheck_step_comes_after_just_is_installed(self, tmp_target: Path):
        """PR #734 review (P1): it invokes a justfile recipe. Ordered before
        `Install just`, it failed with `just: command not found` on a fresh runner.
        """
        target = _scaffold_language(tmp_target, "go")
        names = [s.get("name") for s in steps(job(load_workflow(target), "lint-and-test"))]
        assert "Install just" in names and "Typecheck" in names, names
        assert names.index("Install just") < names.index("Typecheck"), names

    def test_go_typecheck_is_guarded_for_a_source_less_module(self, tmp_target: Path):
        """PR #734 review (P2): `go vet ./...` exits 1 on a module with no .go
        files (`no packages to vet`, verified). A fresh scaffold must not be red;
        the sibling recipes (test-cov, license, fuzz) already guard the same way.
        """
        recipe = self._recipe_body(self._justfile(tmp_target, "go"), "typecheck")
        assert 'find . -name "*.go"' in recipe
        assert "nothing to type-check" in recipe

class TestTypeScriptSecurityGate:
    """PI-729: TS had no blocking security lint; semgrep was its only SAST, non-blocking.

    Python runs ruff's `S` (bandit) rules on every `just lint`. TS had no
    equivalent, so a fresh repo could merge with OWASP-class findings.

    The subtlety these assertions exist for: `eslint-plugin-security`'s
    recommended preset sets its rules to **warn**, and eslint exits 0 on
    warnings. Installing the plugin without pinning severities yields a gate that
    never blocks — the exact defect #729 describes, reintroduced.
    """

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = _scaffold_language(tmp_target, "node")
        self.config = (self.target / "eslint.config.mjs").read_text(encoding="utf-8")
        self.justfile = (self.target / "justfile").read_text(encoding="utf-8")

    def test_security_plugins_installed_by_setup(self):
        assert "eslint-plugin-security" in self.justfile
        assert "eslint-plugin-no-unsanitized" in self.justfile

    @pytest.mark.parametrize(
        "rule",
        [
            "security/detect-eval-with-expression",
            "security/detect-child-process",
            "security/detect-non-literal-fs-filename",
            "security/detect-unsafe-regex",
            "no-unsanitized/method",
            "no-unsanitized/property",
        ],
    )
    def test_security_rules_pinned_to_error(self, rule: str):
        """`warn` would exit 0. The gate must block."""
        assert f'"{rule}": "error"' in self.config, f"{rule} must be pinned to error, not inherited"

    @pytest.mark.parametrize(
        "rule",
        [
            "@typescript-eslint/no-floating-promises",
            "@typescript-eslint/no-misused-promises",
            "@typescript-eslint/no-unsafe-assignment",
            "@typescript-eslint/no-unsafe-call",
            "@typescript-eslint/no-unsafe-member-access",
            "@typescript-eslint/no-unsafe-return",
            "@typescript-eslint/no-unsafe-argument",
        ],
    )
    def test_type_aware_security_rules_are_explicit_not_inherited(self, rule: str):
        """They come from strictTypeChecked today; an upstream change could drop them."""
        assert f'"{rule}": "error"' in self.config

    def test_ci_seeds_the_lint_toolchain_for_upgraded_projects(self):
        """PR #731 review (Codex P1): `bun install` cannot add what package.json
        never listed. An upgraded project's lockfile predates the new eslint
        plugins, so eslint.config.mjs fails to import and `just lint` exits 2 —
        a crash, before any gate runs. Verified: exit 2 before, 1 after.
        """
        ci = (self.target / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        step = ci.split("Install dependencies", 1)[1].split("- name:", 1)[0]
        assert "just setup" in step
        # Every plugin eslint.config.mjs imports must be probed — a partially
        # upgraded project with one and not the other would skip the seed and
        # still crash at import time (PR #731 review).
        for plugin in ("eslint-plugin-security", "eslint-plugin-no-unsanitized"):
            assert plugin in step, f"{plugin} not probed by the toolchain guard"

    def test_security_plugins_registered_in_the_typescript_block(self):
        """Pinning a rule whose plugin was registered by a preset re-couples the
        gate to that preset's shape — the coupling the pins remove.
        """
        assert 'plugins: { tsdoc, security, "no-unsanitized": noUnsanitized }' in self.config

    def test_setup_recipe_is_a_single_valid_command(self):
        """PR #731 review: a reviewer read the trailing `\\` as a shell parse error.

        `just` joins backslash-continued recipe lines into ONE command — verified
        with `just -n setup`, which prints a single `bun add -d …` line and exits
        0. Pinned so the continuation is not "fixed" into a broken one-liner.
        """
        setup = self.justfile.split("\nsetup:", 1)[1].split("\n\n", 1)[0]
        # Executable lines only — the recipe's own comments mention `bun add`.
        commands = [
            ln.strip() for ln in setup.splitlines() if ln.strip() and not ln.strip().startswith("#")
        ]
        assert commands, setup
        assert commands[0].startswith("bun add -d"), commands
        # One invocation, however the line is wrapped.
        assert sum(c.startswith("bun add") for c in commands) == 1, commands

    def test_typescript_pinned_below_7(self):
        """PI-732: unpinned `bun add -d typescript` resolves to TS 7, which
        typescript-eslint cannot parse — eslint exits 2 (crash), not 1.
        """
        assert '"typescript@^5"' in self.justfile
        assert "bun add -d eslint typescript " not in self.justfile
