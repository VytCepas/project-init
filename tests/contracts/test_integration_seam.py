"""PI-326 (epic #316, ADR-015): the cloud-integration seam doc ships whenever a
deploy or IaC workflow uses OIDC, documenting the OIDC + env contract a separate
landing-zone product fills. Governance itself stays out of project-init."""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


def _seam(t: Path) -> Path:
    return t / ".claude" / "docs" / "guides" / "cloud-integration.md"


class TestIntegrationSeam:
    def test_present_for_container_deploy(self, tmp_path: Path):
        t = _scaffold(
            tmp_path / "svc",
            delivery="service",
            delivery_service="true",
            deploy="cloud-run",
            deploy_container="true",
            deploy_enabled="true",
            cloud_oidc="true",
        )
        text = _seam(t).read_text()
        assert "OIDC" in text
        assert "GCP_WORKLOAD_IDENTITY_PROVIDER" in text
        assert "out of scope for project-init" in text.lower() or "separate" in text.lower()

    def test_present_for_iac(self, tmp_path: Path):
        t = _scaffold(tmp_path / "iac", iac="opentofu", iac_enabled="true", cloud_oidc="true")
        assert _seam(t).is_file()

    def test_absent_without_deploy_or_iac(self, tmp_path: Path):
        t = _scaffold(tmp_path / "plain")  # defaults: no deploy, no iac
        assert not _seam(t).exists()
