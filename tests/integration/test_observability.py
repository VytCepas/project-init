"""PI-259: local observability record — profile/source/host/plugin-version/
enforcement surfaced in .claude/config.yaml, including injection into existing
configs on upgrade (ADR-013). Closes the two deferred P2s from #247/#248.
"""

from __future__ import annotations

import re
from pathlib import Path

from project_init.scaffold import load_preset, marketplace_source_vars, scaffold
from project_init.upgrade import run_upgrade, write_scaffold_record
from tests.helpers import make_variables

_MARKER = "# --- scaffold record"


def _human_section(config_text: str) -> str:
    """The hand-editable part of config.yaml, above the generated record block."""
    return config_text.split(_MARKER)[0]


class TestMarketplaceVarsIncludeHost:
    def test_host_is_derived(self):
        assert marketplace_source_vars("https://github.com/o/r")["project_init_host"] == "github.com"
        assert (
            marketplace_source_vars("https://ghes.example.com/o/r")["project_init_host"]
            == "ghes.example.com"
        )


class TestFreshScaffoldRecordsObservability:
    def test_visible_fields_present(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        config_text = (target / ".claude" / "config.yaml").read_text()
        human = _human_section(config_text)
        assert "profile:" in human
        assert "enforcement:" in human
        assert "project_init_host:" in human
        assert "project_init_plugin_version:" in human
        assert "declined_additions: {}" in config_text


class TestUpgradeInjectsObservability:
    def test_pre_259_config_gets_fields_on_apply(self, tmp_path: Path):
        target = tmp_path / "p"
        v = make_variables()
        created = scaffold(target, load_preset("obsidian-only"), v, strict=True)
        write_scaffold_record(target, "obsidian-only", v, created)
        cfg = target / ".claude" / "config.yaml"

        # Simulate a pre-#259 human config: drop the visible enforcement/host lines.
        text = cfg.read_text()
        text = (
            "\n".join(
                ln
                for ln in text.splitlines()
                if not re.match(r"\s+(enforcement|project_init_host):", ln)
            )
            + "\n"
        )
        cfg.write_text(text)
        assert "enforcement:" not in _human_section(cfg.read_text())  # genuinely gone

        assert run_upgrade(target, apply=True) == 0

        human = _human_section(cfg.read_text())
        assert "enforcement:" in human, "upgrade must inject the visible enforcement field"
        assert "project_init_host:" in human, "upgrade must inject the visible host field"

    def test_injection_is_idempotent(self, tmp_path: Path):
        target = tmp_path / "p"
        v = make_variables()
        created = scaffold(target, load_preset("obsidian-only"), v, strict=True)
        write_scaffold_record(target, "obsidian-only", v, created)
        assert run_upgrade(target, apply=True) == 0
        human = _human_section((target / ".claude" / "config.yaml").read_text())
        # Fields are present exactly once (no duplicate injection on a current config).
        assert human.count("\n  profile:") == 1
        assert human.count("\n  enforcement:") == 1

    def test_pre_259_config_gains_updates_placeholder(self, tmp_path: Path):
        target = tmp_path / "p"
        v = make_variables()
        created = scaffold(target, load_preset("obsidian-only"), v, strict=True)
        write_scaffold_record(target, "obsidian-only", v, created)
        cfg = target / ".claude" / "config.yaml"
        # Simulate a config predating the updates section (strip the whole block).
        text = re.sub(
            r"\nupdates:\n(?:  #.*\n)*  declined_additions: \{\}\n",
            "\n",
            cfg.read_text(),
        )
        cfg.write_text(text)
        assert "declined_additions:" not in cfg.read_text()  # genuinely gone
        assert run_upgrade(target, apply=True) == 0
        assert "declined_additions: {}" in cfg.read_text()
