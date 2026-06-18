"""PI-257: org fork lifecycle end-to-end. Scaffolding with `--profile org`
produces a coherent recorded config, host-adaptive delivery, no-egress mode, and
the binding enforcement scripts — the epic's "usable end-to-end" criterion (#253).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from project_init.__main__ import main


def _scaffold_org(target: Path, *extra: str) -> None:
    rc = main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            "obsidian-only",
            "--name",
            "acme-svc",
            "--description",
            "d",
            "--profile",
            "org",
            *extra,
        ]
    )
    assert rc == 0


def _record_vars(target: Path) -> dict:
    text = (target / ".claude" / "config.yaml").read_text()
    m = re.search(r"variables:\s*(\{.*\})", text)
    assert m, "scaffold record not found"
    return json.loads(m.group(1))


class TestOrgEndToEnd:
    def test_recorded_config_is_coherent(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_org(target)
        rec = _record_vars(target)
        assert rec["profile"] == "org"
        assert rec["enforcement"] == "hard"
        assert "project_init_host" in rec
        # The human-readable section surfaces the governance state (#259).
        human = (target / ".claude" / "config.yaml").read_text().split("# ---")[0]
        assert "profile: org" in human
        assert "enforcement: hard" in human

    def test_no_egress_omits_official_marketplace(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_org(target, "--no-egress")
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        assert "claude-plugins-official" not in settings["extraKnownMarketplaces"]
        assert "project-init" in settings["extraKnownMarketplaces"]  # org's own kept

    def test_enforcement_scripts_bind_under_org(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_org(target)
        setup = (target / ".claude" / "scripts" / "setup_github.sh").read_text()
        assert '"bypass_actors": []' in setup  # ruleset binds everyone
        monitor = (target / ".claude" / "scripts" / "monitor_pr.sh").read_text()
        assert "admin-merge is refused under the org profile" in monitor
