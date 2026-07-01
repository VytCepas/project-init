"""Byte-identity contract for the lifecycle decomposition (#476, PI-189).

Moving the GitHub lifecycle (DAG library, scripts, board/wiki/validation
workflows, issue/PR templates, guard hooks, lifecycle skills) out of base into
the ``lifecycle`` / ``lifecycle_fallback`` overlays and gating the mixed files
(settings hooks, pre-push, AGENTS/project-init prose) behind ``{{#if lifecycle}}``
must render the default lifecycle-ON scaffold BYTE-IDENTICALLY.

Unlike memory, the lifecycle files are NOT in ``_PRESERVE_DIRS``, so the upgrade
round-trip covers them — but only via the recorded layer set. This fresh-scaffold
snapshot against a committed pre-move baseline is the direct guard on the move.

The baseline fixtures in tests/fixtures/lifecycle_baseline/ were captured BEFORE
the move. If this test fails, the move/gating changed rendered bytes — fix the
template, do NOT regenerate the baseline.

Exception (#496): the code-map feature intentionally ADDS
`.claude/scripts/gen_code_map.py` and edits AGENTS.md + the justfile. Only those
three keys were re-pinned, after verifying every other file still matched the
baseline — the move invariant is intact for everything else.

Exception (#497/#498): later features re-pinned `lint_memory.sh` (staleness) and
`.claude/config.yaml` (memory descriptor `tier`/`graph_path`, then the top-level
`project_init_contract_version`, ADR-025) the same way — only the intentionally
changed key, after verifying no other drift.

Exception (PI-526): the concern-decoupled skills `save_memory`, `status`, and
`session_summary` gained deterministic presence-checks in their bodies — a
deliberate fix, not move-drift. Only those three SKILL.md hashes were re-pinned
(no_plugin combos), after verifying every other file still matched.

Exception (PI-550): `dag_workflow.py` gained `_strip_text_flag_values` so the
command-guard no longer false-positives on blocked-command phrases inside
free-text flag values (`--body`/`-m`/`--title`/`--notes`). A deliberate guard
fix, not move-drift. Only the `.claude/hooks/dag_workflow.py` hash was re-pinned
across all four combos, after verifying every other file still matched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "lifecycle_baseline"

COMBOS = [
    ("obsidian-only", False),
    ("obsidian-only", True),
    ("obsidian-graphify", False),
    ("obsidian-graphify", True),
]


# Generated inventories regenerated every scaffold/upgrade — NOT part of the
# static template move this contract guards, and they legitimately gain a
# "GitHub lifecycle: on/off" row + the lifecycle skills now sourced from the
# lifecycle_fallback overlay (#476). Their correctness is covered by
# test_lifecycle_none.py, not byte-identity.
_GENERATED = {".claude/CAPABILITIES.md"}

# Files added or intentionally edited AFTER the frozen baseline was captured —
# legitimate content changes, not the static template move this contract guards.
# Excluded from both sides (same mechanism as the settings.json / CAPABILITIES.md
# carve-outs); their correctness is covered by the focused template/governance
# contracts, not byte-identity.
#   • .gitleaks.toml — new base file shipping with the gitleaks CI job (#554)
#   • ci.yml — gained the all-green "CI gate" job (#555)
#   • setup_github.sh — bare required-check contexts + board SSOT (#555/#556)
#   • create_issue.sh / board-automation.yml / config.yaml — board-number SSOT (#556)
#   • session_setup.sh — `uv sync --group dev`, no silent-failure masking (#552/#553)
#   • mypy.ini / justfile / post_edit_lint.sh / python.md — mypy --strict gate:
#     new config file, `typecheck` recipe wired into the Python `ci` recipe,
#     mypy wired into the edit-time lint hook, rule file updated (#558)
#   • every shipped .sh script — reformatted with `shfmt -w -i 2` so the new
#     shellcheck+shfmt scaffold gate (#562) doesn't fail against its own
#     output on a fresh scaffold; a one-time whole-fleet reformat, not a
#     lifecycle-move content change
_ADDED_SINCE_BASELINE = {
    ".gitleaks.toml",
    ".github/workflows/ci.yml",
    ".claude/scripts/setup_github.sh",
    ".claude/scripts/create_issue.sh",
    ".github/workflows/board-automation.yml",
    ".claude/config.yaml",
    ".claude/hooks/session_setup.sh",
    "mypy.ini",
    "justfile",
    ".claude/hooks/post_edit_lint.sh",
    ".claude/rules/python.md",
    ".claude/rules/go.md",
    ".claude/hooks/_py.sh",
    ".claude/scripts/gh_host.sh",
    ".claude/scripts/lint_memory.sh",
    ".claude/scripts/monitor_pr.sh",
    ".claude/scripts/start_issue.sh",
    ".claude/hooks/github_command_guard.sh",
    ".claude/hooks/pre_commit_gate.sh",
    ".claude/hooks/workflow_state_reminder.sh",
}


def _manifest(target: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(target.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(target)
        if "__pycache__" in rel.parts or rel.suffix == ".pyc":
            continue
        if rel.as_posix() in _GENERATED:
            continue
        out[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.mark.parametrize("preset_name,no_plugin", COMBOS)
def test_lifecycle_move_byte_identical(preset_name: str, no_plugin: bool, tmp_path: Path):
    preset = load_preset(preset_name)
    stack = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    extra = overlay_layers([], no_plugin=no_plugin, memory_stack=stack, lifecycle=True)
    preset = {**preset, "layers": [*preset["layers"], *extra]}
    variables = make_variables(
        memory_stack=stack,
        plugin_mode="" if no_plugin else "true",
        no_plugin="true" if no_plugin else "",
    )
    target = tmp_path / "proj"
    scaffold(target, preset, variables)
    got = _manifest(target)

    # Plugin-mode settings.json legitimately gains the project-init-lifecycle
    # plugin enablement (#476 plugin split) — an intended edit, not move drift.
    # The no-plugin hook gating IS designed byte-identical-when-ON, so it stays
    # in the comparison. The plugin-mode change is covered by test_lifecycle_none.
    drop = set(_GENERATED) | _ADDED_SINCE_BASELINE
    if not no_plugin:
        drop.add(".claude/settings.json")
    got = {k: v for k, v in got.items() if k not in drop}

    mode = "no_plugin" if no_plugin else "plugin"
    expected = json.loads((FIXTURES / f"{preset_name}__{mode}.json").read_text())
    # The pre-move baseline still carries the generated inventories; drop the
    # same keys so the comparison matches the move-focused manifest above.
    expected = {k: v for k, v in expected.items() if k not in drop}

    added = sorted(set(got) - set(expected))
    removed = sorted(set(expected) - set(got))
    assert not added and not removed, f"path drift — added={added} removed={removed}"
    mismatched = sorted(p for p in expected if got[p] != expected[p])
    assert not mismatched, f"content drift in: {mismatched}"
