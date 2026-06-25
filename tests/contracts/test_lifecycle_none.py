"""GitHub lifecycle à-la-carte (#476, ADR-021): the lifecycle-free path + the
variable contract + the plugin split.

Byte-identity of the lifecycle-ON scaffold is covered by
test_lifecycle_byte_identity.py. This module covers the NEW behavior: overlay
derivation, the lifecycle/lifecycle_tier/lifecycle_off variable contract across
all three emit paths, the `--lifecycle none` scaffold (no DAG/scripts/workflows/
templates/guard-hooks/lifecycle-skills, valid settings.json, no dangling links),
and the two-plugin split.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from project_init.__main__ import ScaffoldInputs, _build_variables
from project_init.scaffold import load_preset, overlay_layers, scaffold
from project_init.upgrade import _backfill_variables, _migrate_semantic_config
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _inputs(lifecycle: str, *, no_plugin: bool = False) -> ScaffoldInputs:
    return ScaffoldInputs(
        project_name="p",
        project_description="d",
        language="python",
        selected_mcps=[],
        owner="",
        license_choice="none",
        devcontainer=False,
        mise=False,
        vscode=False,
        agents=["claude"],
        no_plugin=no_plugin,
        profile="individual",
        memory="none",
        lifecycle=lifecycle,
    )


# (lifecycle_tier, lifecycle, lifecycle_off) — the rendered-variable contract.
CONTRACT = [
    ("github", "true", ""),
    ("none", "", "true"),
]


class TestLifecycleLayerDerivation:
    def test_overlay_appends_lifecycle_when_on(self):
        # plugin mode: just the lifecycle layer (both modes).
        assert overlay_layers("claude", no_plugin=False, lifecycle=True) == ["lifecycle"]
        # no-plugin: fallback + lifecycle + lifecycle_fallback.
        assert overlay_layers("claude", no_plugin=True, lifecycle=True) == [
            "fallback",
            "lifecycle",
            "lifecycle_fallback",
        ]

    def test_overlay_omits_lifecycle_when_off(self):
        assert overlay_layers("claude", no_plugin=False, lifecycle=False) == []
        assert overlay_layers("claude", no_plugin=True, lifecycle=False) == ["fallback"]

    def test_default_is_off_for_overlay_agnostic_callers(self):
        # Regression guard for the overlay_layers default (mirrors memory).
        assert overlay_layers("claude", no_plugin=False) == []

    def test_lifecycle_precedes_agents(self):
        # base → fallback → lifecycle → lifecycle_fallback → agents.
        assert overlay_layers(
            "claude,codex", no_plugin=True, lifecycle=True
        ) == ["fallback", "lifecycle", "lifecycle_fallback", "codex"]


class TestVariableContract:
    """lifecycle/lifecycle_tier/lifecycle_off must be emitted identically by all
    three emit paths so scaffold + upgrade never diverge (PI-189)."""

    @pytest.mark.parametrize("tier,life,off", CONTRACT)
    def test_build_variables(self, tier, life, off):
        v = _build_variables(load_preset("core"), _inputs(tier))
        assert (v["lifecycle_tier"], v["lifecycle"], v["lifecycle_off"]) == (tier, life, off)

    @pytest.mark.parametrize("tier,life,off", CONTRACT)
    def test_backfill_variables(self, tier, life, off):
        v = _backfill_variables({"memory_stack": "none", "lifecycle_tier": tier})
        assert (v["lifecycle_tier"], v["lifecycle"], v["lifecycle_off"]) == (tier, life, off)

    def test_backfill_legacy_record_gains_lifecycle_on(self):
        # A pre-#476 record has no lifecycle field; backfill derives it ON
        # (lifecycle is opt-OUT) so the gated templates re-render unchanged.
        v = _backfill_variables({"memory_stack": "obsidian-only"})
        assert (v["lifecycle_tier"], v["lifecycle"], v["lifecycle_off"]) == ("github", "true", "")

    @pytest.mark.parametrize("tier,life,off", CONTRACT)
    def test_migrate_semantic_config(self, tier, life, off):
        # Pre-record configs predate the lifecycle decomposition (it was always
        # bundled), so the semantic fallback always reconstructs lifecycle ON,
        # regardless of the (lifecycle-agnostic) tier under test here.
        _preset, variables, _manifest = _migrate_semantic_config(["language: python"])
        assert (variables["lifecycle_tier"], variables["lifecycle"]) == ("github", "true")
        assert variables["lifecycle_off"] == ""


class TestLifecycleNoneScaffold:
    """A lifecycle-free scaffold: no DAG/scripts/workflows/templates/guard hooks/
    lifecycle skills, valid settings, no dangling links — quality core intact."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = tmp_path / "p"
        preset = load_preset("core")
        # --no-plugin so the copied hook/skill set is exercised too.
        extra = overlay_layers([], no_plugin=True, memory_stack="none", lifecycle=False)
        preset = {**preset, "layers": [*preset["layers"], *extra]}
        scaffold(
            self.target,
            preset,
            make_variables(
                memory_stack="none", lifecycle_tier="none", plugin_mode="", no_plugin="true"
            ),
            strict=True,
        )

    def test_no_lifecycle_scripts(self):
        scripts = self.target / ".claude" / "scripts"
        for s in (
            "create_issue.sh",
            "start_issue.sh",
            "finish_pr.sh",
            "monitor_pr.sh",
            "push_branch.sh",
            "setup_github.sh",
            "promote_review.sh",
            "create_nojira_pr.sh",
            "push_wiki.sh",
        ):
            assert not (scripts / s).exists(), f"lifecycle script leaked: {s}"
        # Quality + shared-utility scripts stay.
        assert (scripts / "install_hooks.sh").is_file()
        assert (scripts / "gh_host.sh").is_file()

    def test_no_dag_or_guard_hooks(self):
        hooks = self.target / ".claude" / "hooks"
        assert not (hooks / "dag_workflow.py").exists()
        assert not (hooks / "github_command_guard.sh").exists()
        assert not (hooks / "workflow_state_reminder.sh").exists()
        # Quality/safety hooks stay.
        assert (hooks / "prod_guard.py").is_file()
        assert (hooks / "pre_commit_gate.sh").is_file()

    def test_no_lifecycle_workflows_or_templates(self):
        gh = self.target / ".github"
        for w in (
            "board-automation.yml",
            "issue-validation.yml",
            "review-status.yml",
            "validate-pr.yml",
            "project-init-upgrade.yml",
        ):
            assert not (gh / "workflows" / w).exists(), f"lifecycle workflow leaked: {w}"
        assert not (gh / "ISSUE_TEMPLATE").exists()
        assert not (gh / "pull_request_template.md").exists()
        assert not (gh / "copilot-instructions.md").exists()
        # The quality CI workflow stays.
        assert (gh / "workflows" / "ci.yml").is_file()

    def test_no_lifecycle_skills(self):
        skills = self.target / ".claude" / "skills"
        for sk in ("create_issue", "start_task", "github_workflow", "request_review", "audit"):
            assert not (skills / sk).exists(), f"lifecycle skill leaked: {sk}"
        # A general skill stays (plan is the always-rendered base skill).
        assert (skills / "plan" / "SKILL.md").is_file()

    def test_settings_valid_and_no_lifecycle_hooks(self):
        settings = json.loads((self.target / ".claude" / "settings.json").read_text())
        commands = [
            h["command"]
            for entries in settings["hooks"].values()
            for entry in entries
            for h in entry["hooks"]
        ]
        joined = " ".join(commands)
        assert "github_command_guard" not in joined
        assert "workflow_state_reminder" not in joined
        assert "UserPromptSubmit" not in settings["hooks"]
        # Quality/safety hooks still wired.
        assert any("pre_commit_gate.sh" in c for c in commands)
        assert any("prod_guard.py" in c for c in commands)

    def test_pre_push_keeps_main_block_drops_branch_rule(self):
        pp = (self.target / ".github" / "hooks" / "pre-push").read_text()
        assert "Direct push to main/master is not allowed" in pp  # quality, stays
        assert "lifecycle naming convention" not in pp  # lifecycle rule, gated out
        assert "start_issue.sh" not in pp  # no dangling lifecycle-script reference

    def test_no_dangling_lifecycle_links(self):
        """No markdown link points at a missing lifecycle file."""
        link_re = re.compile(
            r"\]\((?:\./)?(?:\.claude/(?:scripts|hooks)/(?:create_issue|start_issue|finish_pr|"
            r"monitor_pr|push_branch|setup_github|promote_review|create_nojira_pr|push_wiki|"
            r"dag_workflow|github_command_guard|workflow_state_reminder)"
            r"|\.github/(?:workflows/(?:board-automation|issue-validation|review-status|validate-pr|"
            r"project-init-upgrade)|ISSUE_TEMPLATE|pull_request_template|copilot-instructions))"
        )
        offenders = []
        for p in self.target.rglob("*"):
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if link_re.search(text):
                offenders.append(p.relative_to(self.target).as_posix())
        assert not offenders, f"dangling lifecycle links in: {offenders}"

    def test_base_layer_intact(self):
        assert (self.target / "AGENTS.md").is_file()
        assert (self.target / ".claude" / "settings.json").is_file()
        assert (self.target / ".claude" / "project-init.md").is_file()


