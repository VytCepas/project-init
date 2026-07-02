"""#575: SLSA build provenance attestation on release artifacts.

The library release job attests the built wheel/sdist; the delivery=service
deploy/registry workflows attest the pushed container-image digest. Every path
uses actions/attest-build-provenance (first-party, OIDC + Sigstore, SLSA Build
L3) and grants the id-token + attestations permissions it needs.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


def _library(target: Path, language: str = "python") -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    return _scaffold(target, delivery="library", delivery_library="true", language=language, **flags)


def _service_deploy(target: Path, deploy: str) -> Path:
    container = deploy in ("cloud-run", "fly", "k8s", "custom")
    return _scaffold(
        target,
        delivery="service",
        delivery_service="true",
        language="python",
        deploy_target=deploy,
        deploy_enabled="true" if deploy != "none" else "",
        deploy_container="true" if container else "",
        deploy_registry="true" if deploy == "registry" else "",
        deploy_cloud_run="true" if deploy == "cloud-run" else "",
        deploy_fly="true" if deploy == "fly" else "",
        deploy_k8s="true" if deploy == "k8s" else "",
    )


class TestReleaseArtifactProvenance:
    def test_python_release_attests_wheel_and_sdist(self, tmp_path: Path):
        release = (_library(tmp_path / "lib") / ".github" / "workflows" / "release.yml").read_text()
        assert "actions/attest-build-provenance" in release
        assert "dist/*.whl" in release and "dist/*.tar.gz" in release

    def test_release_job_has_attestation_permissions(self, tmp_path: Path):
        release = (_library(tmp_path / "lib") / ".github" / "workflows" / "release.yml").read_text()
        assert "id-token: write" in release
        assert "attestations: write" in release
        # contents: write must be restated at job level (perms override).
        assert "contents: write" in release

    def test_release_process_documents_verify(self, tmp_path: Path):
        release = (_library(tmp_path / "lib") / ".github" / "workflows" / "release.yml").read_text()
        assert "gh attestation verify" in release
        assert "SLSA" in release

    def test_renders_cleanly(self, tmp_path: Path):
        release = (_library(tmp_path / "lib") / ".github" / "workflows" / "release.yml").read_text()
        assert "{{#if" not in release and "{{/if" not in release


class TestContainerImageProvenance:
    def test_deploy_attests_image_digest(self, tmp_path: Path):
        deploy = (_service_deploy(tmp_path / "svc", "cloud-run") / ".github" / "workflows" / "deploy.yml").read_text()
        assert "actions/attest-build-provenance" in deploy
        assert "subject-digest: ${{ steps.build.outputs.digest }}" in deploy
        assert "push-to-registry: true" in deploy
        assert "id-token: write" in deploy
        assert "attestations: write" in deploy

    def test_registry_publish_attests_image_digest(self, tmp_path: Path):
        reg = (_service_deploy(tmp_path / "reg", "registry") / ".github" / "workflows" / "registry-publish.yml").read_text()
        assert "actions/attest-build-provenance" in reg
        # The build step needs an id so its digest output can be referenced.
        assert "id: build" in reg
        assert "subject-digest: ${{ steps.build.outputs.digest }}" in reg
        assert "push-to-registry: true" in reg
        assert "id-token: write" in reg
        assert "attestations: write" in reg

    def test_renders_cleanly(self, tmp_path: Path):
        deploy = (_service_deploy(tmp_path / "svc", "fly") / ".github" / "workflows" / "deploy.yml").read_text()
        assert "{{#if" not in deploy and "{{/if" not in deploy
