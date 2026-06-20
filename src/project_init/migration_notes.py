"""Curated per-version upgrade notes surfaced by `project-init upgrade` (#244).

Deterministic and offline: the notes live in the package and are sliced by the
version span an upgrade crosses — no changelog fetch, no network (ADR-001). One
entry per version that introduced a user-visible change or needs action; a
version with no entry simply has no note. Maintained by hand at release time —
add an entry here whenever a release changes user-facing behaviour or needs a
migration step.
"""

from __future__ import annotations

import re

# version -> {"summary": str, "action_required": str | None}
# Order here is irrelevant — notes are sliced and sorted by parsed version.
MIGRATION_NOTES: dict[str, dict[str, str | None]] = {
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


def _parse(value: str | None) -> tuple[int, int, int] | None:
    """Parse a leading ``X.Y.Z`` (optional ``v`` prefix) into a tuple, or None."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", value or "")
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


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
