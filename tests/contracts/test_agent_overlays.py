"""PI-137: opt-in multi-agent overlays (Codex, Gemini, Ollama tier)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.__main__ import agent_layers, resolve_agents
from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_SKILLS = _REPO_ROOT / "templates" / "fallback" / "dot_claude" / "skills"
_CODEX_SKILLS = _REPO_ROOT / "templates" / "codex" / "dot_agents" / "skills"
_ANTIGRAVITY_SKILLS = _REPO_ROOT / "templates" / "antigravity" / "dot_agents" / "skills"


def _scaffold_agents(target: Path, *agent_names: str) -> Path:
    agents = ["claude", *agent_names]
    preset = load_preset("obsidian-only")
    preset = {**preset, "layers": list(preset["layers"]) + agent_layers(agents)}
    overrides = {
        "agents": ",".join(agents),
        "codex": "true" if "codex" in agents else "",
        "ollama": "true" if "ollama" in agents else "",
        "multi_agent": "true"
        if any(a in agents for a in ("codex", "antigravity", "cursor"))
        else "",
        "other_agents": "true" if len(agents) > 1 else "",
    }
    scaffold(target, preset, make_variables(**overrides), strict=True)
    return target


class TestAgentSelection:
    def test_claude_always_included_and_ordered(self):
        assert resolve_agents("antigravity,codex") == ["claude", "codex", "antigravity"]
        assert resolve_agents("claude") == ["claude"]

    def test_unknown_agent_rejected(self):
        with pytest.raises(ValueError, match="windsurf"):
            resolve_agents("codex,windsurf")

    def test_wizard_reprompts_on_invalid_agents(self, monkeypatch, capsys):
        """An invalid interactive selection must re-prompt, not silently
        fall back to claude-only (PR #167 review)."""
        import project_init.__main__ as cli

        answers = iter(
            ["proj", "desc", "python", "@owner", "none", "codex,windsurf", "codex"]
        )
        monkeypatch.setattr(cli, "_prompt", lambda *a, **k: next(answers))
        monkeypatch.setattr(cli, "_choose_mcps_interactive", lambda catalog: [])
        monkeypatch.setattr(cli, "_choose_browser_interactive", lambda: False)
        monkeypatch.setattr(cli, "_choose_delivery_interactive", lambda language: "prototype")
        monkeypatch.setattr(cli, "_choose_iac_interactive", lambda: "none")
        monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)

        result = cli._gather_inputs_interactive(
            default_name="proj", no_plugin=False, profile="individual"
        )
        assert result.agents == ["claude", "codex"], "valid retry must be honored"
        assert "unknown agent(s): windsurf" in capsys.readouterr().out

    def test_only_codex_and_antigravity_contribute_layers(self):
        assert agent_layers(["claude", "codex", "antigravity", "ollama"]) == [
            "codex",
            "antigravity",
        ]
        assert agent_layers(["claude", "ollama"]) == []

    def test_overlay_layers_is_the_single_source(self):
        """PI-189: scaffold and upgrade derive overlay layers from one helper,
        which accepts a list or a comma-string and prepends fallback."""
        from project_init.scaffold import overlay_layers

        assert overlay_layers(["claude", "codex"], no_plugin=False) == ["codex"]
        assert overlay_layers("claude,codex,antigravity", no_plugin=False) == [
            "codex",
            "antigravity",
        ]
        assert overlay_layers(["claude"], no_plugin=True) == ["fallback"]
        assert overlay_layers("claude,antigravity", no_plugin=True) == [
            "fallback",
            "antigravity",
        ]
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


class TestAntigravityOverlay:
    """PI-386: Antigravity is the Google surface — ships .agents/skills (layer) +
    .agents/hooks.json (+ MCP) via surfaces; the dead Gemini-CLI overlay is gone."""

    def test_ships_agents_skills(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "antigravity")
        skills = sorted((target / ".agents" / "skills").glob("*/SKILL.md"))
        assert skills, "antigravity overlay must ship .agents/skills"
        for skill in skills:
            source = _TEMPLATE_SKILLS / skill.parent.name / "SKILL.md"
            assert skill.read_bytes() == source.read_bytes()

    def test_emits_hooks(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "antigravity")
        config = json.loads((target / ".agents" / "hooks.json").read_text())
        entry = config["safety-gate"]["PreToolUse"][0]
        assert "agent_guard_adapter.py antigravity" in entry["hooks"][0]["command"]

    def test_no_dead_gemini_cli_artifacts(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "antigravity")
        assert not (target / ".gemini-extension").exists()
        assert not (target / ".claude" / "scripts" / "setup_gemini.sh").exists()


class TestOllamaTier:
    def test_instructions_level_only(self, tmp_path: Path):
        """Ollama adds documentation, never agent-specific wiring."""
        target = _scaffold_agents(tmp_path / "p", "ollama")
        assert not (target / ".agents").exists()
        assert not (target / ".codex").exists()
        agents_md = (target / "AGENTS.md").read_text()
        assert "Ollama-based agents" in agents_md


class TestSupportTierDocs:
    def test_caveat_stated_for_any_overlay(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "codex", "antigravity")
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

    def test_antigravity_skill_sources_in_sync(self):
        template = {p.parent.name: p for p in _TEMPLATE_SKILLS.glob("*/SKILL.md")}
        antigravity = {p.parent.name: p for p in _ANTIGRAVITY_SKILLS.glob("*/SKILL.md")}
        assert set(template) == set(antigravity)
        for name, path in template.items():
            assert antigravity[name].read_bytes() == path.read_bytes(), (
                f"antigravity skill {name} drifted — run `just sync-plugin`"
            )


class TestAgentGuardAdapter:
    """PI-388: the shared adapter translates a dag_workflow deny into each
    surface's dialect, sourced from the documented PreToolUse hookSpecificOutput
    shape. `git push origin main` blocks unconditionally (no redirect script)."""

    def _run_adapter(self, target: Path, dialect: str, command: str) -> dict | None:
        adapter = target / ".claude" / "hooks" / "agent_guard_adapter.py"
        payload = json.dumps({"tool_input": {"command": command}})
        proc = subprocess.run(
            [sys.executable, str(adapter), dialect],
            input=payload,
            capture_output=True,
            text=True,
            cwd=target,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def test_codex_emits_documented_pretooluse_schema(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "codex")
        out = self._run_adapter(target, "codex", "git push origin main")
        hso = out["hookSpecificOutput"]
        assert hso["hookEventName"] == "PreToolUse"
        assert hso["permissionDecision"] == "deny"
        assert "main/master" in hso["permissionDecisionReason"]

    def test_antigravity_emits_decision_deny(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "antigravity")
        out = self._run_adapter(target, "antigravity", "git push origin main")
        assert out["decision"] == "deny"
        assert "main/master" in out["reason"]

    def test_innocuous_command_not_blocked(self, tmp_path: Path):
        target = _scaffold_agents(tmp_path / "p", "codex")
        assert self._run_adapter(target, "codex", "ls -la") is None
