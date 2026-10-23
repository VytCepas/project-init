"""ADR-018 / #412: the governance product track — system card, AIBOM, gate.

Covers the generated AIBOM (incl. the fixture-tested CCR extractor), the
seed-once/preserve lifecycle of the user-owned declarations file, and the
gate (pass on a valid card, fail on each violation class) and its refusal to
pass on silence (no card and no dated no-AI declaration fails), exercised as a
real subprocess.
"""

from __future__ import annotations

import json
import re
import shutil
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

_GOV = Path(".agents") / "governance"


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


_GOOD_REASON = "Static documentation site; no model is called, trained or shipped."


def _declare(target: Path, **overrides: str | None) -> Path:
    """Write ``NO_AI_SYSTEM.md``; a ``None`` override omits that field."""
    fields: dict[str, str | None] = {
        "reason": _GOOD_REASON,
        "declared_on": date.today().isoformat(),
        **overrides,
    }
    body = "\n".join(f"{k}: {v}" for k, v in fields.items() if v is not None)
    path = target / _GOV / "NO_AI_SYSTEM.md"
    path.write_text(f"---\n{body}\n---\n\n# No AI system\n", encoding="utf-8")
    return path


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

    def test_upgrade_detects_routes_from_project_not_staging(self, tmp_path: Path):
        # Upgrade re-renders into a staging dir whose CCR config.json is the
        # pristine template copy. Route detection must read the *project's*
        # live config — detecting against staging would make `upgrade --apply`
        # overwrite the AIBOM's real routes with template defaults.
        from project_init.__main__ import main
        from project_init.upgrade import write_scaffold_record

        target = tmp_path / "p"
        preset = load_preset("obsidian-only")
        extra = overlay_layers("claude", no_plugin=False, multi_model=True, governance=True)
        preset = {**preset, "layers": list(preset["layers"]) + extra}
        variables = make_variables(governance="true", multi_model="true")
        created = scaffold(target, preset, variables, strict=True)
        write_scaffold_record(target, "obsidian-only", variables, created)

        ccr = target / ".agents" / "multi-model" / "config.json"
        data = json.loads(ccr.read_text(encoding="utf-8"))
        data["Router"]["think"] = "myprov,my-custom-model"
        ccr.write_text(json.dumps(data), encoding="utf-8")

        assert main(["upgrade", str(target), "--apply", "--accept-new", "all"]) == 0
        aibom = (target / _GOV / "ai-bom.generated.md").read_text(encoding="utf-8")
        assert "my-custom-model" in aibom

    def test_add_multi_model_populates_aibom_routes(self, tmp_path: Path):
        # `add multi-model` on a governance project: the live project has no CCR
        # config yet mid-add (it's the file being installed), so detection must
        # fall back to the freshly-rendered staging config rather than emitting
        # an empty routes table. Detecting the *absent* live config would leave
        # the AIBOM saying "no routes" while the config.json being added has them.
        from project_init.concerns import apply_concern
        from project_init.upgrade import write_scaffold_record

        target = tmp_path / "p"
        preset = load_preset("obsidian-only")
        extra = overlay_layers("claude", no_plugin=False, governance=True)
        preset = {**preset, "layers": list(preset["layers"]) + extra}
        variables = make_variables(governance="true")
        created = scaffold(target, preset, variables, strict=True)
        write_scaffold_record(target, "obsidian-only", variables, created)
        assert not (target / ".agents" / "multi-model" / "config.json").exists()

        assert apply_concern(target, "multi-model", enable=True, apply=True) == 0
        assert (target / ".agents" / "multi-model" / "config.json").is_file()
        aibom = (target / _GOV / "ai-bom.generated.md").read_text(encoding="utf-8")
        assert "Detected CCR routes" in aibom
        assert "deepseek" in aibom, "AIBOM must show the routes just added, not an empty table"


