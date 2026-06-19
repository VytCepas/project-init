"""PI-319 (epic #316, ADR-015): the container parity bundle ships only for
delivery=service projects — Dockerfile, compose.yaml, .dockerignore, container
just recipes, and an auto-enabled devcontainer."""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


def _service(target: Path, language: str = "python") -> Path:
    # make_variables sets the python/node/go flags independently of `language`,
    # so set them explicitly to match the requested runtime.
    flags = {"python": "", "node": "", "go": ""}
    flags[language] = "true"
    return _scaffold(
        target,
        delivery="service",
        delivery_service="true",
        want_devcontainer="true",
        language=language,
        **flags,
    )


class TestParityBundlePresent:
    def test_dockerfile_and_compose_render_for_service(self, tmp_path: Path):
        target = _service(tmp_path / "svc")
        assert (target / "Dockerfile").is_file()
        assert (target / "compose.yaml").is_file()
        assert (target / ".dockerignore").is_file()

    def test_dockerfile_uses_language_base_image(self, tmp_path: Path):
        py = _service(tmp_path / "py", "python")
        assert "python:3.13-slim" in (py / "Dockerfile").read_text()
        go = _service(tmp_path / "go", "go")
        assert "golang:1.23" in (go / "Dockerfile").read_text()

    def test_compose_has_app_service_and_no_uncommented_db(self, tmp_path: Path):
        compose = (_service(tmp_path / "svc") / "compose.yaml").read_text()
        assert "app:" in compose
        assert "build: ." in compose
        # backing services are examples only — commented, never live
        assert "\n  postgres:" not in compose

    def test_justfile_has_container_recipes(self, tmp_path: Path):
        justfile = (_service(tmp_path / "svc") / "justfile").read_text()
        assert "up:" in justfile
        assert "docker compose up --build" in justfile
        assert "down:" in justfile

    def test_service_auto_enables_devcontainer(self, tmp_path: Path):
        target = _service(tmp_path / "svc")
        assert (target / ".devcontainer" / "devcontainer.json").is_file()


class TestParityBundleAbsent:
    def test_prototype_has_no_bundle(self, tmp_path: Path):
        target = _scaffold(tmp_path / "proto", delivery="prototype", language="python")
        assert not (target / "Dockerfile").exists()
        assert not (target / "compose.yaml").exists()
        assert not (target / ".dockerignore").exists()
        justfile = target / "justfile"
        if justfile.exists():
            assert "docker compose" not in justfile.read_text()

    def test_library_has_no_bundle(self, tmp_path: Path):
        target = _scaffold(tmp_path / "lib", delivery="library", language="python")
        assert not (target / "Dockerfile").exists()
        assert not (target / "compose.yaml").exists()

    def test_prototype_without_flag_has_no_devcontainer(self, tmp_path: Path):
        target = _scaffold(tmp_path / "proto", delivery="prototype", language="python")
        assert not (target / ".devcontainer" / "devcontainer.json").exists()


class TestBuildOnceCI:
    """PI-320: service CI builds the same image once (tagged by SHA); host-based
    tests stay the pinned location. Prototype/library CI has no image build."""

    def _ci(self, target: Path) -> str:
        return (target / ".github" / "workflows" / "ci.yml").read_text()

    def test_service_ci_builds_image_once(self, tmp_path: Path):
        ci = self._ci(_service(tmp_path / "svc"))
        assert "build-image:" in ci
        assert "docker/build-push-action" in ci
        assert "${{ github.sha }}" in ci
        assert "push: false" in ci  # deploy overlay (#323) wires the push-by-digest

    def test_prototype_ci_has_no_image_build(self, tmp_path: Path):
        ci = self._ci(_scaffold(tmp_path / "proto", delivery="prototype"))
        assert "build-image:" not in ci
        assert "build-push-action" not in ci
