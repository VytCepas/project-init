"""Cross-project memory descriptor (#498, ADR-024).

Every scaffold records a stable `tier` + resolved paths (config.yaml authoritative,
CAPABILITIES.md human surface) so a root orchestrator (#479) can introspect any
child identically. Anchors are invariant across tiers; higher tiers only add
retrieval surfaces.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.__main__ import main
from project_init.scaffold import memory_tier


def _scaffold(target: Path, preset: str) -> None:
    rc = main(
        [
            str(target),
            "--non-interactive",
            "--name",
            "fx",
            "--description",
            "d",
            "--language",
            "python",
            "--preset",
            preset,
        ]
    )
    assert rc == 0


def _memory_block(target: Path) -> str:
    text = (target / ".claude" / "config.yaml").read_text()
    # the memory: block ends at the next top-level key (mcps:)
    return text.partition("\nmemory:")[2].partition("\nmcps:")[0]


class TestMemoryTierDerivation:
    def test_tier_numbers(self):
        assert memory_tier("auto") == "0"
        assert memory_tier("obsidian-only") == "1"
        assert memory_tier("obsidian-graphify") == "2"
        assert memory_tier("obsidian-graphify-rag") == "3"
        assert memory_tier("none") == ""  # no descriptor


class TestConfigDescriptor:
    @pytest.mark.parametrize(
        "preset,tier,has_vault,has_graph",
        [
            ("auto", "0", False, False),
            ("obsidian-only", "1", True, False),
            ("obsidian-graphify", "2", True, True),
        ],
    )
    def test_tier_and_paths_recorded(self, tmp_path, preset, tier, has_vault, has_graph):
        target = tmp_path / "p"
        _scaffold(target, preset)
        block = _memory_block(target)
        assert f"tier: {tier}" in block
        assert "memory_path: .claude/memory" in block  # anchor always present
        assert ("vault_path: .claude/vault" in block) is has_vault
        assert ("graph_path: graphify-out/graph.json" in block) is has_graph

    def test_none_has_no_descriptor(self, tmp_path):
        target = tmp_path / "p"
        _scaffold(target, "core")
        assert "\nmemory:" not in (target / ".claude" / "config.yaml").read_text()

    def test_anchor_path_invariant_across_tiers(self, tmp_path):
        """memory_path is the same on every tier that has memory (ADR-024 anchor)."""
        for preset in ("auto", "obsidian-only", "obsidian-graphify"):
            target = tmp_path / preset
            _scaffold(target, preset)
            assert "memory_path: .claude/memory" in _memory_block(target)


class TestCapabilitiesSurface:
    def test_capabilities_memory_section(self, tmp_path):
        target = tmp_path / "p"
        _scaffold(target, "obsidian-graphify")
        caps = (target / ".claude" / "CAPABILITIES.md").read_text()
        section = caps.partition("## Memory")[2].partition("## Skills")[0]
        assert "| Tier | 2 |" in section
        assert "| graph_path | graphify-out/graph.json |" in section

    def test_capabilities_none_reports_no_backend(self, tmp_path):
        target = tmp_path / "p"
        _scaffold(target, "core")
        caps = (target / ".claude" / "CAPABILITIES.md").read_text()
        assert "no memory backend" in caps.partition("## Memory")[2].partition("## Skills")[0]


class TestUpgradeRoundTrip:
    def test_descriptor_survives_upgrade(self, tmp_path, capsys):
        target = tmp_path / "p"
        _scaffold(target, "obsidian-graphify")
        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out
        assert "tier: 2" in _memory_block(target)

    def test_record_carries_memory_tier(self, tmp_path):
        from project_init.upgrade import read_scaffold_record

        target = tmp_path / "p"
        _scaffold(target, "obsidian-only")
        _preset, variables, _manifest, _migrated = read_scaffold_record(target)
        assert variables["memory_tier"] == "1"


class TestContractVersion:
    """Top-level `project_init_contract_version` (#498, ADR-025): a stable schema
    version a root orchestrator reads. Deliberately top-level (not nested in
    `memory:`) so it survives the vault-free `none` case; absent ⇒ v0 (reader)."""

    def test_present_even_for_none_project(self, tmp_path):
        # `core` has no memory backend, but the contract version is top-level —
        # the exact opt-out case a nested version would have missed (Codex review).
        target = tmp_path / "p"
        _scaffold(target, "core")
        text = (target / ".claude" / "config.yaml").read_text()
        assert "project_init_contract_version: 1" in text
        assert "\nmemory:" not in text  # still no memory block

    def test_present_for_memory_project(self, tmp_path):
        target = tmp_path / "p"
        _scaffold(target, "obsidian-graphify")
        assert "project_init_contract_version: 1" in (
            target / ".claude" / "config.yaml"
        ).read_text()

    def test_backfill_fills_absent_and_preserves_present(self):
        """Backward-compat: a pre-field record backfills to current (so strict
        re-render works); an explicit recorded value is preserved (setdefault)."""
        from project_init.upgrade import _backfill_variables

        absent = _backfill_variables({"memory_stack": "obsidian-only", "language": "python"})
        assert absent["project_init_contract_version"] == "1"
        present = _backfill_variables(
            {
                "memory_stack": "obsidian-only",
                "language": "python",
                "project_init_contract_version": "0",
            }
        )
        assert present["project_init_contract_version"] == "0"
