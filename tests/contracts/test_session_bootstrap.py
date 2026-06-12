"""PI-146: SessionStart bootstrap hook and opt-in devcontainer overlay."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, fallback_preset(), fallback_variables(**overrides), strict=True)
    return target


class TestSessionStartHook:
    def test_hook_scaffolded_executable_and_wired(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        hook = target / ".claude" / "hooks" / "session_setup.sh"
        assert hook.exists()
        assert os.access(hook, os.X_OK), "shell hooks must carry the executable bit"

        settings = json.loads((target / ".claude" / "settings.json").read_text())
        session_start = settings["hooks"]["SessionStart"]
        commands = [h["command"] for entry in session_start for h in entry["hooks"]]
        assert any("session_setup.sh" in c for c in commands)

    def test_stamp_is_gitignored(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        assert ".claude/.session_setup_stamp" in (target / ".gitignore").read_text()

    def test_hook_never_blocks_the_session(self, tmp_path: Path):
        """No `set -e`, and the script's only exit paths are code 0."""
        target = _scaffold(tmp_path / "p")
        script = (target / ".claude" / "hooks" / "session_setup.sh").read_text()
        assert "set -uo pipefail" in script
        assert "set -euo" not in script


class TestDevcontainerOverlay:
    def test_absent_by_default(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        assert not (target / ".devcontainer").exists()

    def test_rendered_when_opted_in(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", devcontainer="true")
        config = json.loads((target / ".devcontainer" / "devcontainer.json").read_text())
        assert config["name"] == "my-project"
        assert "post-create.sh" in config["postCreateCommand"]
        assert (target / ".devcontainer" / "post-create.sh").exists()

    @pytest.mark.parametrize(
        ("language", "marker", "absent"),
        [
            ("python", "astral.sh/uv", "bun.sh/install"),
            ("node", "bun.sh/install", "astral.sh/uv"),
        ],
    )
    def test_post_create_matches_language(
        self, tmp_path: Path, language: str, marker: str, absent: str
    ):
        flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go")}
        target = _scaffold(
            tmp_path / language, devcontainer="true", language=language, **flags
        )
        script = (target / ".devcontainer" / "post-create.sh").read_text()
        assert marker in script
        assert absent not in script
        assert "just.systems/install.sh" in script, "just is always installed"
        assert "session_setup.sh" in script, "must reuse the SessionStart bootstrap"

    def test_go_uses_official_feature(self, tmp_path: Path):
        target = _scaffold(
            tmp_path / "go", devcontainer="true",
            language="go", python="", go="true",
        )
        config = json.loads((target / ".devcontainer" / "devcontainer.json").read_text())
        assert "ghcr.io/devcontainers/features/go:1" in config.get("features", {})

    def test_non_go_has_no_features_block(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", devcontainer="true")
        config = json.loads((target / ".devcontainer" / "devcontainer.json").read_text())
        assert "features" not in config
