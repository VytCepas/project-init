"""PI-195: execution coverage for the interactive wizard leaf parsers.

These were previously reached only via stubs (every leaf was monkeypatched
away in the integration tests), so their number-parsing / dedup / fallback
branches never actually ran. Here we drive them directly with canned prompts.
"""

from __future__ import annotations

import pytest

from project_init import __main__
from project_init.mcps import MCP_CATALOG


def test_choose_preset_interactive_out_of_range_falls_back(monkeypatch):
    presets = [{"name": "a", "description": "x"}, {"name": "b", "description": "y"}]
    monkeypatch.setattr("rich.prompt.IntPrompt.ask", lambda *a, **k: 99)
    assert __main__._choose_preset_interactive(presets) is presets[0]


def test_choose_preset_interactive_valid_choice(monkeypatch):
    presets = [{"name": "a", "description": "x"}, {"name": "b", "description": "y"}]
    monkeypatch.setattr("rich.prompt.IntPrompt.ask", lambda *a, **k: 2)
    assert __main__._choose_preset_interactive(presets) is presets[1]


def test_choose_mcps_interactive_parses_and_dedups(monkeypatch):
    # Duplicates collapse; out-of-range and non-numeric tokens are ignored.
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: "1,1,99,abc")
    selected = __main__._choose_mcps_interactive(MCP_CATALOG)
    assert [m["id"] for m in selected] == [MCP_CATALOG[0]["id"]]


def test_choose_mcps_interactive_empty_skips(monkeypatch):
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: "")
    assert __main__._choose_mcps_interactive(MCP_CATALOG) == []


@pytest.mark.parametrize("answer", [True, False])
def test_choose_multi_model_interactive_returns_confirm(monkeypatch, answer):
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: answer)
    assert __main__._choose_multi_model_interactive() is answer


def test_choose_multi_model_interactive_shows_messaging(monkeypatch, capsys):
    """#352: the wizard must explain what it does + the native alternatives before
    asking, so the choice is informed."""
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)
    __main__._choose_multi_model_interactive()
    out = capsys.readouterr().out
    # Single-token substrings survive 80-col panel wrapping.
    assert "/model" in out
    assert "deepseek,deepseek-chat" in out
    assert "Alternatives" in out
    assert "gemini" in out  # the native-harness alternative is surfaced
