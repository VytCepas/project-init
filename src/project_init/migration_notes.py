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
            "No action required for normal use. If you rely on `just build` in a "
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
            "`.claude/scripts/setup_rag.sh` in the project to install the "
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
            "`.claude/scripts/setup_github.sh --protect`."
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


def notes_for_span(prev: str | None, current: str | None) -> list[tuple[str, dict]]:
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
    selected = [
        (version, entry)
        for version, entry in MIGRATION_NOTES.items()
        if (v := _parse(version)) is not None and v <= c and (p is None or v > p)
    ]
    if p is None:
        selected = [(version, entry) for version, entry in selected if _parse(version) == c]
    selected.sort(key=lambda item: _parse(item[0]), reverse=True)
    return selected
