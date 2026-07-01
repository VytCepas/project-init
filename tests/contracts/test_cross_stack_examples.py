"""PI-493: language/cloud-gated example snippets in service scaffolds.

A Go/GCP scaffold must not carry Python/Node/AWS example noise. The example
placeholders (.env.example loader hint, .dockerignore ignores, devcontainer
PATH, infra/backend.tf) are gated by the existing language/cloud flags. These
assertions lock the gating so a regression — e.g. un-gating the bun PATH or the
Python ignores — fails CI rather than silently leaking cross-stack hints.
"""

from __future__ import annotations

import json
from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _service(target: Path, language: str = "python", **extra: str) -> Path:
    # make_variables sets python/node/go/rust independently of `language` — set
    # them explicitly to match the requested runtime (mirrors test_parity_bundle).
    flags = {"python": "", "node": "", "go": "", "rust": ""}
    flags[language] = "true"
    scaffold(
        target,
        load_preset("obsidian-only"),
        make_variables(
            language=language,
            delivery="service",
            delivery_service="true",
            want_devcontainer="true",
            **flags,
            **extra,
        ),
        strict=True,
    )
    return target


class TestEnvExampleHint:
    def test_python_hint_only(self, tmp_path: Path):
        env = (_service(tmp_path / "p", "python") / ".env.example").read_text()
        assert "For Python: `uv run --env-file .env`" in env
        assert "bun" not in env
        assert "godotenv" not in env

    def test_node_hint_only(self, tmp_path: Path):
        env = (_service(tmp_path / "n", "node") / ".env.example").read_text()
        assert "For Node:" in env
        assert "bun auto-loads" in env
        assert "uv run" not in env
        assert "godotenv" not in env

    def test_go_hint_only_and_never_sources_env(self, tmp_path: Path):
        env = (_service(tmp_path / "g", "go") / ".env.example").read_text()
        assert "For Go:" in env
        assert "godotenv" in env
        assert "uv run" not in env
        assert "bun" not in env
        # Hardening (PR #368): never suggest sourcing the user-editable .env —
        # a stray command in it would execute. Parse, don't source.
        assert "set -a" not in env
        assert ". ./.env" not in env


class TestDockerignoreGating:
    def test_python_blocks_gated(self, tmp_path: Path):
        di = (_service(tmp_path / "p", "python") / ".dockerignore").read_text()
        assert "__pycache__" in di
        assert ".venv" in di
        assert ".mypy_cache" in di
        assert "node_modules" not in di

    def test_node_block_gated(self, tmp_path: Path):
        di = (_service(tmp_path / "n", "node") / ".dockerignore").read_text()
        assert "node_modules" in di
        assert "__pycache__" not in di
        assert ".venv" not in di

    def test_go_has_neither_language_block(self, tmp_path: Path):
        di = (_service(tmp_path / "g", "go") / ".dockerignore").read_text()
        assert "__pycache__" not in di
        assert "node_modules" not in di
        # Generic entries stay for every service language.
        assert "dist" in di
        assert ".env" in di


class TestDevcontainerPath:
    def _path(self, target: Path) -> str:
        config = json.loads((target / ".devcontainer" / "devcontainer.json").read_text())
        return config["remoteEnv"]["PATH"]

    def test_node_includes_bun(self, tmp_path: Path):
        assert ".bun/bin" in self._path(_service(tmp_path / "n", "node"))

    def test_python_omits_bun(self, tmp_path: Path):
        path = self._path(_service(tmp_path / "p", "python"))
        assert ".bun/bin" not in path
        assert ".local/bin" in path  # generic tool dir stays for all

    def test_go_omits_bun(self, tmp_path: Path):
        assert ".bun/bin" not in self._path(_service(tmp_path / "g", "go"))


class TestBackendCloudNeutral:
    def test_shows_both_s3_and_gcs(self, tmp_path: Path):
        backend = (
            _service(tmp_path / "g", "go", iac="opentofu", iac_enabled="true")
            / "infra"
            / "backend.tf"
        ).read_text()
        assert 'backend "s3"' in backend
        assert 'backend "gcs"' in backend
