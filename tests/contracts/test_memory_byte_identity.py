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
`.agents/scripts/gen_code_map.py` and edits AGENTS.md (the read-the-map pointer)
and the justfile (the `code-map` recipe). Only those keys were re-pinned, after
verifying every OTHER file still matched the baseline — the move invariant is
intact for everything else.

Exception (#498): the memory descriptor intentionally edits `.agents/config.yaml`
(adds `tier` + `graph_path` to the `memory:` block, and later a top-level
`project_init_contract_version` to the `project:` block, ADR-025). Only that key
was re-pinned, after verifying every other file still matched.

Exception (LightRAG cleanup): removing the dead `.agents/memory/.lightrag/`
gitignore line (ADR-024) re-pinned `.gitignore` only.

Exception (PI-526): the concern-decoupled skills `save_memory`, `status`, and
`session_summary` gained deterministic presence-checks in their bodies (don't
write to `.agents/memory/` or `.agents/vault/` when that concern was declined) —
a deliberate fix, not move-drift. Only those three SKILL.md hashes were re-pinned
(no_plugin combos), after verifying every other file still matched.

Exception (PI-550): `dag_workflow.py` gained `_strip_text_flag_values` so the
command-guard no longer false-positives on blocked-command phrases inside
free-text flag values. A deliberate guard fix, not move-drift. Only the
`.agents/hooks/dag_workflow.py` hash was re-pinned across all four combos, after
verifying every other file still matched.

Exception (PI-570): `ruff.toml` gained the RUF/PERF/PTH/RET/ARG/A/S/BLE rule
groups (per-language quality-gate strictness pass) — a deliberate content
change, not move-drift. `.agents/hooks/package_guard.py` also picked up
`# noqa: S310` placement fixes for the new `S` rule group; it was already
excluded above. Only `ruff.toml` is newly excluded here, after verifying
every other file still matched.

Exception (2026-07 review): deliberate content fixes re-pinned after verifying
no other file drifted — `dag_workflow.py` (command-guard bypass fixes),
`.gitignore` (no longer ignoring the committed `.codex/` wiring), `prod_guard.py`
(rm split-flag detection), `commit-msg` (install comment), and the fallback
hooks `pre_commit_gate.sh` / `post_edit_lint.sh` (cd to repo root).

Exception (2026-07 review, second pass): `dag_workflow.py` closed the
quoted-global-option guard bypass, capped its per-subprocess timeout below the
hook budget, and made the nojira "PR already exists" short-circuit check the PR
is OPEN. Only the `.agents/hooks/dag_workflow.py` hash was re-pinned across all
four combos, after verifying every other file still matched.

Exception (PI-643): the git-config / editor-hiding parity sweep enriched two base
files — `.gitignore` (python tool caches: `.mypy_cache/`, `.coverage`, etc.;
mkdocs `site/` + typedoc `_site/` docs build output; `*.swo` / `*.log`) and
`.gitattributes` (`* text=auto`, `linguist-generated` for the `.claude/` mirror
and lockfiles, `linguist-vendored` for the vault). Deliberate content additions,
not move-drift. Only those two hashes were re-pinned across all four combos,
after verifying every other file still matched.

Exception (#668): the scaffolded `.gitignore` gained the `.claude/` runtime
entries (`scheduled_tasks.lock`, `settings.local.json`) — Claude Code writes
session state into the generated `.claude/` mirror it reads, and only the
`.agents/` copies were ignored. Deliberate content addition, not move-drift —
only the `.gitignore` hash was re-pinned across all four combos, after
verifying every other file still matched.

Exception (#710): `push_wiki.sh` upstreamed the repo copy's improvements —
`--prune <page.md> ...` (remove stale pages in the same commit), the
bash-3.2-safe empty-array guard, and the bot-identity commit fallback for
runners with no git identity — while keeping the template's host-aware
`gh_web_base` clone URL. Deliberate feature reconciliation (semi-scaffold
DIVERGED → SYNCED), not move-drift — only the `.agents/scripts/push_wiki.sh`
hash was re-pinned across all four combos, after verifying every other file
still matched.

Exception (#678): `monitor_pr.sh` gained `_cleanup_local_branch` — a squash
merge deletes the remote branch but the local one lingered after every merged
PR; after a confirmed merge the script now deletes the local head branch when
(and only when) its SHA equals the PR's headRefOid. Deliberate feature, not
move-drift — only the `.agents/scripts/monitor_pr.sh` hash was re-pinned
across all four combos, after verifying every other file still matched.

Exception (#632): `monitor_pr.sh` gained `_merge_with_retry`/`_pr_is_merged` —
the single-shot merge raced GitHub's mergeability computation (failing while
every check was green) and a failed attempt whose merge actually landed
server-side was reported as an error. Deliberate bug fix, not move-drift —
only the `.agents/scripts/monitor_pr.sh` hash was re-pinned across all four
combos, after verifying every other file still matched.

Exception (#633): `start_issue.sh`'s seed-commit decision now compares HEAD
against the REMOTE base (`_seed_base`) — GitHub judges "No commits between"
against its own base ref, so a branch cut from origin/main with a lagging
local main skipped the seed and PR creation failed. PR creation also seeds +
retries once on that rejection. Deliberate bug fix, not move-drift — only the
`.agents/scripts/start_issue.sh` hash was re-pinned across all four combos,
after verifying every other file still matched.

Exception (#631): `start_issue.sh` gained `_repo_root_name` — project-key
derivation now anchors on the MAIN worktree's directory (via git-common-dir)
instead of `--show-toplevel`, so linked worktrees derive the same key as the
main checkout. Deliberate bug fix, not move-drift — only the
`.agents/scripts/start_issue.sh` hash was re-pinned across all four combos,
after verifying every other file still matched.
Exception (PI-715): `review-status.yml` no longer maps straight off
`reviewDecision`. It only ever went green on APPROVED, which a solo repo can
never produce (GitHub refuses self-approval; Copilot/Codex submit COMMENTED), so
the required check was permanently pending and every merge became an `--admin`
override. It now reports `success` once a review has landed with no unresolved
threads, `failure` on changes-requested or open comments, `pending` before any
review. Deliberate content change, not move-drift — only the
`.github/workflows/review-status.yml` hash was re-pinned across all four combos,
after verifying every other file still matched.
The same PI-715 change reworded the `github_workflow` SKILL.md (`--no-review` is no longer the routine merge path); its hash was re-pinned in the no_plugin combos only, where the skill ships as a file rather than through the plugin.

Exception (PI-687): `agents/explore.md` gained a four-step orientation contract —
read CODE_MAP/MEMORY/CAPABILITIES first to pick targets, verify every specific
against the source, treat a missing cited path as staleness, and report it. The
discovery subagent previously named no orientation artifact, so AGENTS.md's
"read CODE_MAP first, delegate sweeps to explore" threw the map away at the
delegation boundary. Deliberate content change, not move-drift — only the
`.agents/agents/explore.md` hash was re-pinned across all four combos, after
verifying every other file still matched.

Exception (PI-726): `dag_workflow.py` was reformatted by `ruff format`. `just
lint` now carries `ruff format --check .`, and the shipped hook was not
format-clean — so every fresh python scaffold would have failed its own lint gate
on day one (the #698 class of bug). Deliberate formatting change, not move-drift
— only the `.agents/hooks/dag_workflow.py` hash was re-pinned across all four
combos, after verifying every other file still matched.

Exception (PI-745): the TDD-guidance alignment reworded two always-rendered docs
— `.agents/docs/development/testing.md` and `.github/copilot-instructions.md`
(test-first scoped to design, plus the prove-a-guard-can-fail rule). Deliberate
content change, not move-drift — only those two keys were re-pinned across all
four combos, after asserting no OTHER key drifted.

Exception (PI-920): `review-status.yml` errored on every review event in a
PRIVATE scaffolded repo — `gh pr view --json reviews` pulls
reviews.nodes[].commit, which needs contents:read, and the workflow's explicit
permissions: block sets unlisted scopes to none. Public repos resolved it
anyway, so the defect was invisible in this repo's own CI. Only that one
hash was re-pinned, after confirming it was the sole key that drifted in all
eight fixtures.
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
_GENERATED = {".agents/CAPABILITIES.md"}

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
#   • issue-validation.yml — self-populating board metadata: auto-ensures the
#     type label from the body "- Type:" for MCP/API-created issues, and derives
#     area:<slug> label(s) from the body Area field (PI-777); issue-metadata.md
#     documents that derivation
#   • report_upstream_issue skill (SKILL.md + INDEX/README/project-init.md rows)
#     — new default-on skill routing tooling bugs upstream to project-init
#   • token_efficiency skill (PI-647) — new default-on skill with token-frugal
#     working habits; INDEX/AGENTS.md/justfile rows already excluded above
_ADDED_SINCE_BASELINE = {
    # PI-933: renovate.json gained a customManagers entry so a tool version
    # pinned inside a workflow run step is maintained rather than frozen.
    # (This set covers content drift as well as new paths — see
    # dag_workflow.py above, which is here for a content change.)
    "renovate.json",
    # PI-932: a fresh --language python scaffold shipped no pyproject.toml, so
    # `just lint` died with "Failed to spawn: ruff" before a line of project
    # code existed. The template is python-gated, so this path appears on a
    # Python scaffold only.
    "pyproject.toml",
    # PI-848: local agent specs removed — explore duplicates the built-in
    # Explore agent; code-reviewer ships only on --no-egress scaffolds.
    ".agents/agents/explore.md",
    ".agents/agents/code-reviewer.md",
    ".agents/agents/README.md",
    # PI-845: the command guard gained the upstream issue-create exception.
    ".agents/hooks/dag_workflow.py",
    # PI-846/PI-850: graphify installer tightening — new guard hook +
    # post-install fixer; the rule + setup script gained content.
    ".agents/hooks/graphify_guard.sh",
    ".agents/hooks/graphify_post_install.py",
    ".agents/rules/graphify.md",
    ".agents/scripts/setup_graphify.sh",
    # PI-819: diagnoses a REQUIRED status check that no job reports — the state
    # that leaves every PR permanently BLOCKED with all checks green.
    ".agents/scripts/check_branch_protection.sh",
    # PI-647: token-efficiency conventions propagated to scaffolds
    ".agents/skills/token_efficiency/SKILL.md",
    # PI-694: token-budget lint gate — new always-copied script (justfile
    # wiring already excluded above)
    ".agents/scripts/lint_context_budget.sh",
    # Board-visibility fix: one-time backfill that reconciles the Projects board
    # with closed-issue state (new lifecycle script; board-automation.yml already
    # excluded above).
    ".agents/scripts/backfill_board_done.sh",
    # PI-696: PostToolUse tool-output compressor (settings.json/AGENTS.md
    # wiring already excluded above)
    ".agents/hooks/tool_output_compressor.py",
    # PI-657: guard/per-surface mechanics moved out of always-loaded AGENTS.md
    ".agents/docs/guides/enforcement.md",
    # PI-666: self-hosted-runner escape-hatch guide (ci.yml + justfile edits
    # already excluded above)
    ".agents/docs/guides/self-hosted-ci-runner.md",
    # PI-661: zero-token statusline context meter (wired in settings.json,
    # which is already excluded above)
    ".agents/hooks/statusline.sh",
    # PI-663: checkpoint skill (checkpoint-and-clear session handoff);
    # INDEX/README/project-init.md rows already excluded above. The .gitignore
    # edit (.agents/tmp/) was re-pinned in the fixtures, not excluded.
    ".agents/skills/checkpoint/SKILL.md",
    # PI-665: diagram skill (collaborative Mermaid-first diagramming);
    # INDEX/README/project-init.md rows already excluded above
    ".agents/skills/diagram/SKILL.md",
    # PI-747: verify-test-strength skill (mutation-feedback loop)
    ".agents/skills/verify-test-strength/SKILL.md",
    # PI-671: local_ci skill (Actions billing-lockout escape hatch)
    ".agents/skills/local_ci/SKILL.md",
    # #605: Guards log the governance signal (decision + command)
    ".agents/hooks/_usage_log.sh",
    ".agents/hooks/prod_guard.py",
    # #606: the pre-edit issue guard — a new lifecycle hook, not lifecycle-move drift.
    ".agents/hooks/pre_edit_issue_guard.py",
    ".gitleaks.toml",
    ".github/workflows/ci.yml",
    ".agents/scripts/setup_github.sh",
    ".agents/scripts/create_issue.sh",
    ".github/workflows/board-automation.yml",
    ".github/workflows/issue-validation.yml",
    ".agents/docs/guides/issue-metadata.md",
    # #629: workflow actions pinned to commit SHAs so a fresh scaffold no longer
    # trips its own Semgrep mutable-action-tag gate. ci.yml/board-automation.yml
    # already excluded above; project-init-upgrade.yml is the remaining drift.
    ".github/workflows/project-init-upgrade.yml",
    ".agents/skills/report_upstream_issue/SKILL.md",
    ".agents/skills/INDEX.md",
    ".agents/skills/README.md",
    ".agents/project-init.md",
    ".agents/config.yaml",
    # PI-888: the commit-conventions doc gained a {{#if coauthor}} block naming
    # the Co-Authored-By: Claude trailer (default ON). A deliberate content edit,
    # not memory-move drift — project-init.md (same trailer note) is already
    # excluded above.
    ".agents/docs/development/conventions.md",
    "mypy.ini",
    "justfile",
    ".agents/hooks/post_edit_lint.sh",
    ".agents/rules/python.md",
    ".agents/rules/go.md",
    # node.md gained the `just sbom` (#574) / `just license` (#579) reference
    # lines — a deliberate content edit, like the other rules files here.
    ".agents/rules/node.md",
    ".agents/hooks/session_setup.sh",
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
    # Shift-left commit hooks (see test_commit_hook_gates.py): git pre-commit
    # gained a `just lint` gate; pre-push gained a `just ci` gate.
    ".github/hooks/pre-commit",
    ".github/hooks/pre-push",
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
        if rel.parts and rel.parts[0] == ".claude":
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
        drop.add(".agents/settings.json")
    got = {k: v for k, v in got.items() if k not in drop}

    mode = "no_plugin" if no_plugin else "plugin"
    expected = json.loads((FIXTURES / f"{preset_name}__{mode}.json").read_text())
    expected = {k: v for k, v in expected.items() if k not in drop}

    added = sorted(set(got) - set(expected))
    removed = sorted(set(expected) - set(got))
    assert not added and not removed, f"path drift — added={added} removed={removed}"
    mismatched = sorted(p for p in expected if got[p] != expected[p])
    assert not mismatched, f"content drift in: {mismatched}"
