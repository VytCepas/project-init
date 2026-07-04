"""Regression tests for the 2026-07 audit fixes.

Covers the source-level fixes that don't fit an existing focused module:
the pre-#466 memory_stack upgrade backfill, preset [vars] reaching the render
context, and the wizard honoring --mcps.
"""

from __future__ import annotations

import pytest

from project_init import scaffold as sc
from project_init.__main__ import _gather_mcps_interactive
from project_init.upgrade import (
    _backfill_variables,
    _carry_rag_endpoint,
    _memory_stack_from_flags,
)


class TestMemoryStackBackfill:
    """A record written before memory_stack existed (#466) must reconstruct the
    stack from its gate flags AND backfill the stack name itself — else
    config.yaml's `stack: {{memory_stack}}` survives the strict re-render."""

    @pytest.mark.parametrize(
        ("flags", "expected"),
        [
            ({"rag": "true", "graphify": "true", "obsidian": "true"}, "obsidian-graphify-rag"),
            ({"graphify": "true", "obsidian": "true"}, "obsidian-graphify"),
            ({"obsidian": "true"}, "obsidian-only"),
            ({"memory": "true"}, "auto"),
            # `memory` recorded-but-empty = explicit core (memory declined) —
            # must stay "none", never resurrect a vault.
            ({"memory": ""}, "none"),
            ({}, "obsidian-only"),  # no memory signal at all → pre-#466 floor
        ],
    )
    def test_stack_from_flags(self, flags, expected):
        assert _memory_stack_from_flags(flags) == expected

    def test_backfill_sets_memory_stack_for_graphify_record(self):
        # Pre-#466 obsidian-graphify record: graphify gate but no memory_stack.
        out = _backfill_variables({"language": "python", "graphify": "true", "obsidian": "true"})
        assert out["memory_stack"] == "obsidian-graphify"
        assert out["memory_tier"] == "2"
        assert out["graphify"] == "true"
        assert out["rag"] == ""

    def test_backfill_preserves_recorded_stack(self):
        out = _backfill_variables({"language": "go", "memory_stack": "auto", "memory": "true"})
        assert out["memory_stack"] == "auto"
        assert out["obsidian"] == ""

    def test_backfill_strips_owner_at_prefix_from_license_holder(self):
        # PI-181 parity: the CODEOWNERS "@" must not leak into LICENSE copyright.
        out = _backfill_variables({"project_owner": "@acme/team"})
        assert out["license_holder"] == "acme/team"


class TestPresetVarsReachRender:
    """Preset [vars] (#252) must actually reach the render context (previously a
    no-op): fill empty resolved values, add preset-only keys, coerce to str, and
    never override an explicit (non-empty) value."""

    def test_fills_empty_and_adds_keys(self):
        preset = {"layers": ["base"], "vars": {"project_owner": "@acme", "custom": 7}}
        merged = sc._apply_preset_vars({"project_owner": "", "project_name": "p"}, preset)
        assert merged["project_owner"] == "@acme"  # filled empty
        assert merged["custom"] == "7"  # added + coerced to str

    def test_explicit_value_wins(self):
        preset = {"layers": ["base"], "vars": {"project_owner": "@acme"}}
        merged = sc._apply_preset_vars({"project_owner": "@explicit"}, preset)
        assert merged["project_owner"] == "@explicit"

    def test_no_vars_returns_input_unchanged(self):
        variables = {"project_name": "p"}
        assert sc._apply_preset_vars(variables, {"layers": ["base"]}) is variables

    def test_bool_false_does_not_enable_a_gate(self):
        # str(False) == "False" is truthy and would ENABLE the gate — a TOML
        # false must coerce to "" (off), true to "true".
        preset = {"layers": ["base"], "vars": {"observability": False, "multi_model": True}}
        merged = sc._apply_preset_vars({"observability": "", "multi_model": ""}, preset)
        assert merged["observability"] == ""
        assert merged["multi_model"] == "true"

    def test_control_keys_never_refill_the_render_context(self):
        # memory_stack/lifecycle/governance configure the CLI/upgrade resolution
        # and are folded into the variables upstream. Merging them here breaks
        # convergence: a `governed` preset's `governance = true` would re-enable
        # the gate an explicit `remove governance` set to "", and a preset's
        # `lifecycle = "none"` (a tier name) is a TRUTHY string that would turn
        # every {{#if lifecycle}} block ON (2026-07 review).
        preset = {
            "layers": ["base"],
            "vars": {"governance": True, "lifecycle": "none", "memory_stack": "obsidian-only"},
        }
        merged = sc._apply_preset_vars(
            {"governance": "", "lifecycle": "", "memory_stack": "none"}, preset
        )
        assert merged["governance"] == ""  # explicit OFF survives the preset
        assert merged["lifecycle"] == ""  # tier name never leaks into the gate
        assert merged["memory_stack"] == "none"

    def test_owner_preset_keeps_license_holder_in_step(self):
        # Preset supplies project_owner, no --owner: LICENSE copyright must track
        # CODEOWNERS, not stay the project-name fallback.
        preset = {"layers": ["base"], "vars": {"project_owner": "@acme/team"}}
        merged = sc._apply_preset_vars(
            {"project_owner": "", "license_holder": "myproj", "project_name": "myproj"},
            preset,
        )
        assert merged["project_owner"] == "@acme/team"
        assert merged["license_holder"] == "acme/team"

    def test_explicit_owner_leaves_license_holder_untouched(self):
        # With an explicit --owner, license_holder was already derived from it;
        # a preset project_owner must not override the user's owner or holder.
        preset = {"layers": ["base"], "vars": {"project_owner": "@acme/team"}}
        merged = sc._apply_preset_vars(
            {"project_owner": "@mine", "license_holder": "mine", "project_name": "p"},
            preset,
        )
        assert merged["project_owner"] == "@mine"
        assert merged["license_holder"] == "mine"


