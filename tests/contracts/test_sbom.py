"""#574: generate a CycloneDX SBOM per language, attached to GitHub Releases.

release.yml (library delivery) generates a CycloneDX SBOM with each ecosystem's
native generator and attaches it to the Release. A `just sbom` recipe generates
one on demand regardless of delivery mode. The per-language rules doc mentions it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


def _library(target: Path, language: str) -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    return _scaffold(target, delivery="library", delivery_library="true", language=language, **flags)


def _release(target: Path) -> str:
    return (target / ".github" / "workflows" / "release.yml").read_text()


# The generator each ecosystem's SBOM step must invoke (all verified working).
GENERATORS = {
    "python": "cyclonedx-py environment",
    "node": "@cyclonedx/cdxgen",
    "go": "cyclonedx-gomod",
    "rust": "cargo cyclonedx",
}


class TestReleaseSbom:
    @pytest.mark.parametrize("language", list(GENERATORS))
    def test_release_generates_sbom(self, tmp_path: Path, language: str):
        release = _release(_library(tmp_path / language, language))
        assert "Generate CycloneDX SBOM" in release
        assert GENERATORS[language] in release

    @pytest.mark.parametrize("language", list(GENERATORS))
    def test_sbom_attached_to_release(self, tmp_path: Path, language: str):
        release = _release(_library(tmp_path / language, language))
        # The Release step's files: list globs every generated CycloneDX file.
        assert "*.cdx.json" in release

    def test_node_uses_cdxgen_not_cyclonedx_npm(self, tmp_path: Path):
        """cyclonedx-npm shells out to npm and rejects bun, so cdxgen is used."""
        release = _release(_library(tmp_path / "node", "node"))
        assert "-t bun" in release
        # The generator actually invoked is cdxgen, never a cyclonedx-npm command
        # (the string may appear in an explanatory comment, so check invocations).
        assert "bunx @cyclonedx/cdxgen" in release
        assert "bunx @cyclonedx/cyclonedx-npm" not in release

    @pytest.mark.parametrize("language", list(GENERATORS))
    def test_renders_cleanly(self, tmp_path: Path, language: str):
        release = _release(_library(tmp_path / language, language))
        assert "{{#if" not in release and "{{/if" not in release


class TestSbomRecipe:
    @pytest.mark.parametrize(
        "language,needle",
        [
            ("python", "cyclonedx-py environment"),
            ("node", "@cyclonedx/cdxgen"),
            ("go", "cyclonedx-gomod"),
            ("rust", "cargo cyclonedx"),
        ],
    )
    def test_sbom_recipe_present(self, tmp_path: Path, language: str, needle: str):
        flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
        justfile = (_scaffold(tmp_path / language, language=language, **flags) / "justfile").read_text()
        assert "sbom:" in justfile
        assert needle in justfile

    def test_recipe_present_regardless_of_delivery(self, tmp_path: Path):
        # SBOM-on-demand is not tied to library delivery; a prototype has it too.
        justfile = (_scaffold(tmp_path / "proto", delivery="prototype") / "justfile").read_text()
        assert "sbom:" in justfile


class TestSbomDocumented:
    @pytest.mark.parametrize(
        "language,rules_file",
        [("python", "python.md"), ("node", "node.md"), ("go", "go.md"), ("rust", "rust.md")],
    )
    def test_rules_mention_sbom(self, tmp_path: Path, language: str, rules_file: str):
        flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
        target = _scaffold(tmp_path / language, language=language, **flags)
        rules = (target / ".claude" / "rules" / rules_file).read_text()
        assert "sbom" in rules.lower() or "cyclonedx" in rules.lower()
