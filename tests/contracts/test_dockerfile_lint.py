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
        copy_idx = next(
            i for i, ln in enumerate(lines) if ln.startswith("COPY --from=ghcr.io/astral-sh/uv")
        )
        assert lines[copy_idx - 1].strip() == "# hadolint ignore=DL3007"

    def test_rust_pipe_guarded(self, tmp_path: Path):
        dockerfile = (_service(tmp_path / "svc", "rust") / "Dockerfile").read_text()
        lines = dockerfile.splitlines()
        run_idx = next(
            i for i, ln in enumerate(lines) if ln.startswith("RUN cargo build --release")
        )
        assert lines[run_idx - 1].strip() == "# hadolint ignore=DL4006"

    @pytest.mark.parametrize("language", ["node", "go"])
    def test_node_and_go_need_no_ignores(self, tmp_path: Path, language: str):
        dockerfile = (_service(tmp_path / language, language) / "Dockerfile").read_text()
        assert "hadolint ignore" not in dockerfile


class TestRuntimeStagesDropRoot:
    """Every runtime stage must end up as a non-root user.

    semgrep's dockerfile.security.missing-user is ON in the CI this scaffolder
    ships, so a Dockerfile without USER makes a freshly scaffolded service fail
    its own security gate on the first run — the template was internally
    inconsistent, shipping a rule and a violation of it together. Observed on a
    scaffolded service: "Ran 286 rules on 253 files: 1 finding", the finding
    being this one, and that single finding was the whole reason its CI was red.

    The uid is NUMERIC on purpose. A named user would need useradd (absent from
    distroless, which has no shell at all) or an assumption about what the base
    image already provides. A numeric uid needs no /etc/passwd entry and is
    correct on every base the template uses.

    Parsed by stage rather than grepped for "USER" anywhere in the file: a USER
    line in the BUILD stage satisfies a substring check while leaving the
    runtime running as root, which is the whole defect.
    """

    @staticmethod
    def _runtime_stages(dockerfile: str) -> dict[str, list[str]]:
        stages: dict[str, list[str]] = {}
        current = None
        for line in dockerfile.split("\n"):
            if line.startswith("FROM "):
                current = line.rstrip().split(" AS ")[-1] if " AS " in line else None
                if current:
                    stages[current] = []
            elif current:
                stages[current].append(line)
        return {k: v for k, v in stages.items() if k == "runtime"}

    @pytest.mark.parametrize("language", ["python", "node", "go", "rust"])
    def test_runtime_stage_sets_a_non_root_user(self, tmp_path: Path, language: str):
        df = (_service(tmp_path / language, language) / "Dockerfile").read_text()
        stages = self._runtime_stages(df)
        assert stages, f"{language}: no runtime stage found"
        body = "\n".join(stages["runtime"])
        users = [ln.split()[1] for ln in body.split("\n") if ln.startswith("USER ")]
        assert users, f"{language}: runtime stage never drops root"
        uid = users[-1].split(":")[0]
        assert uid not in ("root", "0"), f"{language}: last USER is root ({users[-1]})"

    @pytest.mark.parametrize("language", ["python", "node", "go", "rust"])
    def test_user_precedes_the_entrypoint(self, tmp_path: Path, language: str):
        """USER after CMD/ENTRYPOINT is a no-op for the running process."""
        body = "\n".join(
            self._runtime_stages(
                (_service(tmp_path / language, language) / "Dockerfile").read_text()
            )["runtime"]
        )
        lines = body.split("\n")
        user_at = max(i for i, ln in enumerate(lines) if ln.startswith("USER "))
        starts = [i for i, ln in enumerate(lines) if ln.startswith(("CMD ", "ENTRYPOINT "))]
        assert starts, f"{language}: runtime stage has no CMD/ENTRYPOINT"
        assert user_at < min(starts), f"{language}: USER comes after the entrypoint"

    @pytest.mark.parametrize("language", ["python", "node", "go", "rust"])
    def test_copied_tree_is_owned_by_that_uid(self, tmp_path: Path, language: str):
        """Dropping to a uid that cannot read its own files fails at runtime,
        not at build — the worst place to find out."""
        body = "\n".join(
            self._runtime_stages(
                (_service(tmp_path / language, language) / "Dockerfile").read_text()
            )["runtime"]
        )
        copies = [ln for ln in body.split("\n") if ln.startswith("COPY --from=build")]
        assert copies, f"{language}: runtime stage copies nothing from build"
        for c in copies:
            assert "--chown=10001:10001" in c, f"{language}: unowned copy — {c}"
