"""ADR-018 / #412: the governance product track — system card, AIBOM, gate.

Covers the generated AIBOM (incl. the fixture-tested CCR extractor), the
seed-once/preserve lifecycle of the user-owned declarations file, and the
presence-triggered gate (pass on a valid card, fail on each violation class,
no-op with zero cards), exercised as a real subprocess.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from project_init import governance
from project_init.scaffold import (
    _GOVERNANCE_USER_FILES,
    load_preset,
    overlay_layers,
    scaffold,
)
from tests.helpers import make_variables

_GOV = Path(".claude") / "governance"


def _scaffold(target: Path, *, governance: bool = True, multi_model: bool = False) -> Path:
    preset = load_preset("obsidian-only")
    extra = overlay_layers(
        "claude", no_plugin=False, multi_model=multi_model, governance=governance
    )
    preset = {**preset, "layers": list(preset["layers"]) + extra}
    scaffold(
        target,
        preset,
        make_variables(
            governance="true" if governance else "",
            multi_model="true" if multi_model else "",
        ),
        strict=True,
    )
    return target


def _run_gate(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(target / _GOV.parent / "scripts" / "governance_gate.sh")],
        cwd=str(target),
        capture_output=True,
        text=True,
    )


def _valid_card(target: Path) -> Path:
    """Write a valid real card + a filled declarations file, return the card path."""
    example = (target / _GOV / "examples" / "SYSTEM_CARD.example.md").read_text()
    today = date.today().isoformat()
    card = target / _GOV / "SYSTEM_CARD.md"
    card.write_text(
        "\n".join(
            f"last_reviewed: {today}" if line.startswith("last_reviewed:") else line
            for line in example.splitlines()
        ),
        encoding="utf-8",
    )
    (target / _GOV / "ai-declarations.md").write_text(
        "# AI Declarations\n\n| Model | Provider |\n|---|---|\n| claude-opus-4-8 | Anthropic |\n",
        encoding="utf-8",
    )
    return card


# --------------------------------------------------------------------------- #
# AIBOM + CCR extractor
# --------------------------------------------------------------------------- #
class TestCCRExtractor:
    def test_extracts_routes_and_providers(self, tmp_path: Path):
        cfg = tmp_path / "config.json"
        cfg.write_text(
            json.dumps(
                {
                    "Providers": [
                        {"name": "anthropic", "models": ["claude-opus-4-8"]},
                        {"name": "deepseek", "models": ["deepseek-v4-flash"]},
                    ],
                    "Router": {
                        "default": "anthropic,claude-opus-4-8",
                        "background": "deepseek,deepseek-v4-flash",
                        "longContextThreshold": 60000,
                    },
                }
            )
        )
        out = governance.extract_ccr_routes(cfg)
        assert ("default", "anthropic", "claude-opus-4-8") in out["routes"]
        assert ("background", "deepseek", "deepseek-v4-flash") in out["routes"]
        # The numeric threshold is not a route.
        assert all(role != "longContextThreshold" for role, _, _ in out["routes"])
        assert set(out["providers"]) == {"anthropic", "deepseek"}

    def test_absent_file_is_empty_not_error(self, tmp_path: Path):
        out = governance.extract_ccr_routes(tmp_path / "nope.json")
        assert out == {"routes": [], "providers": []}


class TestAIBOM:
    def test_generated_with_header_and_no_mcp(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        aibom = (target / _GOV / "ai-bom.generated.md").read_text()
        assert "Do not edit by hand" in aibom
        assert "_None installed._" in aibom
        assert "Multi-model (CCR) overlay not installed" in aibom

    def test_detects_ccr_routes_when_multi_model_on(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", multi_model=True)
        aibom = (target / _GOV / "ai-bom.generated.md").read_text()
        assert "Detected CCR routes" in aibom
        # The shipped CCR config routes background to deepseek (ADR-016).
        assert "deepseek" in aibom
        assert "anthropic" in aibom

    def test_absent_without_governance(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", governance=False)
        assert not (target / _GOV / "ai-bom.generated.md").exists()


# --------------------------------------------------------------------------- #
# Declarations lifecycle (seed-once + preserve)
# --------------------------------------------------------------------------- #
class TestDeclarationsLifecycle:
    def test_seeded_and_intrinsically_preserved(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        assert (target / _GOV / "ai-declarations.md").is_file()
        # Preserved intrinsically (not via config.yaml globs), so the lifecycle
        # holds even for projects that adopt governance after initial scaffold.
        assert ".claude/governance/ai-declarations.md" in _GOVERNANCE_USER_FILES
        assert ".claude/governance/SYSTEM_CARD.md" in _GOVERNANCE_USER_FILES
        assert ".claude/governance/config.json" in _GOVERNANCE_USER_FILES
        # The generated AIBOM must NOT be preserved — it has to refresh.
        assert ".claude/governance/ai-bom.generated.md" not in _GOVERNANCE_USER_FILES

    def test_user_edits_survive_rescaffold(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        decl = target / _GOV / "ai-declarations.md"
        decl.write_text("# my real declarations\n", encoding="utf-8")
        # Re-scaffold onto the same target — the preserved file is not clobbered.
        _scaffold(target)
        assert decl.read_text(encoding="utf-8") == "# my real declarations\n"

    def test_user_edits_survive_upgrade(self, tmp_path: Path):
        from project_init.__main__ import main

        target = tmp_path / "p"
        _scaffold(target)
        decl = target / _GOV / "ai-declarations.md"
        decl.write_text("# real declarations\n", encoding="utf-8")
        assert main(["upgrade", str(target), "--apply", "--accept-new", "all"]) == 0
        assert decl.read_text(encoding="utf-8") == "# real declarations\n"


# --------------------------------------------------------------------------- #
# Gate (subprocess)
# --------------------------------------------------------------------------- #
class TestGate:
    def test_no_card_passes(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        r = _run_gate(target)
        assert r.returncode == 0, r.stderr
        assert "nothing to check" in r.stdout

    def test_valid_card_passes(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        _valid_card(target)
        r = _run_gate(target)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "governance gate passed" in r.stdout

    def test_example_card_is_not_gated(self, tmp_path: Path):
        # The shipped examples/ card must not count as a real card.
        target = _scaffold(tmp_path / "p")
        r = _run_gate(target)
        assert r.returncode == 0
        assert "examples/" not in r.stdout

    def test_card_in_deeper_examples_dir_is_still_gated(self, tmp_path: Path):
        # Only the top-level examples/ is excluded; a real card under a deeper
        # directory named examples must still be validated (Copilot review #416).
        target = _scaffold(tmp_path / "p")
        deep = target / _GOV / "team" / "examples"
        deep.mkdir(parents=True)
        (deep / "SYSTEM_CARD.md").write_text("---\nrole: bogus\n---\n", encoding="utf-8")
        r = _run_gate(target)
        assert r.returncode == 1
        assert "team/examples/SYSTEM_CARD.md" in r.stdout

    def test_future_last_reviewed_fails(self, tmp_path: Path):
        # A future date must not bypass the staleness guard (Copilot review #416).
        target = _scaffold(tmp_path / "p")
        card = _valid_card(target)
        card.write_text(
            "\n".join(
                "last_reviewed: 2099-01-01" if line.startswith("last_reviewed:") else line
                for line in card.read_text(encoding="utf-8").splitlines()
            ),
            encoding="utf-8",
        )
        r = _run_gate(target)
        assert r.returncode == 1
        assert "future" in r.stdout

    def test_missing_field_fails(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        card = _valid_card(target)
        text = "\n".join(
            line
            for line in card.read_text(encoding="utf-8").splitlines()
            if not line.startswith("owner:")
        )
        card.write_text(text, encoding="utf-8")
        r = _run_gate(target)
        assert r.returncode == 1
        assert "owner" in r.stdout

    def test_prohibited_allowed_true_fails(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        card = _valid_card(target)
        text = card.read_text(encoding="utf-8")
        text = text.replace("classification: limited", "classification: prohibited")
        text = text.replace("allowed: true", "allowed: true")  # already true
        card.write_text(text, encoding="utf-8")
        r = _run_gate(target)
        assert r.returncode == 1
        assert "prohibited" in r.stdout and "allowed:false" in r.stdout

    def test_out_of_range_role_fails(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        card = _valid_card(target)
        card.write_text(
            card.read_text(encoding="utf-8").replace("role: deployer", "role: overlord"),
            encoding="utf-8",
        )
        r = _run_gate(target)
        assert r.returncode == 1
        assert "role must be one of" in r.stdout

    def test_stale_last_reviewed_fails(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        card = _valid_card(target)
        old = (date.today() - timedelta(days=400)).isoformat()
        card.write_text(
            "\n".join(
                f"last_reviewed: {old}" if line.startswith("last_reviewed:") else line
                for line in card.read_text(encoding="utf-8").splitlines()
            ),
            encoding="utf-8",
        )
        r = _run_gate(target)
        assert r.returncode == 1
        assert "stale" in r.stdout

    def test_staleness_window_overridable_via_config(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        card = _valid_card(target)
        old = (date.today() - timedelta(days=400)).isoformat()
        card.write_text(
            "\n".join(
                f"last_reviewed: {old}" if line.startswith("last_reviewed:") else line
                for line in card.read_text(encoding="utf-8").splitlines()
            ),
            encoding="utf-8",
        )
        # A generous window in a real config.json lets the old card pass.
        (target / _GOV / "config.json").write_text(
            json.dumps({"staleness_days": 1000}), encoding="utf-8"
        )
        r = _run_gate(target)
        assert r.returncode == 0, r.stdout

    def test_unfilled_declarations_fails(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        _valid_card(target)
        (target / _GOV / "ai-declarations.md").write_text(
            "PLACEHOLDER — fill me\n", encoding="utf-8"
        )
        r = _run_gate(target)
        assert r.returncode == 1
        assert "not filled in" in r.stdout

    @pytest.mark.parametrize(
        "bad,reason",
        [
            ("../../../etc/passwd", "traversal"),
            ("/etc/passwd", "absolute"),
        ],
    )
    def test_models_declared_path_containment(self, tmp_path: Path, bad: str, reason: str):
        target = _scaffold(tmp_path / "p")
        card = _valid_card(target)
        card.write_text(
            card.read_text(encoding="utf-8").replace(
                "models_declared: .claude/governance/ai-declarations.md",
                f"models_declared: {bad}",
            ),
            encoding="utf-8",
        )
        r = _run_gate(target)
        assert r.returncode == 1
        assert "models_declared" in r.stdout
