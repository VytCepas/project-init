#!/usr/bin/env python3
"""Tighten what `graphify install --project` wrote (PI-846 / PI-850).

Run by setup_graphify.sh right after the installer. Two fixups, both
fail-open (a shape the tool no longer produces is reported, never fatal):

1. PI-846 — the installer wires PreToolUse hooks on `Bash` and `Read|Glob`
   whose own matching is substring-broad (every command containing "grep",
   every read of ~30 extensions incl. .md/.txt) and fires per call. Replace
   those hook commands with `.agents/hooks/graphify_guard.sh`, which scopes
   to genuine source-code activity and nudges once per session.

2. PI-850 — the installer appends a full `## graphify` workflow section to
   the root CLAUDE.md; the same guidance auto-loads from
   `.agents/rules/graphify.md` (its single home). Trim the CLAUDE.md section
   to a one-line pointer. The `.claude/CLAUDE.md` /graphify skill-routing
   stub is functional wiring, not workflow duplication — left alone.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

GUARD = '"$CLAUDE_PROJECT_DIR"/.agents/hooks/graphify_guard.sh'

POINTER = (
    "## graphify\n\n"
    "Knowledge-graph workflow (query before grep, `graphify update .` after\n"
    "changes, never hand-edit `graphify-out/`): see `.agents/rules/graphify.md`.\n"
)


def tighten_settings(settings_path: Path) -> str:
    if not settings_path.exists():
        return "settings.json not found — skipped"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "settings.json unparsable — left untouched"
    replaced = 0
    for entry in settings.get("hooks", {}).get("PreToolUse", []):
        matcher = entry.get("matcher", "")
        for hook in entry.get("hooks", []):
            command = hook.get("command", "")
            # The installer's hooks are the ones that mention the graph file
            # inline; ours reference the guard script instead.
            if "graphify-out/graph.json" in command and "graphify_guard" not in command:
                mode = "search" if matcher == "Bash" else "read"
                hook["command"] = f"bash {GUARD} {mode}"
                replaced += 1
    if replaced:
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        return f"scoped {replaced} graphify hook(s) to source-code activity"
    return "no installer-shaped graphify hooks found — nothing to tighten"


def trim_claude_md(claude_md: Path) -> str:
    if not claude_md.exists():
        return "CLAUDE.md not found — skipped"
    text = claude_md.read_text(encoding="utf-8")
    if "## graphify" not in text:
        return "no ## graphify section — nothing to trim"
    if ".agents/rules/graphify.md" in text:
        return "CLAUDE.md already points at the rule — nothing to trim"
    # The section runs to the next H2 or EOF.
    new_text, n = re.subn(r"## graphify\n.*?(?=\n## |\Z)", POINTER, text, count=1, flags=re.S)
    if n:
        claude_md.write_text(new_text, encoding="utf-8")
        return "trimmed CLAUDE.md ## graphify to a pointer at the rule"
    return "## graphify section shape unrecognized — left untouched"


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    print(f"  {tighten_settings(root / '.claude' / 'settings.json')}")
    print(f"  {trim_claude_md(root / 'CLAUDE.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