class TestPluginSplit:
    """Plugin mode: the lifecycle plugin is enabled only when the tier is on."""

    def _settings(self, tmp_path: Path, lifecycle: str) -> dict:
        target = tmp_path / lifecycle
        preset = load_preset("obsidian-only")
        extra = overlay_layers([], no_plugin=False, memory_stack="obsidian-only", lifecycle=lifecycle == "github")
        preset = {**preset, "layers": [*preset["layers"], *extra]}
        scaffold(target, preset, make_variables(lifecycle_tier=lifecycle), strict=True)
        return json.loads((target / ".claude" / "settings.json").read_text())

    def test_lifecycle_plugin_enabled_when_on(self, tmp_path: Path):
        plugins = self._settings(tmp_path, "github")["enabledPlugins"]
        assert plugins.get("project-init-workflow@project-init") is True
        assert plugins.get("project-init-lifecycle@project-init") is True

    def test_lifecycle_plugin_absent_when_off(self, tmp_path: Path):
        plugins = self._settings(tmp_path, "none")["enabledPlugins"]
        assert plugins.get("project-init-workflow@project-init") is True
        assert "project-init-lifecycle@project-init" not in plugins

    def test_both_plugins_registered_in_marketplace(self):
        mp = json.loads((_REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
        names = {p["name"] for p in mp["plugins"]}
        assert {"project-init-workflow", "project-init-lifecycle"} <= names
        for entry in mp["plugins"]:
            assert (_REPO_ROOT / entry["source"]).is_dir()

    def test_lifecycle_plugin_carries_lifecycle_hooks_and_skills(self):
        root = _REPO_ROOT / "plugins" / "project-init-lifecycle"
        events = set(json.loads((root / "hooks" / "hooks.json").read_text())["hooks"])
        assert events == {"PreToolUse", "UserPromptSubmit"}
        for sk in ("create_issue", "start_task", "github_workflow", "request_review", "audit"):
            assert (root / "skills" / sk / "SKILL.md").is_file()
        for hk in ("github_command_guard.sh", "workflow_state_reminder.sh", "dag_workflow.py"):
            assert (root / "hooks" / hk).is_file()

    def test_core_plugin_has_no_lifecycle_hooks(self):
        root = _REPO_ROOT / "plugins" / "project-init-workflow"
        events = set(json.loads((root / "hooks" / "hooks.json").read_text())["hooks"])
        assert "UserPromptSubmit" not in events
        assert not (root / "hooks" / "github_command_guard.sh").exists()
        assert not (root / "skills" / "create_issue").exists()
