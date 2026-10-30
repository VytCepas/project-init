"""PI-195: execution coverage for the interactive wizard leaf parsers.

These were previously reached only via stubs (every leaf was monkeypatched
away in the integration tests), so their number-parsing / dedup / fallback
branches never actually ran. Here we drive them directly with canned prompts.
"""

from __future__ import annotations

import pytest

import project_init.wizard_prompts as _wiz
from project_init import __main__
from project_init.mcps import MCP_CATALOG


def test_choose_preset_interactive_out_of_range_reprompts(monkeypatch, capsys):
    """2026-07 QA: a typo'd menu number must re-prompt, not silently pick the
    default — the user's next answer wins."""
    presets = [{"name": "a", "description": "x"}, {"name": "b", "description": "y"}]
    answers = iter([99, 2])
    monkeypatch.setattr("rich.prompt.IntPrompt.ask", lambda *a, **k: next(answers))
    assert __main__._choose_preset_interactive(presets) is presets[1]
    assert "Invalid choice" in capsys.readouterr().out


def test_choose_preset_interactive_valid_choice(monkeypatch):
    presets = [{"name": "a", "description": "x"}, {"name": "b", "description": "y"}]
    monkeypatch.setattr("rich.prompt.IntPrompt.ask", lambda *a, **k: 2)
    assert __main__._choose_preset_interactive(presets) is presets[1]


def test_choose_mcps_interactive_parses_and_dedups(monkeypatch):
    # Duplicates collapse silently; a fully-valid answer needs no re-prompt.
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: "1,1")
    selected = __main__._choose_mcps_interactive(MCP_CATALOG)
    assert [m["id"] for m in selected] == [MCP_CATALOG[0]["id"]]


def test_choose_mcps_interactive_invalid_tokens_reprompt(monkeypatch, capsys):
    """2026-07 QA: out-of-range / non-numeric tokens must not be silently
    dropped (the non-interactive --mcps path errors on them) — re-ask."""
    answers = iter(["1,99,abc", "2"])
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: next(answers))
    selected = __main__._choose_mcps_interactive(MCP_CATALOG)
    assert [m["id"] for m in selected] == [MCP_CATALOG[1]["id"]]
    out = capsys.readouterr().out
    assert "99" in out and "abc" in out


def test_choose_mcps_interactive_empty_skips(monkeypatch):
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: "")
    assert __main__._choose_mcps_interactive(MCP_CATALOG) == []


def test_gather_inputs_interactive_enter_defaults_uses_description_default(monkeypatch):
    """A full interactive accept-defaults flow must not loop forever on an empty
    required description; it derives a valid default from the accepted name."""
    monkeypatch.setattr(_wiz, "_prompt", lambda _label, default="": default)
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: k.get("default", ""))
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: k.get("default", False))

    result = __main__._gather_inputs_interactive(
        default_name="demo",
        no_plugin=False,
        profile="individual",
        cli_overlays=("prototype", "none", "none", False, False, False),
        memory_flag="obsidian-only",
        lifecycle_flag="github",
        no_docs=True,
        no_renovate=True,
        cli_language="none",
        cli_agents="claude,codex",
    )

    assert result.project_name == "demo"
    assert result.project_description == "demo project"


def test_gather_inputs_interactive_honors_explicit_agents_claude(monkeypatch):
    """`--agents claude` (interactive) must yield a claude-only project, not open
    the surface chooser — the chooser can never return claude-only, so an absent
    flag and an explicit `claude` had been conflated (default was "claude")."""
    monkeypatch.setattr(_wiz, "_prompt", lambda _label, default="": default)
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: k.get("default", ""))
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: k.get("default", False))

    def _fail_chooser():
        raise AssertionError("surface chooser must not run when --agents is explicit")

    monkeypatch.setattr(_wiz, "_choose_agents_interactive", _fail_chooser)

    result = __main__._gather_inputs_interactive(
        default_name="demo",
        no_plugin=False,
        profile="individual",
        cli_overlays=("prototype", "none", "none", False, False, False),
        memory_flag="obsidian-only",
        lifecycle_flag="github",
        no_docs=True,
        no_renovate=True,
        cli_language="none",
        cli_agents="claude",
    )

    assert result.agents == ["claude"]


