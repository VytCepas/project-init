"""#578: lint the scaffolded Dockerfile with hadolint (delivery=service only).

A dedicated lightweight CI job runs hadolint against the Dockerfile, and a
`just lint-docker` recipe runs the same check locally. The scaffolded
Dockerfile itself must pass hadolint clean — the two deliberate anti-pattern
exceptions (build-stage `uv:latest`, the pipe in the Rust name extraction) are
guarded with documented inline ignores rather than left to fail the gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


def _service(target: Path, language: str = "python") -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    return _scaffold(
        target, delivery="service", delivery_service="true", language=language, **flags
    )


def _ci(target: Path) -> str:
    return (target / ".github" / "workflows" / "ci.yml").read_text()


class TestHadolintJob:
    def test_job_present_for_service(self, tmp_path: Path):
        ci = _ci(_service(tmp_path / "svc"))
        assert "dockerfile-lint:" in ci
        assert "hadolint/hadolint-action" in ci
        assert "dockerfile: Dockerfile" in ci

    def test_lightweight_no_build_dependency(self, tmp_path: Path):
        """It runs in parallel with build-image, not gated on it — the hadolint
        job must not `needs:` the build."""
        ci = _ci(_service(tmp_path / "svc"))
        start = ci.index("dockerfile-lint:")
        block = ci[start : ci.index("secret-scan:", start)]
        assert "needs:" not in block

    def test_renders_cleanly(self, tmp_path: Path):
        ci = _ci(_service(tmp_path / "svc"))
        assert "{{#if" not in ci
        assert "{{/if" not in ci

    def test_absent_for_prototype_and_library(self, tmp_path: Path):
        proto = _ci(_scaffold(tmp_path / "proto", delivery="prototype"))
        lib = _ci(_scaffold(tmp_path / "lib", delivery="library", delivery_library="true"))
        for ci in (proto, lib):
            assert "hadolint" not in ci
            assert "dockerfile-lint:" not in ci


class TestLintDockerRecipe:
    def test_recipe_present_for_service(self, tmp_path: Path):
        justfile = (_service(tmp_path / "svc") / "justfile").read_text()
        assert "lint-docker:" in justfile
        assert "hadolint Dockerfile" in justfile

    def test_recipe_absent_for_prototype(self, tmp_path: Path):
        justfile = (_scaffold(tmp_path / "proto", delivery="prototype") / "justfile").read_text()
        assert "lint-docker:" not in justfile


class TestDockerfilePassesClean:
    """The two deliberate exceptions are guarded so hadolint's default
    (fail-on-warning) threshold does not trip on the scaffolded Dockerfile."""

    def test_python_uv_latest_guarded(self, tmp_path: Path):
        dockerfile = (_service(tmp_path / "svc", "python") / "Dockerfile").read_text()
        assert "uv:latest" in dockerfile
        # The ignore directive must sit immediately above the COPY it applies to.
        lines = dockerfile.splitlines()
        copy_idx = next(i for i, ln in enumerate(lines) if ln.startswith("COPY --from=ghcr.io/astral-sh/uv"))
        assert lines[copy_idx - 1].strip() == "# hadolint ignore=DL3007"

    def test_rust_pipe_guarded(self, tmp_path: Path):
        dockerfile = (_service(tmp_path / "svc", "rust") / "Dockerfile").read_text()
        lines = dockerfile.splitlines()
        run_idx = next(i for i, ln in enumerate(lines) if ln.startswith("RUN cargo build --release"))
        assert lines[run_idx - 1].strip() == "# hadolint ignore=DL4006"

    @pytest.mark.parametrize("language", ["node", "go"])
    def test_node_and_go_need_no_ignores(self, tmp_path: Path, language: str):
        dockerfile = (_service(tmp_path / language, language) / "Dockerfile").read_text()
        assert "hadolint ignore" not in dockerfile
