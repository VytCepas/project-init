"""PI-129 / ADR-010: same-repo plugin marketplace, dual-shipped with copies."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import tools.sync_plugin as sync_plugin
from project_init.scaffold import scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MARKETPLACE = _REPO_ROOT / ".claude-plugin" / "marketplace.json"
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "project-init-workflow"
_LIFECYCLE_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "project-init-lifecycle"
_TEMPLATE_CLAUDE = _REPO_ROOT / "templates" / "base" / "dot_agents"
_FALLBACK_CLAUDE = _REPO_ROOT / "templates" / "fallback" / "dot_agents"
_LIFECYCLE_FALLBACK_CLAUDE = _REPO_ROOT / "templates" / "lifecycle_fallback" / "dot_agents"
_LIFECYCLE_CLAUDE = _REPO_ROOT / "templates" / "lifecycle" / "dot_agents"


class TestMarketplaceManifest:
    def test_valid_and_lists_plugins_with_existing_sources(self):
        config = json.loads(_MARKETPLACE.read_text(encoding="utf-8"))
        assert config["name"] == "project-init"
        assert config["owner"]["name"]
        # The lifecycle decomposition (#476) split the single plugin into a core
        # plugin + a GitHub-lifecycle plugin; both ship from this marketplace.
        names = {p["name"] for p in config["plugins"]}
        assert names == {"project-init-workflow", "project-init-lifecycle"}
        for entry in config["plugins"]:
            source = entry["source"]
            assert source.startswith("./"), "same-repo plugins use relative sources"
            assert (_REPO_ROOT / source).is_dir()


class TestPluginManifest:
    def test_plugin_json_valid(self):
        # Both shipped plugins, not just the core one: the lifecycle manifest can
        # regress (missing name, non-semver version) just as easily.
        for root in (_PLUGIN_ROOT, _LIFECYCLE_PLUGIN_ROOT):
            manifest = json.loads(
                (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            assert manifest["name"] == root.name
            assert re.match(r"^\d+\.\d+\.\d+$", manifest["version"]), root.name

    def test_plugin_json_does_not_redeclare_the_standard_hooks_file(self):
        # `hooks/hooks.json` is loaded automatically; naming it in the manifest too
        # makes the client reject it as a duplicate and load *no* hooks at all
        # ("Duplicate hooks file detected"). The key is for *additional* hook files.
        for root in (_PLUGIN_ROOT, _LIFECYCLE_PLUGIN_ROOT):
            manifest = json.loads(
                (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            assert "hooks" not in manifest, root.name
            assert (root / "hooks" / "hooks.json").is_file(), root.name

    def test_hooks_json_references_only_existing_scripts(self):
        config = json.loads((_PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        commands = [
            h["command"]
            for entries in config["hooks"].values()
            for entry in entries
            for h in entry["hooks"]
        ]
        assert commands, "plugin must wire at least one hook"
        # A command may reference CLAUDE_PLUGIN_ROOT more than once — e.g. the
        # _py.sh resolver plus the Python hook it runs (PI-361). Every such
        # referenced path must exist.
        for command in commands:
            refs = re.findall(r'\$\{CLAUDE_PLUGIN_ROOT\}"?/([^\s"]+)', command)
            assert refs, f"hook command must reference CLAUDE_PLUGIN_ROOT: {command}"
            for rel in refs:
                assert (_PLUGIN_ROOT / rel).is_file(), f"missing hook script: {rel}"

    def test_hook_events_match_template_wiring(self):
        """The two plugins together wire the same events the scaffolded settings
        wire, so the documented cutover (ADR-010) is a drop-in swap (#476: the
        lifecycle plugin supplies PreToolUse(guard) + UserPromptSubmit)."""
        plugin_events = set(
            json.loads((_PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        ) | set(
            json.loads(
                (_LIFECYCLE_PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
            )["hooks"]
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
    """tools/sync_plugin.py output must match templates byte-for-byte — run
    `just sync-plugin` after editing shared template skills/hooks. The lifecycle
    decomposition (#476) split the payload across the core + lifecycle plugins;
    the sync functions are the single source of truth for what lands where."""

    def _assert_skills(self, plugin_root, skill_dirs):
        plugin_skills = {p.parent.name: p for p in (plugin_root / "skills").glob("*/SKILL.md")}
        assert {d.name for d in skill_dirs} == set(plugin_skills), (
            f"{plugin_root.name} skill set drifted — run `just sync-plugin`"
        )
        for d in skill_dirs:
            assert plugin_skills[d.name].read_bytes() == (d / "SKILL.md").read_bytes(), (
                f"{plugin_root.name} skill {d.name} drifted — run `just sync-plugin`"
            )

    def _assert_hooks(self, plugin_root, scripts):
        plugin_hooks = {
            p.name: p for p in (plugin_root / "hooks").iterdir() if p.suffix in {".sh", ".py"}
        }
        expected = {s.name: s for s in scripts}
        assert set(expected) == set(plugin_hooks), (
            f"{plugin_root.name} hook set drifted — run `just sync-plugin`"
        )
        for name, src in expected.items():
            assert plugin_hooks[name].read_bytes() == src.read_bytes(), (
                f"{plugin_root.name} hook {name} drifted — run `just sync-plugin`"
            )

    def test_core_plugin_skills_in_sync(self):
        self._assert_skills(_PLUGIN_ROOT, sync_plugin.core_skill_dirs())

    def test_core_plugin_hooks_in_sync(self):
        self._assert_hooks(_PLUGIN_ROOT, sync_plugin.core_hook_scripts())

    def test_lifecycle_plugin_skills_in_sync(self):
        self._assert_skills(_LIFECYCLE_PLUGIN_ROOT, sync_plugin.lifecycle_skill_dirs())

    def test_lifecycle_plugin_hooks_in_sync(self):
        self._assert_hooks(_LIFECYCLE_PLUGIN_ROOT, sync_plugin.lifecycle_hook_scripts())


class TestPayloadVersionLock:
    """PI-881: a plugin's version must move when its payload does.

    Claude Code caches a plugin by version, so a payload change under an
    unchanged version silently serves the stale copy (the PI-845 guard fix
    shipped that way; #857 patched the same class twice by hand). The committed
    `plugins/payload-locks.json` pins each version to a payload hash; these
    tests are the tripwire, and `update_payload_locks()` refuses to relock a
    changed payload without a bump.
    """

    def test_lock_matches_the_committed_tree(self):
        locks = sync_plugin.read_payload_locks()
        for root in (_PLUGIN_ROOT, _LIFECYCLE_PLUGIN_ROOT):
            assert locks.get(root.name) == sync_plugin.expected_lock(root), (
                f"{root.name} payload lock drifted — run `just sync-plugin` "
                "(bump the plugin version first if the payload changed)"
            )

    def test_lock_version_tracks_the_manifest(self):
        locks = sync_plugin.read_payload_locks()
        for root in (_PLUGIN_ROOT, _LIFECYCLE_PLUGIN_ROOT):
            assert locks[root.name]["version"] == sync_plugin.plugin_version(root), root.name

    def test_guard_rejects_a_payload_change_without_a_version_bump(self, tmp_path, monkeypatch):
        # Prove the guard can fail: a lock recording a different hash under the
        # current version must make update_payload_locks() refuse to relock.
        fake = tmp_path / "payload-locks.json"
        poisoned = {
            root.name: {"version": sync_plugin.plugin_version(root), "sha256": "0" * 64}
            for root in (_PLUGIN_ROOT, _LIFECYCLE_PLUGIN_ROOT)
        }
        fake.write_text(json.dumps(poisoned), encoding="utf-8")
        monkeypatch.setattr(sync_plugin, "_PAYLOAD_LOCKS", fake)
        with pytest.raises(SystemExit, match="payload changed but version is still"):
            sync_plugin.update_payload_locks()

    def test_guard_seeds_a_first_seen_plugin_without_objecting(self, tmp_path, monkeypatch):
        fake = tmp_path / "payload-locks.json"  # absent → every plugin is first-seen
        monkeypatch.setattr(sync_plugin, "_PAYLOAD_LOCKS", fake)
        sync_plugin.update_payload_locks()
        assert sync_plugin.read_payload_locks() == {
            root.name: sync_plugin.expected_lock(root)
            for root in (_PLUGIN_ROOT, _LIFECYCLE_PLUGIN_ROOT)
        }

    def test_hash_folds_in_the_executable_bit(self, tmp_path, monkeypatch):
        # A hook losing +x is a breaking payload change even with identical bytes;
        # the digest must move so the version bump is forced (PI-881 review).
        (tmp_path / ".claude-plugin").mkdir()
        (tmp_path / ".claude-plugin" / "plugin.json").write_text('{"version": "1.0.0"}')
        hook = tmp_path / "hooks" / "h.sh"
        hook.parent.mkdir()
        hook.write_text("#!/bin/sh\n")
        hook.chmod(0o755)
        executable = sync_plugin.payload_sha256(tmp_path)
        hook.chmod(0o644)
        assert sync_plugin.payload_sha256(tmp_path) != executable

    def test_shipped_shell_hooks_are_executable(self):
        # hooks.json runs `.sh` files directly; a non-executable one breaks the
        # install. The digest catches a *change*, this catches the absolute state.
        for root in (_PLUGIN_ROOT, _LIFECYCLE_PLUGIN_ROOT):
            for hook in (root / "hooks").glob("*.sh"):
                assert hook.stat().st_mode & 0o111, f"{root.name}/{hook.name} is not executable"


class TestScaffoldedSettingsWiring:
    def test_default_is_plugin_first(self, tmp_path: Path):
        """PI-165 cutover: the plugin is enabled and no duplicate hook
        wiring remains in settings — double-fire is impossible."""
        from tests.helpers import memory_preset

        target = tmp_path / "p"
        # memory_preset appends the lifecycle overlay (#476) so dag_workflow.py
        # (scaffolded in both modes) is present, as a real default scaffold is.
        scaffold(target, memory_preset("obsidian-only"), make_variables(), strict=True)
        settings = json.loads((target / ".agents" / "settings.json").read_text(encoding="utf-8"))
        assert (
            settings["extraKnownMarketplaces"]["project-init"]["source"]["repo"]
            == "example/project-init"
        ), "slug comes from the project_init_repo variable, never hardcoded"
        assert settings["enabledPlugins"]["project-init-workflow@project-init"] is True
        # The lifecycle plugin is enabled too when the tier is on (#476 default).
        assert settings["enabledPlugins"]["project-init-lifecycle@project-init"] is True
        assert "hooks" not in settings, "plugin provides the hook wiring"
        # No payload copies in plugin mode (dag_workflow.py stays: scripts exec it).
        assert not (target / ".agents" / "skills" / "github_workflow").exists()
        assert not (target / ".agents" / "hooks" / "pre_commit_gate.sh").exists()
        assert (target / ".agents" / "hooks" / "dag_workflow.py").is_file()

    def test_no_plugin_restores_copies_and_wiring(self, tmp_path: Path):
        """--no-plugin: full copies + settings wiring, plugin not enabled."""
        from tests.helpers import fallback_preset, fallback_variables

        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        settings = json.loads((target / ".agents" / "settings.json").read_text(encoding="utf-8"))
        assert "project-init-workflow@project-init" not in settings["enabledPlugins"]
        commands = [
            h["command"]
            for entries in settings["hooks"].values()
            for entry in entries
            for h in entry["hooks"]
        ]
        assert any("pre_commit_gate.sh" in c for c in commands)
        assert (target / ".agents" / "skills" / "github_workflow" / "SKILL.md").is_file()
        assert (target / ".agents" / "hooks" / "prod_guard.py").is_file()


class TestSyncTool:
    def test_sync_removes_stale_hook_scripts(self, tmp_path: Path, monkeypatch):
        """A renamed/deleted template hook must disappear from the plugin on
        re-sync, while plugin-authored hooks.json survives (PR #166 review)."""
        import shutil

        fake_root = tmp_path / "repo"
        fake_templates = fake_root / "templates" / "base" / "dot_agents"
        shutil.copytree(_TEMPLATE_CLAUDE, fake_templates)
        fake_fallback = fake_root / "templates" / "fallback" / "dot_agents"
        shutil.copytree(_FALLBACK_CLAUDE, fake_fallback)
        fake_lifecycle = fake_root / "templates" / "lifecycle" / "dot_agents"
        shutil.copytree(_LIFECYCLE_CLAUDE, fake_lifecycle)
        fake_lifecycle_fallback = fake_root / "templates" / "lifecycle_fallback" / "dot_agents"
        shutil.copytree(_LIFECYCLE_FALLBACK_CLAUDE, fake_lifecycle_fallback)
        fake_plugin = fake_root / "plugins" / "project-init-workflow"
        shutil.copytree(_PLUGIN_ROOT, fake_plugin)
        fake_lifecycle_plugin = fake_root / "plugins" / "project-init-lifecycle"
        shutil.copytree(_LIFECYCLE_PLUGIN_ROOT, fake_lifecycle_plugin)

        monkeypatch.setattr(sync_plugin, "TEMPLATE_CLAUDE", fake_templates)
        monkeypatch.setattr(sync_plugin, "FALLBACK_CLAUDE", fake_fallback)
        monkeypatch.setattr(sync_plugin, "LIFECYCLE_CLAUDE", fake_lifecycle)
        monkeypatch.setattr(sync_plugin, "LIFECYCLE_FALLBACK_CLAUDE", fake_lifecycle_fallback)
        monkeypatch.setattr(sync_plugin, "WORKFLOW_PLUGIN", fake_plugin)
        monkeypatch.setattr(sync_plugin, "LIFECYCLE_PLUGIN", fake_lifecycle_plugin)
        # Keep the derived overlay sources out of this test's blast radius.
        monkeypatch.setattr(sync_plugin, "CODEX_SKILLS", fake_root / "codex-skills")
        monkeypatch.setattr(sync_plugin, "ANTIGRAVITY_SKILLS", fake_root / "antigravity-skills")
        monkeypatch.setattr(sync_plugin, "AMP_SKILLS", fake_root / "amp-skills")
        monkeypatch.setattr(sync_plugin, "JUNIE_SKILLS", fake_root / "junie-skills")

        # A core (fallback) hook deletion must vanish from the core plugin.
        (fake_fallback / "hooks" / "pre_commit_gate.sh").unlink()
        sync_plugin.sync()

        assert not (fake_plugin / "hooks" / "pre_commit_gate.sh").exists()
        assert (fake_plugin / "hooks" / "hooks.json").exists()
        assert (fake_lifecycle_plugin / "hooks" / "hooks.json").exists()
        assert (fake_plugin / "hooks" / "hooks.json").exists()


class TestManifestDiscoveryPath:
    """The manifest location is a consumer's discovery contract, not our convention.

    Claude Code reads manifests *only* from `.claude-plugin/`. PI-606 renamed the
    directory to `.agents-plugin/` alongside the `.claude/` -> `.agents/` migration
    and silently un-shipped both plugins; every assertion above kept passing because
    they resolve through module constants, which followed the rename. These pin the
    literal path instead, so the same mistake fails loudly.
    """

    def test_marketplace_manifest_is_at_the_spec_path(self):
        assert (_REPO_ROOT / ".claude-plugin" / "marketplace.json").is_file()

    def test_every_plugin_manifest_is_at_the_spec_path(self):
        for root in (_PLUGIN_ROOT, _LIFECYCLE_PLUGIN_ROOT):
            assert (root / ".claude-plugin" / "plugin.json").is_file(), root.name

    def test_no_manifest_survives_outside_the_spec_path(self):
        strays = [*_REPO_ROOT.glob(".agents-plugin"), *_REPO_ROOT.glob("plugins/*/.agents-plugin")]
        assert strays == []
