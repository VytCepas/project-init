"""PI-323 (epic #316, ADR-015): the opt-in deploy overlay. Services that choose a
container deploy target get a build-once-by-digest deploy.yml + a declarative
deploy/environments.yaml; registry → publish-only; none/non-service → nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.__main__ import resolve_deploy
from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


def _service_deploy(target: Path, deploy: str) -> Path:
    """A delivery=service scaffold with a chosen deploy target's render vars."""
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


def _deploy_yml(t: Path) -> Path:
    return t / ".github" / "workflows" / "deploy.yml"


def _envs(t: Path) -> Path:
    return t / "deploy" / "environments.yaml"


def _registry(t: Path) -> Path:
    return t / ".github" / "workflows" / "registry-publish.yml"


class TestContainerDeploy:
    def test_deploy_files_render(self, tmp_path: Path):
        t = _service_deploy(tmp_path / "svc", "cloud-run")
        assert _deploy_yml(t).is_file()
        assert _envs(t).is_file()
        assert not _registry(t).exists()

    def test_build_once_by_digest_and_gated_prod(self, tmp_path: Path):
        text = _deploy_yml(_service_deploy(tmp_path / "svc", "cloud-run")).read_text()
        assert "environment: staging" in text
        assert "environment: production" in text
        assert "push-by-digest" in text or "outputs.digest" in text  # promote the digest
        assert "gcloud run deploy" in text  # per-target ship stub
        assert "{{#if" not in text and "{{/if" not in text  # rendered cleanly

    def test_environments_yaml_fixed_shape(self, tmp_path: Path):
        text = _envs(_service_deploy(tmp_path / "svc", "fly")).read_text()
        assert "staging:" in text and "production:" in text
        assert "gated: true" in text  # production is the gated one

    def test_fly_and_k8s_stubs(self, tmp_path: Path):
        assert "flyctl deploy" in _deploy_yml(_service_deploy(tmp_path / "f", "fly")).read_text()
        assert "kubectl set image" in _deploy_yml(_service_deploy(tmp_path / "k", "k8s")).read_text()


class TestRegistryAndOff:
    def test_registry_publishes_not_deploys(self, tmp_path: Path):
        t = _service_deploy(tmp_path / "reg", "registry")
        assert _registry(t).is_file()
        assert not _deploy_yml(t).exists()  # registry is publication, not a deploy
        # No environments model either — registry doesn't promote staging→prod (PR #337).
        assert not _envs(t).exists()
        assert "PUBLICATION" in _registry(t).read_text()  # not a deployment

    def test_deploy_none_service_has_no_overlay(self, tmp_path: Path):
        t = _service_deploy(tmp_path / "svc", "none")
        assert not _deploy_yml(t).exists()
        assert not _envs(t).exists()
        assert not _registry(t).exists()

    def test_prototype_has_no_overlay(self, tmp_path: Path):
        t = _scaffold(tmp_path / "proto", delivery="prototype")
        assert not _deploy_yml(t).exists()
        assert not _envs(t).exists()


class TestResolveDeploy:
    def test_default_none(self):
        assert resolve_deploy(None, "service") == "none"
        assert resolve_deploy("", "prototype") == "none"

    def test_target_requires_service(self):
        with pytest.raises(ValueError, match="only to delivery=service"):
            resolve_deploy("cloud-run", "library")
        assert resolve_deploy("cloud-run", "service") == "cloud-run"

    def test_invalid_target(self):
        with pytest.raises(ValueError, match="invalid deploy target"):
            resolve_deploy("heroku", "service")
