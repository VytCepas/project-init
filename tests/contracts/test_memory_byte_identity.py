"""Byte-identity contract for the memory decomposition (#466, PI-189).

Moving memory/vault content base→obsidian overlay and gating it behind
`{{#if memory}}` must render the existing obsidian-only / obsidian-graphify
backends BYTE-IDENTICALLY. `memory/` and `vault/` are excluded from the upgrade
manifest (`_PRESERVE_DIRS`), so the upgrade round-trip does NOT cover the move —
this fresh-scaffold snapshot against a committed pre-move baseline is the only
thing that does.

The baseline fixtures in tests/fixtures/memory_baseline/ were captured BEFORE
the move (tools/scratch gen_baseline.py). If this test fails, the move/gating
changed rendered bytes — fix the template, do NOT regenerate the baseline.

Exception (#497): the `auto`/`obsidian` tier split kept every file byte-identical
EXCEPT `lint_memory.sh`, which gained deterministic staleness checks (a deliberate
feature, not move-drift). Only that one hash was re-pinned.

Exception (#496): the code-map feature intentionally ADDS
`.claude/scripts/gen_code_map.py` and edits AGENTS.md (the read-the-map pointer)
and the justfile (the `code-map` recipe). Only those keys were re-pinned, after
verifying every OTHER file still matched the baseline — the move invariant is
intact for everything else.

Exception (#498): the memory descriptor intentionally edits `.claude/config.yaml`
(adds `tier` + `graph_path` to the `memory:` block, and later a top-level
`project_init_contract_version` to the `project:` block, ADR-025). Only that key
was re-pinned, after verifying every other file still matched.

Exception (LightRAG cleanup): removing the dead `.claude/memory/.lightrag/`
gitignore line (ADR-024) re-pinned `.gitignore` only.

Exception (PI-526): the concern-decoupled skills `save_memory`, `status`, and
`session_summary` gained deterministic presence-checks in their bodies (don't
write to `.claude/memory/` or `.claude/vault/` when that concern was declined) —
a deliberate fix, not move-drift. Only those three SKILL.md hashes were re-pinned
(no_plugin combos), after verifying every other file still matched.

Exception (PI-550): `dag_workflow.py` gained `_strip_text_flag_values` so the
command-guard no longer false-positives on blocked-command phrases inside
free-text flag values. A deliberate guard fix, not move-drift. Only the
`.claude/hooks/dag_workflow.py` hash was re-pinned across all four combos, after
verifying every other file still matched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "memory_baseline"

COMBOS = [
    ("obsidian-only", False),
    ("obsidian-only", True),
    ("obsidian-graphify", False),
    ("obsidian-graphify", True),
]


# Generated/lifecycle-touched files excluded from the memory-move comparison
# (#476): CAPABILITIES.md is a regenerated inventory that gained a "GitHub
# lifecycle" row + the lifecycle skills now sourced from lifecycle_fallback;
# plugin-mode settings.json gained the project-init-lifecycle plugin enablement.
# Neither is part of the memory move this contract guards.
_GENERATED = {".claude/CAPABILITIES.md"}

# Files added or intentionally edited AFTER the frozen baseline was captured —
# legitimate content changes, not the memory move this contract guards. Excluded
# from both sides (same mechanism as the settings.json / CAPABILITIES.md carve-
# outs above); their correctness is covered by the focused template/governance
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
#   • package_guard.py / settings.json / AGENTS.md — new supply-chain install
#     guard hook (uv add/bun add/pip install/npm install/cargo add checked
#     against PyPI/npm/crates.io), wired into settings.json and documented (#564)
#     memory-move content change
_ADDED_SINCE_BASELINE = {
    ".gitleaks.toml",
    ".github/workflows/ci.yml",
    ".claude/scripts/setup_github.sh",
    ".claude/scripts/create_issue.sh",
    ".github/workflows/board-automation.yml",
    ".claude/config.yaml",
    "mypy.ini",
    "justfile",
    ".claude/hooks/post_edit_lint.sh",
    ".claude/rules/python.md",
    ".claude/rules/go.md",
    ".claude/hooks/session_setup.sh",
    ".claude/hooks/_py.sh",
    ".claude/scripts/gh_host.sh",
    ".claude/scripts/lint_memory.sh",
    ".claude/scripts/monitor_pr.sh",
    ".claude/scripts/start_issue.sh",
    ".claude/hooks/github_command_guard.sh",
    ".claude/hooks/pre_commit_gate.sh",
    ".claude/hooks/workflow_state_reminder.sh",
    ".claude/hooks/package_guard.py",
    ".claude/settings.json",
    "AGENTS.md",
    ".claude/rules/rust.md",
    ".claude/rules/typescript.md",
}


def _manifest(target: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(target.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(target)
        # Skip Python bytecode caches: a developer's local templates/ tree may
        # carry __pycache__ that scaffold() copies, but a clean checkout (CI)
        # does not — including them would be spurious drift.
        if "__pycache__" in rel.parts or rel.suffix == ".pyc":
            continue
        out[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.mark.parametrize("preset_name,no_plugin", COMBOS)
def test_memory_move_byte_identical(preset_name: str, no_plugin: bool, tmp_path: Path):
    preset = load_preset(preset_name)
    stack = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    # lifecycle=True: the baseline was captured when the lifecycle files lived in
    # base, so a full (lifecycle-on) scaffold is what reproduces it (#476).
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

    drop = set(_GENERATED) | _ADDED_SINCE_BASELINE
    if not no_plugin:
        drop.add(".claude/settings.json")
    got = {k: v for k, v in got.items() if k not in drop}

    mode = "no_plugin" if no_plugin else "plugin"
    expected = json.loads((FIXTURES / f"{preset_name}__{mode}.json").read_text())
    expected = {k: v for k, v in expected.items() if k not in drop}

    added = sorted(set(got) - set(expected))
    removed = sorted(set(expected) - set(got))
    assert not added and not removed, f"path drift — added={added} removed={removed}"
    mismatched = sorted(p for p in expected if got[p] != expected[p])
    assert not mismatched, f"content drift in: {mismatched}"