# --------------------------------------------------------------------------- #
# Declarations lifecycle (seed-once + preserve)
# --------------------------------------------------------------------------- #
class TestDeclarationsLifecycle:
    def test_seeded_and_intrinsically_preserved(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        assert (target / _GOV / "ai-declarations.md").is_file()
        # Preserved intrinsically (not via config.yaml globs), so the lifecycle
        # holds even for projects that adopt governance after initial scaffold.
        assert ".agents/governance/ai-declarations.md" in _GOVERNANCE_USER_FILES
        assert ".agents/governance/SYSTEM_CARD.md" in _GOVERNANCE_USER_FILES
        assert ".agents/governance/NO_AI_SYSTEM.md" in _GOVERNANCE_USER_FILES
        assert ".agents/governance/config.json" in _GOVERNANCE_USER_FILES
        # The generated AIBOM must NOT be preserved — it has to refresh.
        assert ".agents/governance/ai-bom.generated.md" not in _GOVERNANCE_USER_FILES

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
    def test_valid_declaration_passes_where_silence_fails(self, tmp_path: Path):
        # Same scaffold, one file apart: nothing declared fails, a declaration passes.
        target = _scaffold(tmp_path / "p")
        assert _run_gate(target).returncode == 1
        _declare(target)
        r = _run_gate(target)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "governance gate passed" in r.stdout

    def test_valid_card_passes(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        _valid_card(target)
        r = _run_gate(target)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "governance gate passed" in r.stdout

    def test_example_card_is_not_gated(self, tmp_path: Path):
        # Nothing under the top-level examples/ counts as a real card: next to a
        # declaration it is neither validated nor a contradiction. The shipped
        # example is named *.example.md, so also plant a file the gate would
        # match by name (SYSTEM_CARD.md) — only the examples/ exclusion saves it.
        target = _scaffold(tmp_path / "p")
        assert (target / _GOV / "examples" / "SYSTEM_CARD.example.md").is_file()
        (target / _GOV / "examples" / "SYSTEM_CARD.md").write_text(
            "---\nrole: bogus\n---\n", encoding="utf-8"
        )
        _declare(target)
        r = _run_gate(target)
        assert r.returncode == 0, r.stdout + r.stderr
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

    def test_gate_root_is_cwd_independent(self, tmp_path: Path):
        # The gate must resolve the project root from the SCRIPT's location, not
        # the caller's CWD (git rev-parse --show-toplevel) — else running it from
        # inside another repo would validate that repo and vacuously pass, hiding
        # a real violation in the scaffolded project (PI review 2026-07).
        target = _scaffold(tmp_path / "p")
        deep = target / _GOV / "team" / "examples"
        deep.mkdir(parents=True)
        (deep / "SYSTEM_CARD.md").write_text("---\nrole: bogus\n---\n", encoding="utf-8")
        # An unrelated directory that is its own git repo (the trap for a
        # CWD/toplevel-based resolver — it has no governance card, so a
        # cwd-based gate would find nothing and pass).
        other = tmp_path / "other-repo"
        other.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(other), check=True)
        r = subprocess.run(
            ["bash", str(target / _GOV.parent / "scripts" / "governance_gate.sh")],
            cwd=str(other),
            capture_output=True,
            text=True,
        )
        assert r.returncode == 1, r.stdout + r.stderr
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
                "models_declared: .agents/governance/ai-declarations.md",
                f"models_declared: {bad}",
            ),
            encoding="utf-8",
        )
        r = _run_gate(target)
        assert r.returncode == 1
        assert "models_declared" in r.stdout


