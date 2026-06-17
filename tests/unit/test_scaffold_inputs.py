"""PI-190: ScaffoldInputs (named record replacing the positional input tuple)
and the single source for the migrate/backfill "off" variable defaults."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from project_init.__main__ import ScaffoldInputs, _build_parser, _resolve_inputs


def test_resolve_inputs_returns_named_record():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "x", "--non-interactive", "--preset", "obsidian-only",
            "--name", "demo", "--description", "d", "--language", "python", "--no-plugin",
        ]
    )
    inputs = _resolve_inputs(args, parser, Path("x"))
    assert isinstance(inputs, ScaffoldInputs)
    assert inputs.project_name == "demo"
    assert inputs.language == "python"
    assert inputs.agents == ["claude"]
    assert inputs.no_plugin is True
    assert inputs.selected_mcps == []


def test_resolve_inputs_none_when_interactive():
    parser = _build_parser()
    args = parser.parse_args(["x", "--preset", "obsidian-only"])
    assert _resolve_inputs(args, parser, Path("x")) is None


def test_scaffold_inputs_is_frozen():
    si = ScaffoldInputs(
        "n", "d", "python", [], "", "none", False, False, False, ["claude"], False
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        si.project_name = "x"  # type: ignore[misc]


def test_migrate_and_backfill_share_off_defaults():
    """PI-190: the ~16 'off' overlay/governance defaults come from one source."""
    from project_init.upgrade import _overlay_off_defaults

    d = _overlay_off_defaults()
    assert d["agents"] == "claude"
    assert d["no_plugin"] == "true"
    assert d["license"] == "none"
    assert all(d[k] == "" for k in ("devcontainer", "mise", "vscode", "codex", "gemini"))
