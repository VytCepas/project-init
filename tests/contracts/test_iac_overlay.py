"""PI-325 (epic #316, ADR-015): opt-in IaC overlay — OpenTofu (HCL) skeleton +
plan-on-PR workflow (apply manual/gated). Default OFF; emits no real resources."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


def _iac(target: Path) -> Path:
    return _scaffold(target, iac="opentofu", iac_enabled="true")


class TestIacOverlayPresent:
    def test_hcl_skeleton_renders(self, tmp_path: Path):
        t = _iac(tmp_path / "p")
        for f in ("versions.tf", "main.tf", "variables.tf", "outputs.tf", "backend.tf", "README.md"):
            assert (t / "infra" / f).is_file(), f"missing infra/{f}"

    def test_backend_is_commented_stub(self, tmp_path: Path):
        backend = (_iac(tmp_path / "p") / "infra" / "backend.tf").read_text()
        # Every backend line is commented — no uncommented backend block.
        assert 'backend "s3"' in backend
        assert '# terraform {' in backend
        assert "\nterraform {" not in backend  # not uncommented

    def test_gitignore_keeps_lockfile_tracked(self, tmp_path: Path):
        gi = (_iac(tmp_path / "p") / "infra" / ".gitignore").read_text()
        assert "*.tfstate" in gi
        assert ".terraform.lock.hcl" not in gi.replace("# NOT ignored: .terraform.lock.hcl is committed (provider checksum pinning).", "")

    def test_workflow_uses_opentofu_and_gated_apply(self, tmp_path: Path):
        wf = (_iac(tmp_path / "p") / ".github" / "workflows" / "infra.yml").read_text()
        assert "opentofu/setup-opentofu" in wf
        assert "tofu plan" in wf and "tofu validate" in wf
        assert "environment: infra-apply" in wf          # gated apply
        assert "workflow_dispatch" in wf                  # manual, not on merge
        assert "id-token: write" in wf                    # OIDC

    def test_precommit_targets_tofu(self, tmp_path: Path):
        pc = (_iac(tmp_path / "p") / "infra" / ".pre-commit-config.yaml").read_text()
        assert "pre-commit-terraform" in pc
        assert "terraform_trivy" in pc
        assert "PCT_TFPATH=tofu" in pc  # invoke OpenTofu, not terraform


class TestIacOverlayAbsent:
    def test_none_emits_no_infra(self, tmp_path: Path):
        t = _scaffold(tmp_path / "p", iac="none")
        assert not (t / "infra").exists()
        assert not (t / ".github" / "workflows" / "infra.yml").exists()


class TestResolveIac:
    def test_default_none(self):
        from project_init.__main__ import resolve_iac

        assert resolve_iac(None) == "none"
        assert resolve_iac("") == "none"

    def test_aliases(self):
        from project_init.__main__ import resolve_iac

        assert resolve_iac("tofu") == "opentofu"
        assert resolve_iac("terraform") == "opentofu"

    def test_rejects_unknown(self):
        from project_init.__main__ import resolve_iac

        with pytest.raises(ValueError, match="invalid iac tool"):
            resolve_iac("pulumi")
