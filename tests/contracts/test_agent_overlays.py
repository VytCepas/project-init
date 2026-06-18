"""PI-137: opt-in multi-agent overlays (Codex, Gemini, Ollama tier)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from project_init.__main__ import agent_layers, resolve_agents
from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_SKILLS = _REPO_ROOT / "templates" / "fallback" / "dot_claude" / "skills"
_CODEX_SKILLS = _REPO_ROOT / "templates" / "codex" / "dot_agents" / "skills"
_GEMINI_COMMANDS = (
    _REPO_ROOT / "templates" / "gemini" / "dot_gemini-extension" / "commands"
)


def _scaffold_agents(target: Path, *agent_names: str) -> Path:
    agents = ["claude", *agent_names]
    preset = load_preset("obsidian-only")
    preset = {**preset, "layers": list(preset["layers"]) + agent_layers(agents)}
    overrides = {
        "agents": ",".join(agents),
        "codex": "true" if "codex" in agents else "",
        "gemini": "true" if "gemini" in agents else "",
        "ollama": "true" if "ollama" in agents else "",
        "multi_agent": "true" if ("codex" in agents or "gemini" in agents) else "",
        "other_agents": "true" if len(agents) > 1 else "",
    }
    scaffold(target, preset, make_variables(**overrides), strict=True)
    return target


class TestAgentSelection:
    def test_claude_always_included_and_ordered(self):
        assert resolve_agents("gemini,codex") == ["claude", "codex", "gemini"]
        assert resolve_agents("claude") == ["claude"]

    def test_unknown_agent_rejected(self):
        with pytest.raises(ValueError, match="cursor"):
            resolve_agents("codex,cursor")

    def test_wizard_reprompts_on_invalid_agents(self, monkeypatch, capsys):
        """An invalid interactive selection must re-prompt, not silently
        fall back to claude-only (PR #167 review)."""
        import project_init.__main__ as cli

        answers = iter(
            ["proj", "desc", "python", "@owner", "none", "codex,cursor", "codex"]
        )
        monkeypatch.setattr(cli, "_prompt", lambda *a, **k: next(answers))
        monkeypatch.setattr(cli, "_choose_mcps_interactive", lambda catalog: [])
        monkeypatch.setattr(cli, "_choose_db_interactive", lambda: None)
        monkeypatch.setattr(cli, "_choose_browser_interactive", lambda: False)
        monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)

        result = cli._gather_inputs_interactive(
            default_name="proj", no_plugin=False, profile="individual"
        )
        assert result.agents == ["claude", "codex"], "valid retry must be honored"
        assert "unknown agent(s): cursor" in capsys.readouterr().out

    def test_only_codex_and_gemini_contribute_layers(self):
        assert agent_layers(["claude", "codex", "gemini", "ollama"]) == ["codex", "gemini"]
        assert agent_layers(["claude", "ollama"]) == []

    def test_overlay_layers_is_the_single_source(self):
        """PI-189: scaffold and upgrade derive overlay layers from one helper,
        which accepts a list or a comma-string and prepends fallback."""
        from project_init.scaffold import overlay_layers

        assert overlay_layers(["claude", "codex"], no_plugin=False) == ["codex"]
        assert overlay_layers("claude,codex,gemini", no_plugin=False) == ["codex", "gemini"]
        assert overlay_layers(["claude"], no_plugin=True) == ["fallback"]
        assert overlay_layers("claude,gemini", no_plugin=True) == ["fallback", "gemini"]
        assert overlay_layers(["claude", "ollama"], no_plugin=False) == []
        # agent_layers is now a thin delegator to the shared helper.
        assert agent_layers(["claude", "codex"]) == overlay_layers(
            ["claude", "codex"], no_plugin=False
        )


