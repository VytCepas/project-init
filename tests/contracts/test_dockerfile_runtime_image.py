"""PI-954 / PI-955: the scaffolded service image must be runnable and scannable.

PI-628 removed a contradiction — one Python scaffold emitting three different
answers to "what Python is this project on". `Dockerfile.tmpl` was never wired
into that fix and kept asserting its own fourth answer, a hardcoded
`python:3.13-slim`, while `python_floor` wrote `3.11` to `.python-version`.
`uv sync` honours the pin, downloads its own interpreter into the BUILD stage,
and builds the venv against a path the runtime stage never copies. The image
then runs green on the base interpreter with none of its dependencies, because
`python` resolves PAST a dangling venv entry.

The tests below pin the derivation rather than the literal, so a future
hardcoded tag fails here rather than in someone's container.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "base" / "Dockerfile.tmpl"


def _service(target: Path, language: str = "python", **overrides: str) -> str:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    scaffold(
        target,
        load_preset("obsidian-only"),
        make_variables(
            delivery="service", delivery_service="true", language=language, **flags, **overrides
        ),
        strict=True,
    )
    return (target / "Dockerfile").read_text()


def _python_tags(dockerfile: str) -> list[str]:
    return re.findall(r"^FROM python:([^\s-]+)-slim AS \w+", dockerfile, re.M)


class TestBaseTagFollowsThePin:
    """The tag is DERIVED from python_floor — never a literal."""

    @pytest.mark.parametrize("floor", ["3.11", "3.12", "3.13", "3.14"])
    def test_both_stages_use_the_declared_floor(self, tmp_path: Path, floor: str):
        tags = _python_tags(_service(tmp_path / f"svc{floor}", python_floor=floor))
        assert tags == [floor, floor], (
            f"expected both stages on python:{floor}-slim, got {tags}. A build stage "
            "that disagrees with the pin makes uv download its own interpreter."
        )

    def test_no_hardcoded_python_tag_survives_in_the_template(self):
        """The literal is what regressed; assert on the source, not only a render."""
        hardcoded = re.findall(r"FROM python:(\d+\.\d+)-slim", _TEMPLATE.read_text())
        assert not hardcoded, f"Dockerfile.tmpl hardcodes a python tag: {hardcoded}"

    def test_dockerfile_tag_agrees_with_the_python_version_file(self, tmp_path: Path):
        """The cross-file invariant, end to end through the real CLI.

        `.python-version` is what `uv sync` reads inside the build stage, so these
        two disagreeing IS the defect — not a style question.
        """
        target = tmp_path / "e2e"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "project_init",
                str(target),
                "--non-interactive",
                "--preset",
                "core",
                "--name",
                "t",
                "--description",
                "t",
                "--language",
                "python",
                "--delivery",
                "service",
                "--deploy",
                "none",
                "--no-docs",
                "--no-plugin",
                "--lifecycle",
                "none",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        pin = (target / ".python-version").read_text().strip()
        assert _python_tags((target / "Dockerfile").read_text()) == [pin, pin]


class TestRuntimeStageProvesItself:
    """Both guards fail the BUILD; without them a broken image ships green."""

    def test_runtime_asserts_the_venv_interpreter_resolves(self, tmp_path: Path):
        df = _service(tmp_path / "svc")
        assert "/app/.venv/bin/python -V" in df, (
            "the runtime stage must execute the venv interpreter; a dangling "
            "symlink otherwise reaches production and the app runs on the base "
            "interpreter with none of its dependencies"
        )

    def test_runtime_asserts_pip_is_actually_gone(self, tmp_path: Path):
        assert "! command -v pip" in _service(tmp_path / "svc")

    def test_removal_paths_are_spelled_out_not_brace_expanded(self, tmp_path: Path):
        """RUN uses /bin/sh — dash here — which does NOT brace-expand.

        `rm -rf .../{pip,wheel}` reaches rm as one literal path, matches nothing
        and exits 0, so the removal silently no-ops while the build stays green.
        """
        df = _service(tmp_path / "svc")
        removal = df[df.index("RUN rm -rf") : df.index("ENV PATH=")]
        assert "{" not in removal, f"brace expansion in a /bin/sh RUN: {removal!r}"
        for pkg in ("pip", "setuptools", "wheel", "pkg_resources"):
            assert f"site-packages/{pkg}" in removal, f"{pkg} is not removed"


class TestScopedToPythonServices:
    def test_absent_for_non_service_delivery(self, tmp_path: Path):
        target = tmp_path / "proto"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        assert not (target / "Dockerfile").exists()

    @pytest.mark.parametrize("language", ["node", "go", "rust"])
    def test_other_languages_get_no_python_stage(self, tmp_path: Path, language: str):
        df = _service(tmp_path / language, language=language)
        assert not _python_tags(df)
        assert "site-packages" not in df
