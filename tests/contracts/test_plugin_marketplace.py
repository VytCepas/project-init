"""PI-129 / ADR-010: same-repo plugin marketplace, dual-shipped with copies."""

from __future__ import annotations

import json
import re
from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MARKETPLACE = _REPO_ROOT / ".claude-plugin" / "marketplace.json"
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "project-init-workflow"
_TEMPLATE_CLAUDE = _REPO_ROOT / "templates" / "base" / "dot_claude"
_FALLBACK_CLAUDE = _REPO_ROOT / "templates" / "fallback" / "dot_claude"


class TestMarketplaceManifest:
    def test_valid_and_lists_plugin_with_existing_source(self):
        config = json.loads(_MARKETPLACE.read_text())
        assert config["name"] == "project-init"
        assert config["owner"]["name"]
        (entry,) = config["plugins"]
        assert entry["name"] == "project-init-workflow"
        source = entry["source"]
        assert source.startswith("./"), "same-repo plugins use relative sources"
        assert (_REPO_ROOT / source).is_dir()


class TestPluginManifest:
    def test_plugin_json_valid(self):
        manifest = json.loads(
            (_PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert manifest["name"] == "project-init-workflow"
        assert re.match(r"^\d+\.\d+\.\d+$", manifest["version"])
        assert manifest["hooks"] == "./hooks/hooks.json"

    def test_hooks_json_references_only_existing_scripts(self):
        config = json.loads((_PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
        commands = [
            h["command"]
            for entries in config["hooks"].values()
            for entry in entries
            for h in entry["hooks"]
        ]
        assert commands, "plugin must wire at least one hook"
        for command in commands:
            assert "${CLAUDE_PLUGIN_ROOT}" in command
            rel = command.split("${CLAUDE_PLUGIN_ROOT}")[1].strip('"').lstrip("/")
            assert (_PLUGIN_ROOT / rel).is_file(), f"missing hook script: {rel}"

    def test_hook_events_match_template_wiring(self):
        """The plugin wires the same events the scaffolded settings wire, so
        the documented cutover (ADR-010) is a drop-in swap."""
        plugin_events = set(
            json.loads((_PLUGIN_ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        )
        template_settings = (_TEMPLATE_CLAUDE / "settings.json.tmpl").read_text()
        template_events = set(
            re.findall(
                r'"(SessionStart|PreToolUse|PostToolUse|UserPromptSubmit)"',
                template_settings,
            )
        )
        assert plugin_events == template_events

    def test_no_templated_files_in_plugin(self):
        """Plugins are static — anything needing render stays scaffold-only."""
        assert not list(_PLUGIN_ROOT.rglob("*.tmpl"))


class TestPluginPayloadInSync:
    """tools/sync_plugin.py output must match templates byte-for-byte —
    run `just sync-plugin` after editing shared template skills/hooks."""

    def test_shared_skills_in_sync(self):
        template_skills = {
            p.parent.name: p
            for p in (_FALLBACK_CLAUDE / "skills").glob("*/SKILL.md")
        }
        plugin_skills = {
            p.parent.name: p
            for p in (_PLUGIN_ROOT / "skills").glob("*/SKILL.md")
        }
        assert set(template_skills) == set(plugin_skills)
        for name, template_path in template_skills.items():
            assert plugin_skills[name].read_bytes() == template_path.read_bytes(), (
                f"plugin skill {name} drifted — run `just sync-plugin`"
            )

    def test_hook_scripts_in_sync(self):
        template_hooks = {
            p.name: p
            for p in (_FALLBACK_CLAUDE / "hooks").iterdir()
            if p.suffix in {".sh", ".py"}
        }
        template_hooks["dag_workflow.py"] = (
            _TEMPLATE_CLAUDE / "hooks" / "dag_workflow.py"
        )
        plugin_hooks = {
            p.name: p
            for p in (_PLUGIN_ROOT / "hooks").iterdir()
            if p.suffix in {".sh", ".py"}
        }
        assert set(template_hooks) == set(plugin_hooks)
        for name, template_path in template_hooks.items():
            assert plugin_hooks[name].read_bytes() == template_path.read_bytes(), (
                f"plugin hook {name} drifted — run `just sync-plugin`"
            )


class TestScaffoldedSettingsWiring:
    def test_default_is_plugin_first(self, tmp_path: Path):
        """PI-165 cutover: the plugin is enabled and no duplicate hook
        wiring remains in settings — double-fire is impossible."""
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        assert (
            settings["extraKnownMarketplaces"]["project-init"]["source"]["repo"]
            == "example/project-init"
        ), "slug comes from the project_init_repo variable, never hardcoded"
        assert settings["enabledPlugins"]["project-init-workflow@project-init"] is True
        assert "hooks" not in settings, "plugin provides the hook wiring"
        # No payload copies in plugin mode (dag_workflow.py stays: scripts exec it).
        assert not (target / ".claude" / "skills" / "github_workflow").exists()
        assert not (target / ".claude" / "hooks" / "pre_commit_gate.sh").exists()
        assert (target / ".claude" / "hooks" / "dag_workflow.py").is_file()

    def test_no_plugin_restores_copies_and_wiring(self, tmp_path: Path):
        """--no-plugin: full copies + settings wiring, plugin not enabled."""
        from tests.helpers import fallback_preset, fallback_variables

        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        assert "project-init-workflow@project-init" not in settings["enabledPlugins"]
        commands = [
            h["command"]
            for entries in settings["hooks"].values()
            for entry in entries
            for h in entry["hooks"]
        ]
        assert any("pre_commit_gate.sh" in c for c in commands)
        assert (target / ".claude" / "skills" / "github_workflow" / "SKILL.md").is_file()
        assert (target / ".claude" / "hooks" / "prod_guard.py").is_file()


class TestSyncTool:
    def test_sync_removes_stale_hook_scripts(self, tmp_path: Path, monkeypatch):
        """A renamed/deleted template hook must disappear from the plugin on
        re-sync, while plugin-authored hooks.json survives (PR #166 review)."""
        import shutil

        import tools.sync_plugin as sync_plugin

        fake_root = tmp_path / "repo"
        fake_templates = fake_root / "templates" / "base" / "dot_claude"
        shutil.copytree(_TEMPLATE_CLAUDE, fake_templates)
        fake_fallback = fake_root / "templates" / "fallback" / "dot_claude"
        shutil.copytree(_FALLBACK_CLAUDE, fake_fallback)
        fake_plugin = fake_root / "plugins" / "project-init-workflow"
        shutil.copytree(_PLUGIN_ROOT, fake_plugin)

        monkeypatch.setattr(sync_plugin, "TEMPLATE_CLAUDE", fake_templates)
        monkeypatch.setattr(sync_plugin, "FALLBACK_CLAUDE", fake_fallback)
        monkeypatch.setattr(sync_plugin, "PLUGIN_ROOT", fake_plugin)
        # Keep the derived overlay sources out of this test's blast radius.
        monkeypatch.setattr(sync_plugin, "CODEX_SKILLS", fake_root / "codex-skills")
        monkeypatch.setattr(sync_plugin, "GEMINI_SKILLS", fake_root / "gemini-skills")
        monkeypatch.setattr(sync_plugin, "GEMINI_COMMANDS", fake_root / "gemini-cmds")

        (fake_fallback / "hooks" / "pre_commit_gate.sh").unlink()
        sync_plugin.sync()

        assert not (fake_plugin / "hooks" / "pre_commit_gate.sh").exists()
        assert (fake_plugin / "hooks" / "hooks.json").exists()