class TestClaudeOnlyDefault:
    def test_no_agent_overlay_files(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p")
        assert not (target / ".agents").exists()
        assert not (target / ".codex").exists()
        assert not (target / ".gemini-extension").exists()
        assert not (target / ".claude" / "hooks" / "agent_guard_adapter.py").exists()
        assert not (target / ".claude" / "scripts" / "setup_gemini.sh").exists()


class TestCodexOverlay:
    def test_skills_byte_identical_to_shared_source(self, tmp_path: Path):
        """Plugin-mode scaffolds have no .claude/skills copies — the .agents
        copies are compared against the shared source of truth."""
        target = _scaffold_agents(tmp_path / "p", "codex")
        rendered = sorted((target / ".agents" / "skills").glob("*/SKILL.md"))
        assert rendered, "codex overlay must ship skills"
        for skill in rendered:
            source = _TEMPLATE_SKILLS / skill.parent.name / "SKILL.md"
            assert skill.read_bytes() == source.read_bytes()

    def test_hooks_json_wires_adapter(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "codex")
        config = json.loads((target / ".codex" / "hooks.json").read_text())
        (entry,) = config["hooks"]["PreToolUse"]
        command = entry["hooks"][0]["command"]
        assert "agent_guard_adapter.py codex" in command
        assert (target / ".claude" / "hooks" / "agent_guard_adapter.py").is_file()


class TestGeminiOverlay:
    def test_extension_manifest_valid(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "gemini")
        manifest = json.loads(
            (target / ".gemini-extension" / "gemini-extension.json").read_text()
        )
        assert manifest["name"] == "my-project-workflow"
        assert manifest["version"]

    def test_commands_point_at_existing_skills(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "gemini")
        commands = sorted((target / ".gemini-extension" / "commands").glob("*.toml"))
        assert commands, "gemini overlay must ship pointer commands"
        for command in commands:
            parsed = tomllib.loads(command.read_text())
            assert parsed["description"]
            referenced = f".agents/skills/{command.stem}/SKILL.md"
            assert referenced in parsed["prompt"]
            assert (target / referenced).is_file(), (
                "gemini layer must ship the .agents skills it points at"
            )

    def test_hooks_use_gemini_dialect(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "gemini")
        config = json.loads(
            (target / ".gemini-extension" / "hooks" / "hooks.json").read_text()
        )
        (entry,) = config["hooks"]["BeforeTool"]
        assert "agent_guard_adapter.py gemini" in entry["hooks"][0]["command"]

    def test_setup_script_links_extension(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "gemini")
        script = target / ".claude" / "scripts" / "setup_gemini.sh"
        assert "gemini extensions link .gemini-extension" in script.read_text()


class TestOllamaTier:
    def test_instructions_level_only(self, tmp_path: Path):
        """Ollama adds documentation, never agent-specific wiring."""
        target = _scaffold_agents(tmp_path / "p", "ollama")
        assert not (target / ".agents").exists()
        assert not (target / ".codex").exists()
        assert not (target / ".gemini-extension").exists()
        agents_md = (target / "AGENTS.md").read_text()
        assert "Ollama-based agents" in agents_md


class TestSupportTierDocs:
    def test_caveat_stated_for_any_overlay(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "codex", "gemini")
        agents_md = (target / "AGENTS.md").read_text()
        assert "only the Claude Code path is functionally CI-tested" in agents_md
        onboarding = (
            target / ".claude" / "docs" / "guides" / "developer-onboarding.md"
        ).read_text()
        assert "Multi-agent support tiers" in onboarding


class TestSyncedCopiesInRepo:
    """The overlay sources are derived files — `just sync-plugin` keeps them
    aligned with templates/base/dot_claude/skills."""

    def test_codex_skill_sources_in_sync(self):
        template = {
            p.parent.name: p for p in _TEMPLATE_SKILLS.glob("*/SKILL.md")
        }
        codex = {p.parent.name: p for p in _CODEX_SKILLS.glob("*/SKILL.md")}
        assert set(template) == set(codex)
        for name, path in template.items():
            assert codex[name].read_bytes() == path.read_bytes(), (
                f"codex skill {name} drifted — run `just sync-plugin`"
            )

    def test_gemini_command_sources_in_sync(self):
        template_names = {p.parent.name for p in _TEMPLATE_SKILLS.glob("*/SKILL.md")}
        command_names = {p.stem for p in _GEMINI_COMMANDS.glob("*.toml")}
        assert command_names == template_names, "run `just sync-plugin`"
