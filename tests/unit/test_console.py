"""Unit tests for the shared wizard console (PI-645).

Covers the single-house-style menu row, the preset table and its off-TTY plain
fallback, and that the scaffolding spinner is an inert no-op when captured.
"""

from __future__ import annotations

from rich.console import Console

import project_init.console as pc


def test_option_line_single_house_style() -> None:
    """Number is the styled token and the row carries name + description."""
    line = pc.option_line(2, "core", "no memory backend")
    assert "2" in line and "core" in line and "no memory backend" in line
    assert "(recommended)" not in line
    assert "(recommended)" in pc.option_line(1, "obsidian-only", "the default", recommended=True)


def test_is_interactive_false_under_capture(capsys) -> None:
    """Captured/piped output is never a TTY, so richer devices stand down."""
    assert pc.is_interactive() is False
    capsys.readouterr()


def test_render_presets_plain_lists_every_preset(capsys) -> None:
    """Off a TTY the table degrades to a plain numbered list of all presets."""
    presets = [
        {"name": "core", "description": "no memory", "vars": {"memory_stack": "none"}},
        {"name": "obsidian-only", "description": "vault only", "vars": {"memory_stack": "obsidian-only"}},
    ]
    pc.render_presets(presets, default_idx=2)
    out = capsys.readouterr().out
    assert "Available presets" in out
    assert "core" in out and "obsidian-only" in out
    # The recommended marker lands on the default index only.
    assert out.count("(recommended)") == 1


def test_render_presets_table_when_interactive(monkeypatch, capsys) -> None:
    """Forced-TTY path renders the aligned table incl. the Memory column."""
    rec = Console(theme=pc.WIZARD_THEME, force_terminal=True, width=100)
    monkeypatch.setattr(pc, "console", rec)
    monkeypatch.setattr(pc, "is_interactive", lambda: True)
    presets = [{"name": "core", "description": "no memory", "vars": {"memory_stack": "none"}}]
    pc.render_presets(presets, default_idx=1)
    out = capsys.readouterr().out
    assert "core" in out and "none" in out
    assert "recommended" in out


def test_render_presets_handles_missing_memory(capsys) -> None:
    """A preset without a memory_stack var shows a dash, not a KeyError."""
    pc.render_presets([{"name": "x", "description": "d", "vars": {}}], default_idx=1)
    assert "x" in capsys.readouterr().out


def test_scaffolding_is_noop_off_tty(capsys) -> None:
    """The spinner emits nothing to stdout when stderr is not a TTY."""
    with pc.scaffolding("working"):
        ran = True
    assert ran
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "working" not in captured.err
