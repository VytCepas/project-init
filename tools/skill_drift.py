#!/usr/bin/env python3
"""Advisory drift check: personal ~/.claude/skills copies vs their template source.

PI-681. `tools/sync_plugin.py` already guards templates -> plugin -> per-surface
copies, and the semi-scaffold (PI-685) guards templates -> this repo's own
.agents/. The one edge nothing can CI-test is templates vs the maintainer's
personal `~/.claude/skills/<name>/` copies, which live outside version control.

This script makes that drift visible with one command (`just skill-drift`). It is
DELIBERATELY advisory — the personal directory is not in the repo, so this is a
heads-up, not a gate: it always exits 0. When a shared skill's personal copy has
drifted from `templates/fallback/...`, port the change into the template source
(then `uv run python tools/sync_plugin.py` + `just sync-claude`), or refresh the
personal copy from the template — whichever direction is correct for the edit.

Stdlib only; no deps (repo convention).
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PERSONAL_SKILLS = Path.home() / ".claude" / "skills"

# Skills that ship in templates/ AND are maintained as a personal ~/.claude copy.
# name -> template source (the SOURCE of record, per ADR-010). Extend as more
# personal skills get templated.
SHARED_SKILLS: dict[str, str] = {
    "diagram": "templates/fallback/dot_agents/skills/diagram/SKILL.md",
}


def main() -> int:
    """Report drift for every shared skill; always exit 0 (advisory)."""
    drifted: list[str] = []
    for name, rel in sorted(SHARED_SKILLS.items()):
        template = _REPO_ROOT / rel
        personal = _PERSONAL_SKILLS / name / "SKILL.md"
        if not template.exists():
            print(f"?  {name}: template source missing ({rel}) — check SHARED_SKILLS")
            continue
        if not personal.exists():
            print(f"–  {name}: no personal copy at {personal} — skipping")
            continue
        t = template.read_text(encoding="utf-8")
        p = personal.read_text(encoding="utf-8")
        if t == p:
            print(f"✓  {name}: personal copy in sync with {rel}")
            continue
        drifted.append(name)
        print(f"✗  {name}: DRIFT — personal copy differs from {rel}")
        diff = difflib.unified_diff(
            p.splitlines(keepends=True),
            t.splitlines(keepends=True),
            fromfile=f"~/.claude/skills/{name}/SKILL.md (personal)",
            tofile=f"{rel} (template — source of record)",
        )
        sys.stdout.writelines(diff)
        if not t.endswith("\n") or not p.endswith("\n"):
            print()

    if drifted:
        print(
            f"\n{len(drifted)} skill(s) drifted: {', '.join(drifted)}. "
            "Port the edit to the template source (then sync_plugin.py + "
            "sync-claude), or refresh the personal copy — see this script's "
            "docstring. Advisory only; not a gate."
        )
    else:
        print("\nAll shared skills in sync (or no personal copy present).")
    return 0  # advisory: never fail the caller


if __name__ == "__main__":
    raise SystemExit(main())
