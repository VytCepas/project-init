"""PI-322 (epic #316, ADR-015): library delivery ships a release workflow whose
publish job is DISABLED by default (gated on PUBLISH_ENABLED), so a fresh
scaffold never fails a release pushing to an unwired registry."""

from __future__ import annotations

from pathlib import Path

import yaml

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


def _library(target: Path, language: str = "python") -> Path:
    flags = {"python": "", "node": "", "go": ""}
    flags[language] = "true"
    return _scaffold(
        target, delivery="library", delivery_library="true", language=language, **flags
    )


def _release(target: Path) -> Path:
    return target / ".github" / "workflows" / "release.yml"


class TestLibraryRelease:
    def test_release_workflow_present_for_library(self, tmp_path: Path):
        assert _release(_library(tmp_path / "lib")).is_file()

    def test_publish_is_disabled_by_default(self, tmp_path: Path):
        text = _release(_library(tmp_path / "lib")).read_text()
        assert "vars.PUBLISH_ENABLED == 'true'" in text  # gated → inert by default

    def test_release_workflow_is_valid_yaml(self, tmp_path: Path):
        doc = yaml.safe_load(_release(_library(tmp_path / "lib")).read_text())
        assert "release" in doc["jobs"] and "publish" in doc["jobs"]

    def test_python_library_uses_trusted_publishing(self, tmp_path: Path):
        text = _release(_library(tmp_path / "lib", "python")).read_text()
        assert "pypa/gh-action-pypi-publish" in text
        assert "id-token: write" in text

    def test_absent_for_service_and_prototype(self, tmp_path: Path):
        svc = _scaffold(tmp_path / "svc", delivery="service", delivery_service="true")
        proto = _scaffold(tmp_path / "proto", delivery="prototype")
        assert not _release(svc).exists()
        assert not _release(proto).exists()
