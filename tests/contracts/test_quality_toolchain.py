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

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold_language(target: Path, language: str) -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go")}
    scaffold(target, load_preset("obsidian-only"), make_variables(language=language, **flags))
    return target


class TestPythonToolchain:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = _scaffold_language(tmp_target, "python")

    def test_ruff_config_rendered_and_parseable(self):
        config = tomllib.loads((self.target / "ruff.toml").read_text())
        select = config["lint"]["select"]
        for rule in ("D", "C901", "PLR0912", "PLR0913", "PLR0915"):
            assert rule in select, f"{rule} missing from scaffolded ruff select"
        assert config["lint"]["pydocstyle"]["convention"] == "google"
        assert config["lint"]["mccabe"]["max-complexity"] == 10

    def test_ruff_exempts_tests_and_agent_infra(self):
        config = tomllib.loads((self.target / "ruff.toml").read_text())
        ignores = config["lint"]["per-file-ignores"]
        assert "D" in ignores["tests/**"]
        assert "C901" in ignores[".claude/**"]

    def test_mkdocs_config_rendered(self):
        content = (self.target / "mkdocs.yml").read_text()
        assert "name: material" in content
        assert "mkdocstrings" in content
        assert "docstring_style: google" in content
        assert "Zensical" in content, "migration note for mkdocs-material maintenance mode"

    def test_docs_workflow_uses_mkdocs(self):
        content = (self.target / ".github" / "workflows" / "docs.yml").read_text()
        assert "mkdocs build" in content
        assert "actions/deploy-pages" in content

    def test_no_other_language_configs(self):
        assert not (self.target / "eslint.config.mjs").exists()
        assert not (self.target / ".golangci.yml").exists()
        assert not (self.target / "typedoc.json").exists()


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

    def test_typedoc_config_rendered_and_parseable(self):
        raw = (self.target / "typedoc.json").read_text()
        uncommented = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)
        config = json.loads(uncommented)
        assert config["entryPoints"]
        assert config["validation"]["notDocumented"] is True

    def test_docs_workflow_uses_typedoc(self):
        content = (self.target / ".github" / "workflows" / "docs.yml").read_text()
        assert "typedoc" in content
        assert "actions/deploy-pages" in content

    def test_no_other_language_configs(self):
        assert not (self.target / "ruff.toml").exists()
        assert not (self.target / "mkdocs.yml").exists()
        assert not (self.target / ".golangci.yml").exists()


class TestGoToolchain:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = _scaffold_language(tmp_target, "go")

    def test_golangci_config_rendered(self):
        content = (self.target / ".golangci.yml").read_text()
        assert 'version: "2"' in content
        for linter in ("revive", "godoclint", "gocognit"):
            assert linter in content, f"{linter} missing from .golangci.yml"

    def test_no_docs_workflow(self):
        """Go needs no docs site — pkg.go.dev renders doc comments."""
        assert not (self.target / ".github" / "workflows" / "docs.yml").exists()

    def test_no_other_language_configs(self):
        assert not (self.target / "ruff.toml").exists()
        assert not (self.target / "eslint.config.mjs").exists()
        assert not (self.target / "typedoc.json").exists()


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
            ".github/workflows/docs.yml",
        ):
            assert not (target / name).exists(), f"{name} must not render for language=none"

    def test_strict_mode_skips_empty_renders(self, tmp_target: Path):
        """Strict mode must not trip over language-gated files rendering empty."""
        flags = {lang: "" for lang in ("python", "node", "go")}
        created = scaffold(
            tmp_target,
            load_preset("obsidian-only"),
            make_variables(language="none", **flags),
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
        for section in ("Context and Problem Statement", "Considered Options", "Decision Outcome", "Consequences"):
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
        assert "--cov-fail-under" in self.ci
        assert "pytest_cov" in self.ci, "gate must activate only when pytest-cov is installed"

    def test_mutmut_job_present_but_commented(self):
        assert "mutmut" in self.ci
        for line in self.ci.splitlines():
            if "mutmut" in line:
                assert line.lstrip().startswith("#"), f"mutmut must stay commented: {line!r}"


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
