"""ADR-029 gateway wizard: the six-ask default path, its equivalence guarantee,
and the informed-consent echo (PI-895).

The collapse's contract: an Enter-only run must resolve every concern to the
exact value the pre-collapse Enter-only wizard produced; every group chooser is
reachable through the gateway; and the full resolution — led by the security
surface — is echoed before the gateway consents and before bootstrap runs.
"""

from __future__ import annotations

import project_init.__main__ as __main__
import project_init.wizard_prompts as _wiz


def _enter_only(monkeypatch, **kwargs):
    """Drive the wizard pressing Enter at everything (rich prompts → defaults)."""
    monkeypatch.setattr(_wiz, "_prompt", lambda _label, default="": default)
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: k.get("default", ""))
    monkeypatch.setattr("rich.prompt.IntPrompt.ask", lambda *a, **k: k.get("default", 1))
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: k.get("default", False))
    return __main__._gather_inputs_interactive(
        default_name="demo", no_plugin=False, profile=None, **kwargs
    )


def test_enter_only_matches_the_pre_collapse_defaults(monkeypatch):
    """The equivalence anchor: Enter-through must reproduce, field for field,
    what the pre-collapse wizard's Enter defaults produced (captured literal —
    if this changes, the standard setup changed for every user)."""
    inputs = _enter_only(monkeypatch)
    assert inputs.project_name == "demo"
    assert inputs.project_description == "demo project"
    assert inputs.language == "none"
    assert inputs.selected_mcps == []
    assert inputs.owner == ""
    assert inputs.license_choice == "none"
    assert inputs.devcontainer is False
    assert inputs.mise is False
    assert inputs.vscode is False
    assert inputs.agents == ["claude"]
    assert inputs.profile == "individual"
    assert inputs.python_version == ""
    assert inputs.review_cycles == 2
    assert inputs.delivery == "prototype"
    assert inputs.deploy == "none"
    assert inputs.iac == "none"
    assert inputs.multi_model is False
    assert inputs.governance is False
    assert inputs.observability is False
    assert inputs.memory == "obsidian-only"
    assert inputs.lifecycle == "github"
    assert inputs.want_docs is True
    assert inputs.renovate is True
    assert inputs.coauthor is True
    # Bootstrap's chooser defaults True pre-collapse and stays the final ask.
    assert inputs.bootstrap is True


def test_default_path_runs_no_group_chooser(monkeypatch):
    """The six-ask guarantee: with the gateway left closed, no group chooser
    may run — a regression here silently re-grows the wizard."""
    for chooser in (
        "_choose_profile_interactive",
        "_choose_delivery_interactive",
        "_choose_deploy_interactive",
        "_choose_iac_interactive",
        "_choose_mcps_interactive",
        "_choose_browser_interactive",
        "_choose_agents_interactive",
        "_choose_devcontainer_interactive",
        "_choose_mise_interactive",
        "_choose_vscode_interactive",
        "_choose_docs_interactive",
        "_choose_renovate_interactive",
        "_choose_multi_model_interactive",
        "_choose_governance_interactive",
        "_choose_observability_interactive",
        "_choose_memory_interactive",
        "_choose_lifecycle_interactive",
        "_choose_review_cycles_interactive",
        "_choose_coauthor_interactive",
    ):
        monkeypatch.setattr(
            _wiz,
            chooser,
            lambda *a, _c=chooser, **k: (_ for _ in ()).throw(
                AssertionError(f"{_c} must not run on the standard path")
            ),
        )
    monkeypatch.setattr(_wiz, "_choose_gateway_interactive", lambda pinned: set())
    monkeypatch.setattr(_wiz, "_choose_bootstrap_interactive", lambda: False)
    monkeypatch.setattr(_wiz, "_prompt", lambda _label, default="": default)
    inputs = __main__._gather_inputs_interactive(default_name="demo", no_plugin=False, profile=None)
    assert inputs.bootstrap is False


def test_opened_memory_group_runs_its_choosers(monkeypatch):
    """A gateway-opened group runs the pre-collapse choosers and their answers land."""
    monkeypatch.setattr(_wiz, "_prompt", lambda _label, default="": default)
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: k.get("default", False))
    monkeypatch.setattr(_wiz, "_choose_gateway_interactive", lambda pinned: {"memory"})
    monkeypatch.setattr(_wiz, "_choose_memory_interactive", lambda *a, **k: "obsidian-graphify-rag")
    monkeypatch.setattr(_wiz, "_choose_lifecycle_interactive", lambda *a, **k: "github")
    monkeypatch.setattr(_wiz, "_choose_review_cycles_interactive", lambda *a, **k: 5)
    inputs = __main__._gather_inputs_interactive(default_name="demo", no_plugin=False, profile=None)
    assert inputs.memory == "obsidian-graphify-rag"
    assert inputs.review_cycles == 5


def test_gateway_reprompts_on_invalid_selection(monkeypatch, capsys):
    """The gateway keeps the leaf-parser contract: invalid input re-prompts and
    the retry is honored — never silently dropped (PI-195 lineage)."""
    answers = iter(["9,junk", "6"])
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: next(answers))
    opened = _wiz._choose_gateway_interactive({})
    assert "Invalid selection(s): 9, junk." in capsys.readouterr().out
    assert opened == {"memory"}


def test_gateway_lists_pinned_flags(monkeypatch, capsys):
    """A flag user sees their choices annotated at the gateway, per group."""
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: "")
    _wiz._choose_gateway_interactive({"memory": ["--memory", "--lifecycle"]})
    out = capsys.readouterr().out
    assert "pinned: --memory, --lifecycle" in out


def test_preview_echo_surfaces_the_security_resolution(monkeypatch, capsys):
    """The security surface is echoed, not silently defaulted (harbor J1):
    enforcement, egress, lifecycle gate, MCP set, agent surfaces, governance —
    shown BEFORE the gateway so accepting the standard setup is informed."""
    _enter_only(monkeypatch)
    out = capsys.readouterr().out
    assert "Standard setup" in out
    assert "advisory" in out  # enforcement mode (individual profile)
    assert "marketplace egress on" in out
    assert "github / 2" in out  # lifecycle / review cycles
    assert "claude" in out  # agent surfaces
    assert "safety.allow starts [] (deny-by-default)" in out


def test_preview_echo_positions_the_rag_tier_for_preset_memory(monkeypatch, capsys):
    """ADR-024: when the preset pins memory and the ladder chooser never runs,
    the echo still positions graph/RAG as opt-in, scale-gated rungs."""
    _enter_only(monkeypatch, preset_name="obsidian-only")
    out = capsys.readouterr().out
    assert "tier 1" in out
    assert "multi-project" in out
    assert "obsidian-only" in out


def test_opened_group_re_echoes_the_final_resolution(monkeypatch, capsys):
    """When a group changed something, the resolution is re-echoed before the
    final question so what scaffolds is never stale relative to what was shown."""
    monkeypatch.setattr(_wiz, "_prompt", lambda _label, default="": default)
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: k.get("default", False))
    monkeypatch.setattr(_wiz, "_choose_gateway_interactive", lambda pinned: {"memory"})
    monkeypatch.setattr(_wiz, "_choose_memory_interactive", lambda *a, **k: "auto")
    monkeypatch.setattr(_wiz, "_choose_lifecycle_interactive", lambda *a, **k: "none")
    __main__._gather_inputs_interactive(default_name="demo", no_plugin=False, profile=None)
    out = capsys.readouterr().out
    assert out.count("Resolved configuration") == 1
    assert "none / 0" in out  # re-echo shows the changed lifecycle / cycles