class TestCarryRagEndpoint:
    """The memory-block splice on upgrade must not reset a hand-set
    memory.rag_endpoint — the template always renders it empty and
    setup_rag.sh explicitly instructs the user to set it (2026-07 review)."""

    _OLD = (
        "memory:\n"
        "  tier: 3\n"
        '  rag_endpoint: "ccc mcp"  # user-set per setup_rag.sh\n'
        "\n"
    )
    _NEW = (
        "memory:\n"
        "  tier: 3\n"
        "  rag_endpoint:        # tier 3: set after running setup_rag.sh\n"
        "\n"
    )

    def test_user_value_survives_the_splice(self):
        out = _carry_rag_endpoint(self._OLD, self._NEW)
        assert '  rag_endpoint: "ccc mcp"  # user-set per setup_rag.sh' in out
        assert "tier: 3" in out

    def test_untouched_endpoint_takes_fresh_render(self):
        out = _carry_rag_endpoint(self._NEW, self._NEW)
        assert out == self._NEW

    def test_template_supplied_value_wins_over_old(self):
        rendered = self._NEW.replace("rag_endpoint:  ", "rag_endpoint: new-value")
        assert _carry_rag_endpoint(self._OLD, rendered) == rendered

    def test_no_endpoint_line_is_a_no_op(self):
        no_rag = "memory:\n  tier: 2\n\n"
        assert _carry_rag_endpoint(self._OLD, no_rag) == no_rag


class TestWizardHonorsMcpsFlag:
    """--mcps passed without --non-interactive must be honored, not dropped."""

    def test_cli_mcps_resolved_without_catalog_prompt(self, monkeypatch):
        # --mcps pins the catalog picks without the multi-select, but browser
        # automation is its own selectable concern (ADR-023): it must still be
        # OFFERED when --browser was not given, matching how devcontainer/mise/
        # vscode still prompt in the same run (2026-07 review).
        offered = []
        monkeypatch.setattr(
            "project_init.__main__._choose_browser_interactive",
            lambda: offered.append(True) or False,
        )
        selected = _gather_mcps_interactive("context7", False)
        assert [m["id"] for m in selected] == ["context7"]
        assert offered, "browser concern must still be offered (ADR-023)"

    def test_cli_mcps_browser_prompt_accept_adds_playwright(self, monkeypatch):
        monkeypatch.setattr(
            "project_init.__main__._choose_browser_interactive", lambda: True
        )
        selected = _gather_mcps_interactive("context7", False)
        assert [m["id"] for m in selected] == ["context7", "playwright"]

    def test_cli_mcps_with_browser(self):
        selected = _gather_mcps_interactive("context7", True)
        ids = [m["id"] for m in selected]
        assert "context7" in ids
        assert "playwright" in ids
