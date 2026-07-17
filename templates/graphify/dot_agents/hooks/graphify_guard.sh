#!/usr/bin/env bash
# graphify_guard.sh <search|read> — scoped replacement for the PreToolUse
# hooks `graphify install --project` writes (PI-846).
#
# The installer's own matchers fire on EVERY Bash command containing a search
# word and every Read/Glob touching ~30 extensions (including .md/.txt), ~50
# injected tokens per call — noise on config audits and non-source work.
# setup_graphify.sh swaps the installer's hook commands for this script, which
# nudges only when all of these hold:
#   * graphify-out/graph.json exists (the graph is built),
#   * the tool call actually targets SOURCE CODE — code extensions only, and
#     never paths under .agents/, .claude/, docs/, graphify-out/, vendored or
#     lock/config files,
#   * the nudge has not already fired this session (stamp keyed on the hook
#     payload's session_id — advisory once per session, not per call).
#
# Fail-open by design: any parse problem exits 0 silently.

set -euo pipefail

MODE="${1:-read}"

[ -f graphify-out/graph.json ] || exit 0

INPUT=$(cat)

# Resolve the interpreter through the canonical helper (PI-361).
PYRES="$(dirname "$0")/_py.sh"

GRAPHIFY_HOOK_INPUT="$INPUT" "$PYRES" - "$MODE" <<'PY'
import json
import os
import sys
import tempfile

mode = sys.argv[1]
try:
    payload = json.loads(os.environ.get("GRAPHIFY_HOOK_INPUT") or "{}")
except Exception:
    sys.exit(0)

tool_input = payload.get("tool_input") or {}

# Once per session: the payload carries session_id; no id → treat as unstamped.
session = str(payload.get("session_id") or "")
stamp = os.path.join(
    tempfile.gettempdir(), f"graphify-guard-{session or os.getppid()}"
)
if os.path.exists(stamp):
    sys.exit(0)

CODE_EXTS = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".kt", ".swift", ".php",
    ".scala", ".lua",
)
EXCLUDED_PARTS = (
    ".agents/", ".claude/", "docs/", "graphify-out/", "node_modules/",
    ".venv/", "vendor/",
)

def is_source_target(text: str) -> bool:
    text = text.lower().replace("\\", "/")
    if any(part in text for part in EXCLUDED_PARTS):
        return False
    return any(ext in text for ext in CODE_EXTS)

if mode == "search":
    command = str(tool_input.get("command") or "")
    search_words = ("grep", "rg ", "ripgrep", "find ", "fd ", "ack ", "ag ")
    if not any(w in command for w in search_words):
        sys.exit(0)
    # A search naming no path at all is a broad sweep over the repo — nudge;
    # one naming an excluded/non-source target is not our business.
    if any(part in command.lower() for part in EXCLUDED_PARTS):
        sys.exit(0)
else:
    target = " ".join(
        str(tool_input.get(k) or "") for k in ("file_path", "pattern", "path")
    )
    if not is_source_target(target):
        sys.exit(0)

try:
    open(stamp, "w").close()
except Exception:
    pass

context = (
    "graphify-out/graph.json exists — for codebase orientation, prefer "
    "`graphify query \"<question>\"` (scoped subgraph), `graphify path`, or "
    "`graphify explain` before sweeping raw files; grep/read directly when "
    "modifying or debugging specific lines. Workflow: .agents/rules/graphify.md "
    "(advisory, shown once per session)."
)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": context,
    }
}))
PY

exit 0