# --------------------------------------------------------------------------- #
# Silence is not a pass: a card, or a dated "ships no AI system" declaration
# --------------------------------------------------------------------------- #
class TestGateNeverPassesOnSilence:
    def test_no_card_and_no_declaration_fails_naming_both_ways_out(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        r = _run_gate(target)
        assert r.returncode == 1, r.stdout + r.stderr
        assert "SYSTEM_CARD.md" in r.stdout
        assert "NO_AI_SYSTEM.md" in r.stdout
        assert "declared_on" in r.stdout and "reason" in r.stdout
        assert "governance gate passed" not in r.stdout
        assert "nothing to check" not in r.stdout

    def test_the_files_the_failure_says_to_copy_exist(self, tmp_path: Path):
        # An instruction to copy a template that was never shipped is a dead end.
        target = _scaffold(tmp_path / "p")
        r = _run_gate(target)
        templates = set(re.findall(r"\.agents/governance/examples/[\w.]+\.md", r.stdout))
        assert templates == {
            ".agents/governance/examples/SYSTEM_CARD.template.md",
            ".agents/governance/examples/NO_AI_SYSTEM.template.md",
        }
        for rel in templates:
            assert (target / rel).is_file(), rel

    def test_missing_governance_dir_is_silence_not_an_exemption(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        shutil.rmtree(target / _GOV)
        r = _run_gate(target)
        assert r.returncode == 1, r.stdout + r.stderr
        assert "NO_AI_SYSTEM.md" in r.stdout

    @pytest.mark.parametrize(
        "overrides,expected",
        [
            ({"reason": None}, "missing/placeholder field: reason"),
            ({"reason": ""}, "missing/placeholder field: reason"),
            ({"reason": "<REPLACE: why>"}, "missing/placeholder field: reason"),
            ({"declared_on": None}, "missing/placeholder field: declared_on"),
            ({"declared_on": ""}, "missing/placeholder field: declared_on"),
            ({"declared_on": "<REPLACE: YYYY-MM-DD>"}, "missing/placeholder field: declared_on"),
            ({"declared_on": "last tuesday"}, "declared_on must be an ISO date"),
            ({"declared_on": "2026-02-30"}, "declared_on is not a valid date"),
            ({"declared_on": "2099-01-01"}, "declared_on is in the future"),
        ],
    )
    def test_declaration_without_a_real_reason_and_date_fails(
        self, tmp_path: Path, overrides: dict[str, str | None], expected: str
    ):
        target = _scaffold(tmp_path / "p")
        _declare(target, **overrides)
        r = _run_gate(target)
        assert r.returncode == 1, r.stdout + r.stderr
        assert expected in r.stdout
        assert "governance gate passed" not in r.stdout

    def test_declaration_without_frontmatter_fails_on_both_fields(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        (target / _GOV / "NO_AI_SYSTEM.md").write_text("This repo ships no AI.\n", encoding="utf-8")
        r = _run_gate(target)
        assert r.returncode == 1
        assert "field: reason" in r.stdout and "field: declared_on" in r.stdout

    def test_declaration_may_be_dated_today_but_not_tomorrow(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        _declare(target, declared_on=(date.today() + timedelta(days=1)).isoformat())
        assert _run_gate(target).returncode == 1
        _declare(target, declared_on=date.today().isoformat())
        assert _run_gate(target).returncode == 0

    def test_old_declaration_does_not_expire(self, tmp_path: Path):
        # Unlike a card's last_reviewed, a declaration carries no staleness
        # window: a recurring red on the honest majority would be rubber-stamped.
        target = _scaffold(tmp_path / "p")
        _declare(target, declared_on=(date.today() - timedelta(days=2000)).isoformat())
        r = _run_gate(target)
        assert r.returncode == 0, r.stdout + r.stderr

    @pytest.mark.parametrize("where", ["team", "examples"])
    def test_declaration_only_counts_at_the_governance_root(self, tmp_path: Path, where: str):
        # One fixed repo-level path; a copy filed elsewhere is still silence.
        target = _scaffold(tmp_path / "p")
        misfiled = _declare(target)
        dest = target / _GOV / where
        dest.mkdir(exist_ok=True)
        misfiled.rename(dest / "NO_AI_SYSTEM.md")
        r = _run_gate(target)
        assert r.returncode == 1, r.stdout + r.stderr

    def test_template_copied_verbatim_fails_until_filled(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        template = target / _GOV / "examples" / "NO_AI_SYSTEM.template.md"
        declaration = target / _GOV / "NO_AI_SYSTEM.md"
        shutil.copy(template, declaration)
        r = _run_gate(target)
        assert r.returncode == 1
        assert "field: reason" in r.stdout and "field: declared_on" in r.stdout
        # Filling in exactly the two placeholder lines is all it takes.
        filled = [
            f'reason: "{_GOOD_REASON}"'
            if line.startswith("reason:")
            else f"declared_on: {date.today().isoformat()}"
            if line.startswith("declared_on:")
            else line
            for line in template.read_text(encoding="utf-8").splitlines()
        ]
        declaration.write_text("\n".join(filled) + "\n", encoding="utf-8")
        r = _run_gate(target)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_card_and_declaration_together_contradict(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        _valid_card(target)
        _declare(target)
        r = _run_gate(target)
        assert r.returncode == 1, r.stdout + r.stderr
        assert "contradiction" in r.stdout
        assert "SYSTEM_CARD.md" in r.stdout and "NO_AI_SYSTEM.md" in r.stdout
        assert "governance gate passed" not in r.stdout

    def test_contradiction_holds_even_when_the_declaration_is_unfilled(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        _valid_card(target)
        _declare(target, reason=None)
        r = _run_gate(target)
        assert r.returncode == 1
        assert "contradiction" in r.stdout

    def test_card_alone_is_unchanged(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        _valid_card(target)
        r = _run_gate(target)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "OK   .agents/governance/SYSTEM_CARD.md" in r.stdout
        assert "contradiction" not in r.stdout


class TestUpgradeSurfacesTheGateChange:
    """A repo upgrading with no card and no declaration is told why CI will go
    red and exactly which file to add — through the packaged migration notes."""

    def test_note_names_the_file_and_the_fields(self):
        from project_init.migration_notes import notes_for_span

        (version, entry), *rest = notes_for_span("1.2.2", "1.2.3")
        assert version == "1.2.3" and not rest
        action = entry["action_required"] or ""
        for needle in (
            ".agents/governance/NO_AI_SYSTEM.md",
            ".agents/governance/SYSTEM_CARD.md",
            ".agents/governance/examples/NO_AI_SYSTEM.template.md",
            "reason",
            "declared_on",
            "governance_gate.sh",
        ):
            assert needle in action, needle

    def test_upgrade_output_carries_the_action(self, capsys):
        from project_init.upgrade import _print_migration_notes

        _print_migration_notes("1.2.2", "1.2.3")
        out = " ".join(capsys.readouterr().out.split())
        assert "action required" in out
        assert "NO_AI_SYSTEM.md" in out

    def test_a_repo_already_on_the_change_is_not_told_again(self):
        from project_init.migration_notes import notes_for_span

        assert "1.2.3" not in [v for v, _ in notes_for_span("1.2.3", "1.2.4")]
