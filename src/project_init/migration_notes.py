"""Curated per-version upgrade notes surfaced by `project-init upgrade` (#244).

Deterministic and offline: the notes live in the package and are sliced by the
version span an upgrade crosses — no changelog fetch, no network (ADR-001). One
entry per version that introduced a user-visible change or needs action; a
version with no entry simply has no note. Maintained by hand at release time —
add an entry here whenever a release changes user-facing behaviour or needs a
migration step.
"""

from __future__ import annotations

from project_init.scaffold import parse_version as _parse  # canonical (2026-07 review)

# version -> {"summary": str, "action_required": str | None}
# Order here is irrelevant — notes are sliced and sorted by parsed version.
MIGRATION_NOTES: dict[str, dict[str, str | None]] = {
    "1.1.5": {
        "summary": (
            "Fixes a FALSE ALARM in the 1.1.4 branch-protection diagnostic (#822). "
            "Run without a PR number, `check_branch_protection.sh` compared the "
            "required contexts against the default branch's check-runs and reported "
            "a PR-only check (`Check PR title, branch, and linked issue`) as "
            "unsatisfiable — telling you to rewrite branch protection that was "
            "perfectly fine. A required context can legitimately be PR-only, and on "
            "the default branch a PR-only check and a real phantom look identical: "
            "absent. It now uses the PR's own check rollup — the exact set GitHub "
            "matches against — and declines to guess when there is no PR."
        ),
        "action_required": (
            "If 1.1.4's diagnostic told you a required check was unsatisfiable, "
            "re-check with a PR number before changing anything: "
            "`.agents/scripts/check_branch_protection.sh <PR>`. If it now reports "
            "all checks satisfied, your branch protection was always correct and "
            "needs no change."
        ),
    },
    "1.1.4": {
        "summary": (
            "Diagnoses the silent forever-block (#819). Branch protection is written "
            "once, at scaffold time; the workflows keep changing. A REQUIRED status "
            "check that no job reports is never satisfied, so the branch sits "
            "`BLOCKED` with every check green and no error anywhere — and EVERY pull "
            "request in the repo becomes unmergeable. Projects scaffolded before "
            "PI-555 require the per-version matrix contexts (`Lint and test (3.12)` "
            "…), and PI-761 stopped producing those on a PR, so they are stranded. "
            "The new `.agents/scripts/check_branch_protection.sh` names the "
            "unsatisfiable checks, and `monitor_pr.sh` runs it whenever a PR is "
            "BLOCKED instead of leaving the cause to be guessed."
        ),
        "action_required": (
            "If your PRs are stuck 'BLOCKED' while every check passes, run "
            "`.agents/scripts/check_branch_protection.sh` — it names the required "
            "checks nothing reports. The fix is to re-run "
            "`.agents/scripts/setup_github.sh`, which re-syncs protection to require "
            "the single `CI gate` job (it `needs:` the whole matrix and the secret "
            "scan, so it survives any future matrix change). Scaffolds created after "
            "PI-555 already require `CI gate` and need nothing."
        ),
    },
    "1.1.3": {
        "summary": (
            "Fixes a data-loss bug in the 1.1.2 `.claude/` -> `.agents/` migration "
            "(#816). That migration re-rendered the files the templates own and "
            "DELETED everything else: project-authored ADRs and the entire `memory/` "
            "tier were removed and never recreated — silently, with the upgrade "
            "reporting success. The migration now moves the whole `.claude/` tree "
            "into `.agents/` before computing drift, so your own files survive and "
            "your edits to managed files 3-way merge instead of being overwritten."
        ),
        "action_required": (
            "If you already upgraded to 1.1.2 from a pre-v1.0.1 (`.claude/`) layout, "
            "your project-authored files under `.claude/` — ADRs, the `memory/` tier — "
            "were DELETED. Recover them from the commit BEFORE the upgrade; do not "
            "restore from HEAD, which may already contain the deletion:\n"
            "  1. Find the deleting commit (search all history, not just the last "
            "one): `git log --diff-filter=D --name-only -- .claude/`\n"
            "  2. Restore from its parent: `git checkout <sha>^ -- .claude/`\n"
            "  3. Move each recovered file to the matching `.agents/` path, then "
            "delete the leftover `.claude/` copies (`.claude/` is now a generated "
            "mirror).\n"
            "If the upgrade was never committed, `git checkout -- .claude/` is enough. "
            "If the tree was NOT clean at upgrade time, uncommitted content is gone. "
            "Upgrading straight from 1.0.x to 1.1.3 is unaffected — it never loses the "
            "files in the first place."
        ),
    },
    "1.1.2": {
        "summary": (
            "Three fixes, all of which failed silently in 1.1.x. (1) Both plugins "
            "were uninstallable and loaded ZERO hooks: the marketplace manifests "
            "sat at `.agents-plugin/`, which Claude Code never reads, and each "
            "plugin.json redeclared the standard hooks file so the client rejected "
            "it as a duplicate. Plugin-first scaffolds take their hooks only from "
            "the plugin, so they ran with no commit gate, no lint-on-edit and no "
            "prod guard — while `.agents/rules/hooks.md` said the hooks were firing "
            "(#810). (2) The git `pre-commit` hook DESTROYED UNSTAGED WORK: "
            "`git apply` is not atomic, and the hook read its non-zero exit as "
            "'nothing was touched', so a single commit could delete uncommitted "
            "files and still exit 0 (#812). (3) `upgrade` refused to run on any "
            "pre-v1.0.1 scaffold, reporting it as never scaffolded (#814)."
        ),
        "action_required": (
            "Run `.agents/scripts/install_hooks.sh` after upgrading. The git hooks "
            "are COPIED into `.git/hooks/` at install time, so upgrading the "
            "template does NOT replace the copy you are running — without this "
            "step you keep the pre-commit hook that destroys unstaged work, while "
            "believing 1.1.2 fixed it. Also re-add the plugin marketplace "
            "(`claude plugin marketplace add <your project-init repo>`) if you "
            "tried before 1.1.2 and it failed: every install attempt against the "
            "old manifests errored out."
        ),
    },
    "1.0.2": {
        "summary": (
            "TypeScript projects gain a BLOCKING security lint "
            "(eslint-plugin-security + eslint-plugin-no-unsanitized, severities "
            "pinned to error), and `typescript` is pinned to ^5 because "
            "typescript-eslint cannot parse TypeScript 7 — unpinned, `just lint` "
            "crashed with exit 2 on every fresh Node scaffold (#729, #732)."
        ),
        "action_required": (
            "Node projects: run `just setup` after upgrading. Your package.json "
            "predates the new eslint plugins, and `bun install` cannot add what "
            "it never listed — without this, eslint.config.mjs fails to import "
            "and `just lint` exits 2. The scaffolded CI now seeds them "
            "automatically, but local runs need the one-time install."
        ),
    },
    "1.0.1": {
        "summary": (
            "Patch release from live E2E testing against real mini-projects. "
            "Fresh Python and Node scaffolds now pass day-one `just ci` before "
            "application sources/tests exist; the interactive wizard can finish "
            "with Enter defaults by deriving a description from the project "
            "name; generated observability and multi-agent hook adapter files "
            "satisfy the scaffolded ruff gates; and the pre-push hook resolves "
            "the scaffolded project root when run outside an initialized git "
            "repo."
        ),
        "action_required": (
            "Re-run `project-init upgrade` to pick up the day-one justfile, "
            "observability, multi-agent hook, and pre-push fixes. No breaking "
            "changes."
        ),
    },
    "1.0.0": {
        "summary": (
            "First stable release, following a full QA sweep (~180 scaffolder "
            "invocations across presets, languages, overlays, hostile input, "
            "and subcommand lifecycles — zero crashes). Fixes: `--strict` no "
            "longer rejects user text containing literal `{{...}}`; wizard "
            "menus re-prompt on a mistyped number instead of silently using "
            "the default, and invalid MCP selections re-ask; `add`/`remove` "
            "reject a positional path with a `--target` hint (including `add "
            "memory <path>`); clearer errors for empty `--name`/`--description` "
            "and a bare trailing subcommand word; failing runs print nothing "
            "on stdout. Scaffolded fixes: CI's integration and nightly-mutation "
            "jobs skip cleanly before a pyproject.toml exists; deploy.yml ship "
            "stubs name your project (new `{{project_slug}}` variable) instead "
            "of `my-service`; AGENTS.md support-tier notes now cover "
            "Cursor/Amp/Junie. Wizard explainers were rewritten for newcomers "
            "(profile panel, glossed MCP/RAG/OpenTofu/GHCR jargon, accurate "
            "default lines)."
        ),
        "action_required": (
            "Re-run `project-init upgrade` to pick up the CI-guard, deploy-stub, "
            "and AGENTS.md fixes. No breaking changes."
        ),
    },
    "0.6.1": {
        "summary": (
            "Bug-fix pass from a full code review. Scaffolder: `upgrade --apply` "
            "no longer resets a hand-set `memory.rag_endpoint`, preset control "
            "vars (governance/lifecycle/memory_stack) no longer leak into the "
            "template gates (so `remove governance` on a governed-preset project "
            'now converges, and a preset\'s `lifecycle = "none"` renders '
            "correctly), and the wizard honors `--agents`, re-prompts on a "
            "mistyped language/license instead of silently coercing to `none`, "
            "and still offers the browser concern when `--mcps` is passed. "
            "Scaffolded fixes: the GitHub command-guard closes a quoted "
            "global-option bypass (`git -c foo='a b' push`), its hook budget no "
            "longer fails open on one slow gh call, start_issue.sh reports a "
            "nonexistent issue instead of dying silently, monitor_pr.sh "
            "surfaces bot review comments instead of a false timeout message, "
            "and the commit gate no longer blocks commits in uv projects that "
            "don't ship ruff."
        ),
        "action_required": (
            "Re-run `project-init upgrade` to pick up the guard and script "
            "fixes. No breaking changes."
        ),
    },
    "0.6.0": {
        "summary": (
            "Robustness + hardening pass (2026-07 review). Re-running the "
            "scaffolder over a recorded project no longer clobbers files you "
            "edited after scaffolding — edited/unrecorded managed files are "
            "parked as `<file>.new` siblings using the recorded content hashes. "
            "The GitHub lifecycle command-guard closes bypasses (git global "
            "options, GraphQL merge mutations, interpreter heredocs). Scaffolded "
            "fixes: the rust/go/node + service justfile no longer defines `build` "
            "twice (the container recipe is now `image`), `.gitignore` stops "
            "ignoring committed `.codex/` wiring, monitor_pr.sh requires an "
            "explicit --admin to override a BLOCKED merge, and several hooks/"
            "scripts are more portable. CI SHA-pins its Actions and verifies the "
            "shfmt download against published checksums."
        ),
        "action_required": (
            "Python projects: `just ci` now includes a blocking strict-mypy "
            "`typecheck` gate (new in 0.6.0). Pre-existing untyped code can turn "
            "CI red on upgrade — either fix the reported errors, or soften "
            "mypy.ini (`strict = False`) / drop `typecheck` from the `ci:` "
            "recipe while you migrate. If you rely on `just build` in a "
            "service-delivery project, note the container build recipe is now "
            "`just image` (`just build` is the language build). Re-run "
            "`project-init upgrade` to pick up the guard/template fixes."
        ),
    },
    "0.5.0": {
        "summary": (
            "Base is now à-la-carte and self-explaining (ADR-023, epic #470): a "
            "core preset plus opt-out concerns — --memory none, --lifecycle "
            "none, --no-docs, --no-renovate. Memory gains a tiered model "
            "(ADR-024): memory/ split from vault/ as an auto tier with a "
            "staleness lint, a low-token code-map for agents, and an opt-in "
            "tier-3 code-RAG engine (--memory obsidian-graphify-rag, "
            "cocoindex-code, keyless/on-device, ADR-026). Adds --observability "
            "and --governance overlays, the "
            "agentic-OS cross-project memory descriptor contract, and "
            "orchestrator-friendly --json scaffold output."
        ),
        "action_required": (
            "No action required to keep current behaviour — the new concerns "
            "default ON (opt-out), so an upgrade scaffolds the same surface as "
            "before. Tier-3 RAG is opt-in: scaffold with "
            "--memory obsidian-graphify-rag, then run "
            "`.agents/scripts/setup_rag.sh` in the project to install the "
            "engine."
        ),
    },
    "0.4.0": {
        "summary": (
            "Delivery model (--delivery library|service|prototype) drives the "
            "env/CI/release bundle: a container parity bundle for services, "
            "opt-in deploy (--deploy) and IaC (--iac) overlays, a library "
            "release workflow, and a single-trunk default (ADR-015, epic #316)."
        ),
        "action_required": (
            "Branch-per-env was removed — if you used dev/staging branches, "
            "branch protection is now centralized: run "
            "`.agents/scripts/setup_github.sh --protect`."
        ),
    },
    "0.3.0": {
        "summary": (
            "Distribution profiles (--profile individual|standalone|org), the "
            "`project-init upgrade` drift/apply system, a host-aware plugin "
            "marketplace, and opt-in --no-egress (ADR-013)."
        ),
        "action_required": None,
    },
}


def notes_for_span(
    prev: str | None, current: str | None
) -> list[tuple[str, dict[str, str | None]]]:
    """Return ``[(version, entry)]`` for the span, newest version first.

    Selects versions ``v`` with ``prev < v <= current``. When *prev* is missing
    or unparseable (a first upgrade, or a pre-record migration), only the
    *current* version's note is returned so the user sees where they are landing
    without a flood of historical notes. An empty list means nothing to show
    (e.g. a same-version re-run, or a downgrade).
    """
    c = _parse(current)
    if c is None:
        return []
    p = _parse(prev)
    # Carry the parsed tuple ``v`` through so the sort never re-parses and never
    # needs a None fallback: an unparseable version can't reach the sort because
    # the comprehension already dropped it (Codex review).
    selected = [
        (v, version, entry)
        for version, entry in MIGRATION_NOTES.items()
        if (v := _parse(version)) is not None and v <= c and (p is None or v > p)
    ]
    if p is None:
        selected = [(v, version, entry) for v, version, entry in selected if v == c]
    selected.sort(key=lambda item: item[0], reverse=True)
    return [(version, entry) for _v, version, entry in selected]
