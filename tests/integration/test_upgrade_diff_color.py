"""#545: colorized unified diff in the upgrade/add/remove drift report.

`_colorize_diff` styles +/-/@@ lines; rich strips the colour on a non-TTY or
under NO_COLOR. Assertions target the diff *content* (after stripping ANSI), not
the escape codes, except where the presence/absence of colour is the point.
"""

from __future__ import annotations

import re
from pathlib import Path

from rich.console import Console

from project_init.__main__ import main
from project_init.upgrade import _colorize_diff, run_upgrade

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip(text: str) -> str:
    return _ANSI.sub("", text)


def _render(diff: str, *, color: bool) -> str:
    """Render a diff through a rich Console with colour forced on or off."""
    console = Console(
        force_terminal=True if color else None,
        no_color=not color,
        width=200,
    )
    with console.capture() as cap:
        console.print(_colorize_diff(diff))
    return cap.get()


_SAMPLE = (
    "--- current/CLAUDE.md\n"
    "+++ upgrade/CLAUDE.md\n"
    "@@ -1,3 +1,3 @@\n"
    " unchanged context line\n"
    "-old project tagline\n"
    "+new project tagline\n"
)


def test_content_preserved_after_stripping_ansi() -> None:
    out = _strip(_render(_SAMPLE, color=True))
    # Every diff line's text survives colouring — assert on content, not codes.
    assert "-old project tagline" in out
    assert "+new project tagline" in out
    assert "@@ -1,3 +1,3 @@" in out
    assert "unchanged context line" in out


def test_color_emits_ansi_for_changed_lines() -> None:
    out = _render(_SAMPLE, color=True)
    assert "\x1b[" in out  # styling present on a colour-capable sink


def test_no_color_env_falls_back_to_plain() -> None:
    out = _render(_SAMPLE, color=False)
    assert "\x1b[" not in out  # NO_COLOR / non-TTY → clean plain text
    assert "+new project tagline" in out


def test_added_and_removed_get_distinct_styles() -> None:
    # The added line carries a green code and the removed a red one, so a reader
    # can tell them apart — the whole point of the feature.
    added = _render("+brand new line\n", color=True)
    removed = _render("-deleted line\n", color=True)
    assert "32m" in added  # ANSI green
    assert "31m" in removed  # ANSI red


def _scaffold(target: Path) -> None:
    rc = main(
        [
            str(target),
            "--preset",
            "obsidian-only",
            "--non-interactive",
            "--name",
            "diff-color-fixture",
            "--description",
            "Diff color test",
            "--language",
            "python",
        ]
    )
    assert rc == 0


def test_real_drift_shows_changed_line(tmp_path: Path, capsys) -> None:
    # End-to-end: a one-line edit to a managed file must surface that line in the
    # drift report's diff body (content assertion, ANSI stripped).
    _scaffold(tmp_path)
    claude_md = tmp_path / "CLAUDE.md"
    original = claude_md.read_text()
    marker = "ZZZ_UNIQUE_DRIFT_MARKER_545"
    claude_md.write_text(original.replace("\n", f" {marker}\n", 1))

    run_upgrade(tmp_path, apply=False)
    out = _strip(capsys.readouterr().out)
    assert marker in out  # the drifted line appears in the rendered diff
