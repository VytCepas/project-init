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
`.agents/scripts/gen_code_map.py` and edits AGENTS.md + the justfile. Only those
three keys were re-pinned, after verifying every other file still matched the
baseline — the move invariant is intact for everything else.

Exception (#497/#498): later features re-pinned `lint_memory.sh` (staleness) and
`.agents/config.yaml` (memory descriptor `tier`/`graph_path`, then the top-level
`project_init_contract_version`, ADR-025) the same way — only the intentionally
changed key, after verifying no other drift.

Exception (PI-526): the concern-decoupled skills `save_memory`, `status`, and
`session_summary` gained deterministic presence-checks in their bodies — a
deliberate fix, not move-drift. Only those three SKILL.md hashes were re-pinned
(no_plugin combos), after verifying every other file still matched.

Exception (PI-550): `dag_workflow.py` gained `_strip_text_flag_values` so the
command-guard no longer false-positives on blocked-command phrases inside
free-text flag values (`--body`/`-m`/`--title`/`--notes`). A deliberate guard
fix, not move-drift. Only the `.agents/hooks/dag_workflow.py` hash was re-pinned
across all four combos, after verifying every other file still matched.

Exception (PI-570): `ruff.toml` gained the RUF/PERF/PTH/RET/ARG/A/S/BLE rule
groups (per-language quality-gate strictness pass) — a deliberate content
change, not move-drift. `.agents/hooks/package_guard.py` also picked up
`# noqa: S310` placement fixes for the new `S` rule group; it was already
excluded above. Only `ruff.toml` is newly excluded here, after verifying
every other file still matched.

Exception (2026-07 review): a batch of deliberate content fixes were re-pinned
after verifying no other file drifted — `dag_workflow.py` (git-global-option
normalization + GraphQL-merge rule + interpreter-heredoc scanning),
`.gitignore` (stopped ignoring the committed `.codex/` wiring), `prod_guard.py`
(rm split-flag detection), `commit-msg` (corrected install comment), and the
fallback hooks `pre_commit_gate.sh` / `post_edit_lint.sh` (cd to repo root so a
subdirectory session lints the right paths).

Exception (init-lint fix): `dag_workflow.py` gained three `# noqa: S603`
directives on its `subprocess.run` calls — the scaffolded `ruff.toml` selects
`S` and lints `.agents/**`, so a fresh lifecycle-on project's `just lint` failed
on those argv-list (never shell-string) calls, mirroring the `# noqa: S310`
package_guard.py already carries. Only the `.agents/hooks/dag_workflow.py` hash
was re-pinned across all four combos, after verifying every other file matched.

Exception (2026-07 review, second pass): `dag_workflow.py` closed the
quoted-global-option guard bypass (`git -c foo='a b' push …`), capped its
per-subprocess timeout below the hook budget, and made the nojira "PR already
exists" short-circuit check the PR is OPEN. Deliberate guard fixes, not
move-drift — only the `.agents/hooks/dag_workflow.py` hash was re-pinned across
all four combos, after verifying every other file still matched.

Exception (CI-status fix): `check_ci_green` now folds a StatusContext entry's
`state` field (classic commit statuses — Vercel/Codecov/legacy CI — carry
`state`, not `status`/`conclusion`) so a green commit status is no longer
miscounted as "still running" forever, blocking the merge gate. Deliberate bug
fix, not move-drift — only the `.agents/hooks/dag_workflow.py` hash was re-pinned
across all four combos, after verifying every other file still matched.

Exception (PI-643): the git-config / editor-hiding parity sweep enriched two base
files — `.gitignore` (python tool caches: `.mypy_cache/`, `.coverage`, etc.;
mkdocs `site/` + typedoc `_site/` docs build output; `*.swo` / `*.log`) and
`.gitattributes` (`* text=auto`, `linguist-generated` for the `.claude/` mirror
and lockfiles, `linguist-vendored` for the vault). Deliberate content additions,
not move-drift. Only those two hashes were re-pinned across all four combos,
after verifying every other file still matched.
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
_GENERATED = {".agents/CAPABILITIES.md"}

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
#   • package_guard.py / settings.json / AGENTS.md — new supply-chain install
#     guard hook (uv add/bun add/pip install/npm install/cargo add checked
#     against PyPI/npm/crates.io), wired into settings.json and documented (#564)
#     lifecycle-move content change
#   • board-automation.yml / issue-validation.yml — self-populating board
#     metadata: dual-format ("### Heading" + "- Field: value") body parsing so
#     issues created outside the web form still populate all board fields, plus
#     auto-ensuring the type label from the body "- Type:" for MCP/API issues
#   • skills/report_upstream_issue/SKILL.md + skills/INDEX.md — new default-on
#     skill that routes tooling/scaffolding bugs upstream to project-init; only
#     the --no-plugin combos copy the skill in (plugin mode ships it via the
#     workflow plugin), and the INDEX gains its row
#   • skills/token_efficiency/SKILL.md (PI-647) — new default-on skill with
#     token-frugal working habits; same --no-plugin/plugin split as
#     report_upstream_issue; INDEX/AGENTS.md/justfile edits already excluded
_ADDED_SINCE_BASELINE = {
    # PI-647: token-efficiency conventions propagated to scaffolds
    ".agents/skills/token_efficiency/SKILL.md",
    # #605: Guards log the governance signal (decision + command)
    ".agents/hooks/_usage_log.sh",
    ".agents/hooks/prod_guard.py",
    # #606: the pre-edit issue guard — a new lifecycle hook, not lifecycle-move drift.
    ".agents/hooks/pre_edit_issue_guard.py",
    ".agents/skills/report_upstream_issue/SKILL.md",
    ".agents/skills/INDEX.md",
    # ... and its discoverability rows in the surface-independent skill tables.
    ".agents/project-init.md",
    ".agents/skills/README.md",
    ".gitleaks.toml",
    ".github/workflows/ci.yml",
    ".agents/scripts/setup_github.sh",
    ".agents/scripts/create_issue.sh",
    ".github/workflows/board-automation.yml",
    ".github/workflows/issue-validation.yml",
    ".agents/config.yaml",
    ".agents/hooks/session_setup.sh",
    "mypy.ini",
    "justfile",
    ".agents/hooks/post_edit_lint.sh",
    ".agents/rules/python.md",
    # node.md gained the `just sbom` (#574) / `just license` (#579) reference
    # lines — a deliberate content edit, like the other rules files here.
    ".agents/rules/node.md",
    ".agents/rules/go.md",
    ".agents/hooks/_py.sh",
    ".agents/scripts/gh_host.sh",
    ".agents/scripts/lint_memory.sh",
    ".agents/scripts/monitor_pr.sh",
    ".agents/scripts/start_issue.sh",
    ".agents/hooks/github_command_guard.sh",
    ".agents/hooks/pre_commit_gate.sh",
    ".agents/hooks/workflow_state_reminder.sh",
    ".agents/hooks/package_guard.py",
    ".agents/settings.json",
    "AGENTS.md",
    ".agents/rules/rust.md",
    ".agents/rules/typescript.md",
    "ruff.toml",
    # Shift-left commit hooks: the git pre-commit gained a `just lint` gate (so
    # human commits are held to the same static gate as CI, not only agent
    # commits), and pre-push gained a `just ci` gate. Deliberate content edits,
    # not lifecycle-move drift; their behavior is covered by test_commit_hook_gates.py.
    ".github/hooks/pre-commit",
    ".github/hooks/pre-push",
    # #629: every shipped workflow action is now pinned to a full commit SHA
    # (with a `# vX` comment for Renovate) so a fresh scaffold no longer trips
    # its own Semgrep mutable-action-tag gate. ci.yml and board-automation.yml
    # are already excluded above; project-init-upgrade.yml is the remaining
    # lifecycle workflow whose rendered bytes this deliberate edit changes.
    ".github/workflows/project-init-upgrade.yml",
}


def _manifest(target: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(target.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(target)
        if "__pycache__" in rel.parts or rel.suffix == ".pyc":
            continue
        if rel.parts and rel.parts[0] == ".claude":
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
        drop.add(".agents/settings.json")
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
