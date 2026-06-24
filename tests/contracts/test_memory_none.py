"""Memory backend à-la-carte (#466): the vault-free path + the variable contract.

Byte-identity of the existing obsidian backends is covered by
test_memory_byte_identity.py. This module covers the NEW behavior: overlay
derivation, the memory/obsidian/graphify variable contract across all three
emit paths, the vault-free `core` scaffold, and the default-preset guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from project_init.__main__ import ScaffoldInputs, _build_variables, _default_preset_index
from project_init.scaffold import list_presets, load_preset, memory_layers, overlay_layers, scaffold
from project_init.upgrade import _backfill_variables, _migrate_semantic_config
from tests.helpers import make_variables


def _inputs(memory: str) -> ScaffoldInputs:
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
        no_plugin=False,
        profile="individual",
        memory=memory,
    )


# (memory_stack, memory, obsidian, graphify) — the rendered-variable contract.
CONTRACT = [
    ("none", "", "", ""),
    ("obsidian-only", "true", "true", ""),
    ("obsidian-graphify", "true", "true", "true"),
]


class TestMemoryLayerDerivation:
    def test_memory_layers_mapping(self):
        assert memory_layers("none") == []
        assert memory_layers("obsidian-only") == ["obsidian"]
        # graphify always implies the obsidian vault it exports from.
        assert memory_layers("obsidian-graphify") == ["obsidian", "graphify"]

    def test_default_is_none_for_memory_agnostic_callers(self):
        # agent_layers() and many existing tests rely on the default NOT pulling
        # in obsidian (regression guard for the overlay_layers default).
        assert overlay_layers("claude", no_plugin=False) == []
        assert overlay_layers("claude,codex", no_plugin=False) == ["codex"]

    def test_memory_layers_precede_fallback_and_agents(self):
        # Historical order: base → obsidian → graphify → fallback → agents.
        assert overlay_layers(
            "claude,codex", no_plugin=True, memory_stack="obsidian-graphify"
        ) == ["obsidian", "graphify", "fallback", "codex"]


class TestVariableContract:
    """memory/obsidian/graphify must be emitted identically by all three paths."""

    @pytest.mark.parametrize("stack,mem,obs,gfy", CONTRACT)
    def test_build_variables(self, stack, mem, obs, gfy):
        v = _build_variables(load_preset("core"), _inputs(stack))
        assert (v["memory_stack"], v["memory"], v["obsidian"], v["graphify"]) == (stack, mem, obs, gfy)

    @pytest.mark.parametrize("stack,mem,obs,gfy", CONTRACT)
    def test_backfill_variables(self, stack, mem, obs, gfy):
        v = _backfill_variables({"memory_stack": stack})
        assert (v["memory_stack"], v["memory"], v["obsidian"], v["graphify"]) == (stack, mem, obs, gfy)

    def test_backfill_legacy_record_gains_memory_gate(self):
        # A pre-#466 record has memory_stack but no `memory` gate var; backfill
        # derives it (default ON) so the gated templates re-render unchanged.
        v = _backfill_variables({"memory_stack": "obsidian-only"})
        assert (v["memory"], v["obsidian"]) == ("true", "true")

    @pytest.mark.parametrize("stack,mem,obs,gfy", CONTRACT)
    def test_migrate_semantic_config(self, stack, mem, obs, gfy):
        lines = ["language: python", "memory:", f"  stack: {stack}"]
        preset_name, variables, _manifest = _migrate_semantic_config(lines)
        assert (variables["memory_stack"], variables["memory"]) == (stack, mem)
        assert (variables["obsidian"], variables["graphify"]) == (obs, gfy)
        # The vault-free stack maps to the `core` preset, NOT load_preset("none").
        assert preset_name == ("core" if stack == "none" else stack)


class TestDefaultPresetIndex:
    def test_core_does_not_become_the_enter_default(self):
        presets = list_presets()
        names = [p["name"] for p in presets]
        assert "core" in names
        default = presets[_default_preset_index(presets) - 1]
        assert default["name"] == "obsidian-only"


class TestCoreScaffold:
    """A vault-free scaffold: no memory/vault, no memory config, no dangling links."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = tmp_path / "p"
        preset = load_preset("core")
        # --no-plugin so the fallback skill set is exercised too.
        extra = overlay_layers([], no_plugin=True, memory_stack="none")
        preset = {**preset, "layers": [*preset["layers"], *extra]}
        scaffold(
            self.target,
            preset,
            make_variables(memory_stack="none", plugin_mode="", no_plugin="true"),
            strict=True,
        )

    def test_no_vault_or_memory_dirs(self):
        assert not (self.target / ".claude" / "vault").exists()
        assert not (self.target / ".claude" / "memory").exists()

    def test_no_memory_specific_docs(self):
        assert not (self.target / ".claude" / "docs" / "guides" / "using-memory.md").exists()
        assert not (self.target / ".claude" / "docs" / "adr" / "adr-001-memory-stack.md").exists()
        # the rest of docs/adr is still there
        assert (self.target / ".claude" / "docs" / "adr" / "adr-002-mcp-choices.md").is_file()

    def test_config_has_no_memory_block(self):
        cfg = (self.target / ".claude" / "config.yaml").read_text()
        assert "memory:" not in cfg
        assert "vault_path" not in cfg
        assert "mcps:" in cfg  # the block that followed the memory block survives

    def test_gitignore_has_no_vault_or_memory_lines(self):
        gi = (self.target / ".gitignore").read_text()
        assert ".claude/vault" not in gi
        assert ".claude/memory" not in gi

    def test_no_dangling_memory_links(self):
        """No markdown link points at a missing .claude/vault|memory path."""
        link_re = re.compile(r"\]\((?:\./)?\.claude/(?:vault|memory)\b")
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
        assert not offenders, f"dangling memory/vault links in: {offenders}"

    def test_base_layer_intact(self):
        assert (self.target / "AGENTS.md").is_file()
        assert (self.target / ".claude" / "settings.json").is_file()
        assert (self.target / ".claude" / "skills" / "plan" / "SKILL.md").is_file()

    def test_capabilities_does_not_claim_a_vault(self):
        cap = (self.target / ".claude" / "CAPABILITIES.md").read_text()
        assert ".claude/vault" not in cap
        assert "obsidian-only" not in cap and "obsidian-graphify" not in cap
