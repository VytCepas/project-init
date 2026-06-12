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
            for p in (_TEMPLATE_CLAUDE / "skills").glob("*/SKILL.md")
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
            for p in (_TEMPLATE_CLAUDE / "hooks").iterdir()
            if p.suffix in {".sh", ".py"}
        }
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
    def test_marketplace_offered_but_plugin_not_enabled(self, tmp_path: Path):
        """ADR-010 dual-ship: marketplace registered (plugin offered on
        trust); plugin NOT enabled — copies are the active wiring, and
        enabling both would double-fire every hook."""
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        assert (
            settings["extraKnownMarketplaces"]["project-init"]["source"]["repo"]
            == "example/project-init"
        ), "slug comes from the project_init_repo variable, never hardcoded"
        assert not any(
            "project-init-workflow" in key for key in settings["enabledPlugins"]
        )
