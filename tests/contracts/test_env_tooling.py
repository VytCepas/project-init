"""PI-140: mise pinning, env/secret pattern, and .vscode overlays."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


class TestMiseOverlay:
    def test_absent_by_default(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        assert not (target / "mise.toml").exists()

    @pytest.mark.parametrize(
        ("language", "tool", "absent"),
        [
            ("python", "python", "go"),
            ("node", "bun", "python"),
            ("go", "go", "bun"),
        ],
    )
    def test_pins_per_language(self, tmp_path: Path, language: str, tool: str, absent: str):
        flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go")}
        target = _scaffold(tmp_path / language, mise="true", language=language, **flags)
        config = tomllib.loads((target / "mise.toml").read_text())
        assert tool in config["tools"]
        assert absent not in config["tools"]
        assert "just" in config["tools"], "just is pinned for every language"

    def test_ownership_rule_documented(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", mise="true")
        mise = (target / "mise.toml").read_text()
        assert "mise  owns toolchain VERSIONS only" in mise
        agents = (target / "AGENTS.md").read_text()
        assert "Ownership boundaries" in agents
        assert "`mise` owns toolchain versions" in agents

    def test_no_tasks_or_env_sections(self, tmp_path: Path):
        """mise owns versions ONLY — tasks/env are deliberately unused."""
        target = _scaffold(tmp_path / "p", mise="true")
        config = tomllib.loads((target / "mise.toml").read_text())
        assert set(config.keys()) == {"tools"}


class TestEnvPattern:
    @pytest.mark.parametrize("preset", ["obsidian-only", "obsidian-lightrag"])
    def test_env_example_rendered_for_every_preset(self, tmp_path: Path, preset: str):
        target = tmp_path / preset
        flags = {"lightrag": "true" if "lightrag" in preset else ""}
        scaffold(target, load_preset(preset), make_variables(**flags), strict=True)
        example = (target / ".env.example").read_text()
        assert "Loading order" in example
        assert "Never commit .env" in example
        if "lightrag" in preset:
            assert "ANTHROPIC_API_KEY=" in example

    def test_env_is_gitignored(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        lines = (target / ".gitignore").read_text().splitlines()
        assert ".env" in lines

    def test_secrets_guide_documents_escalation_without_deps(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        guide = (target / ".claude" / "docs" / "guides" / "secrets.md").read_text()
        for manager in ("sops", "1Password CLI", "Doppler"):
            assert manager in guide
        assert "installs **none**" in guide, "manager choice stays org-specific"


def _scaffold_vscode(target: Path, **overrides: str) -> Path:
    return _scaffold(target, vscode="true", vscode_off="", **overrides)


class TestVscodeOverlay:
    def test_absent_by_default(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        assert not (target / ".vscode").exists()

    def test_minimal_files_only(self, tmp_path: Path):
        target = _scaffold_vscode(tmp_path / "p")
        files = sorted(p.name for p in (target / ".vscode").iterdir())
        assert files == ["extensions.json", "settings.json"]

    def test_python_wires_ruff_format_on_save(self, tmp_path: Path):
        target = _scaffold_vscode(tmp_path / "p")
        settings = json.loads((target / ".vscode" / "settings.json").read_text())
        assert settings["editor.formatOnSave"] is True
        assert settings["[python]"]["editor.defaultFormatter"] == "charliermarsh.ruff"
        extensions = json.loads((target / ".vscode" / "extensions.json").read_text())
        assert "charliermarsh.ruff" in extensions["recommendations"]
        assert "anthropic.claude-code" in extensions["recommendations"]

    def test_go_recommends_go_extension(self, tmp_path: Path):
        target = _scaffold_vscode(
            tmp_path / "go", language="go", python="", go="true"
        )
        extensions = json.loads((target / ".vscode" / "extensions.json").read_text())
        assert "golang.go" in extensions["recommendations"]
        assert "charliermarsh.ruff" not in extensions["recommendations"]

    def test_gitignore_shares_only_scaffolded_files(self, tmp_path: Path):
        target = _scaffold_vscode(tmp_path / "p")
        gitignore = (target / ".gitignore").read_text()
        assert ".vscode/*" in gitignore
        assert "!.vscode/extensions.json" in gitignore
        assert "!.vscode/settings.json" in gitignore

    def test_gitignore_keeps_personal_vscode_ignored_by_default(self, tmp_path: Path):
        """Without --vscode, no unignore rules may leak personal editor
        config into git (PR #163 review)."""
        target = _scaffold(tmp_path / "p")
        gitignore = (target / ".gitignore").read_text()
        assert "\n.vscode/\n" in gitignore
        assert "!.vscode" not in gitignore