def test_gather_inputs_interactive_absent_agents_opens_chooser(monkeypatch):
    """An absent --agents flag (None) opens the surface chooser when the
    integrations group is opened at the gateway (ADR-029); an unopened gateway
    keeps the claude-only default, which the standard-path test pins."""
    monkeypatch.setattr(_wiz, "_prompt", lambda _label, default="": default)
    monkeypatch.setattr(_wiz, "_choose_gateway_interactive", lambda pinned: {"integrations"})
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: k.get("default", ""))
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: k.get("default", False))

    called = []
    monkeypatch.setattr(
        _wiz, "_choose_agents_interactive", lambda: called.append(True) or ["claude", "vscode"]
    )

    result = __main__._gather_inputs_interactive(
        default_name="demo",
        no_plugin=False,
        profile="individual",
        cli_overlays=("prototype", "none", "none", False, False, False),
        memory_flag="obsidian-only",
        lifecycle_flag="github",
        no_docs=True,
        no_renovate=True,
        cli_language="none",
        cli_agents=None,
    )

    assert called == [True]
    assert result.agents == ["claude", "vscode"]


def test_prompt_menu_index_reprompts_until_in_range(monkeypatch, capsys):
    """2026-07 QA: the shared numbered-menu helper (preset/profile/delivery/
    deploy/iac/memory/lifecycle) re-asks on out-of-range answers."""
    answers = iter([0, 99, 3])
    monkeypatch.setattr("rich.prompt.IntPrompt.ask", lambda *a, **k: next(answers))
    assert __main__._prompt_menu_index("Pick", 5, default=1) == 3
    out = capsys.readouterr().out
    assert out.count("Invalid choice") == 2
    assert "between 1 and 5" in out


@pytest.mark.parametrize("answer", [True, False])
def test_choose_multi_model_interactive_returns_confirm(monkeypatch, answer):
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: answer)
    assert __main__._choose_multi_model_interactive() is answer


@pytest.mark.parametrize("answer", [True, False])
def test_choose_coauthor_interactive_returns_confirm(monkeypatch, answer):
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: answer)
    assert __main__._choose_coauthor_interactive() is answer


def test_choose_coauthor_interactive_shows_trailer(monkeypatch, capsys):
    """#888: the wizard states the exact trailer it will add before asking."""
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)
    __main__._choose_coauthor_interactive()
    assert "Co-Authored-By: Claude" in capsys.readouterr().out


def test_choose_multi_model_interactive_shows_messaging(monkeypatch, capsys):
    """#352: the wizard must explain what it does + the native alternatives before
    asking, so the choice is informed."""
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)
    __main__._choose_multi_model_interactive()
    out = capsys.readouterr().out
    # Single-token substrings survive 80-col panel wrapping.
    assert "/model" in out
    assert "deepseek,deepseek-v4-flash" in out
    assert "Alternatives" in out
    assert "codex" in out  # the native-harness alternative is surfaced


@pytest.mark.parametrize("answer", [True, False])
def test_choose_observability_interactive_returns_confirm(monkeypatch, answer):
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: answer)
    assert __main__._choose_observability_interactive() is answer


def test_choose_observability_interactive_shows_messaging(monkeypatch, capsys):
    """#404: the wizard must explain what it ships (file-based, no backend) before
    asking, so the choice is informed."""
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)
    __main__._choose_observability_interactive()
    out = capsys.readouterr().out
    # Single-token substrings survive 80-col panel wrapping.
    assert "usage_report.py" in out
    assert "egress" in out.lower()
