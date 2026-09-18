"""A scaffolded PLAN.md opens with the project's done-gate (#988, item 2).

"Is this finished?" should be answered by a falsifier the repo itself states: a
`Done when:` line, and the `probed by:` check that proves it. Before this, no
template emitted a PLAN.md at all, so a scaffolded repo had nowhere to state one.

Asserted on the RENDERED file from the real CLI, for every preset, and on the
OPENING of the file rather than anywhere in it. A gate buried under other
content is one a reader never sees, so "somewhere in PLAN.md" would pass the
exact failure this exists to prevent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.__main__ import main
from project_init.scaffold import list_presets

_PRESETS = sorted(p["name"] for p in list_presets())


def _render_plan(target: Path, preset: str, language: str = "python") -> list[str]:
    """Scaffold *preset* through the CLI and return PLAN.md's non-blank lines."""
    rc = main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            preset,
            "--name",
            "gate-probe",
            "--description",
            "done-gate probe",
            "--language",
            language,
            "--lifecycle",
            "none",
        ]
    )
    assert rc == 0, f"scaffold of {preset} exited {rc}"
    plan = target / "PLAN.md"
    assert plan.is_file(), f"{preset}: no PLAN.md was scaffolded"
    return [line for line in plan.read_text(encoding="utf-8").splitlines() if line.strip()]


def _assert_opens_with_gate(lines: list[str], label: str) -> None:
    assert lines[0] == "# Plan — gate-probe", f"{label}: PLAN.md lost its title: {lines[0]!r}"
    assert lines[1].startswith("Done when: "), (
        f"{label}: PLAN.md must open with its `Done when:` line, got {lines[1]!r}"
    )
    assert lines[2].startswith("probed by: "), (
        f"{label}: the `Done when:` line must be followed by its `probed by:` probe, "
        f"got {lines[2]!r}"
    )


@pytest.mark.parametrize("preset", _PRESETS)
def test_every_preset_scaffolds_a_plan_that_opens_with_the_done_gate(tmp_path: Path, preset: str):
    _assert_opens_with_gate(_render_plan(tmp_path / "proj", preset), preset)


def test_the_gate_ships_without_a_language(tmp_path: Path):
    # The template is unconditional: a `--language none` project still gets it,
    # because "is this finished?" does not depend on the stack.
    _assert_opens_with_gate(_render_plan(tmp_path / "proj", "core", language="none"), "none")
