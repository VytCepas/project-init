"""Tool-output compressor (PI-641 WS13, prototype): shrink re-derivable Bash dumps.

PostToolUse hook on Bash (Claude Code >= 2.1.121). When a plain ``git diff`` /
``git show`` / ``git log`` / ``gh pr diff`` result exceeds
``PI_COMPRESS_MIN_CHARS`` (default 4000), the recorded result is replaced with
a diffstat-style summary, the first lines of the output, and a pointer to the
full text spilled under ``.agents/tmp/tool_output/`` — the command itself has
already run untouched (unlike a PreToolUse command rewriter). A tool result is
re-sent with the context on every later turn, so one 12k-char diff costs its
~3k tokens times every remaining turn of the session.

Scope is deliberately surgical (prototype): only single git-diff-class
commands whose full output stays re-derivable on demand (Read the spill file,
or re-run with ``--stat`` / a path filter). Piped or compound commands are
exempt — a pipe usually means the agent already filtered. Disable with
``PI_COMPRESS_TOOL_OUTPUT=0``.

Fail-open by design: any internal error exits 0 with no output, and Claude
Code itself ignores an ``updatedToolOutput`` whose shape doesn't match the
tool's schema, so the original result stands on both failure paths.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

DEFAULT_MIN_CHARS = 4000
HEAD_LINES = 20

# Commands whose large output is noise we can summarize losslessly-enough:
# unified diffs and log dumps, all re-derivable from the repo at any time.
_TARGET = re.compile(r"^(?:git\s+(?:diff|show|log)|gh\s+pr\s+diff)\b")


def _target_command(command: str) -> bool:
    """True when *command* is a single, unfiltered git-diff-class invocation."""
    cmd = command.strip()
    # Tolerate one leading `cd <path> &&` — a common agent idiom.
    m = re.match(r"^cd\s+[^;|&]+?&&\s*(.*)$", cmd, re.DOTALL)
    if m:
        cmd = m.group(1).strip()
    # Pipes mean the agent already filtered; compounds mix outputs we can't
    # attribute — leave both alone.
    if any(sep in cmd for sep in ("|", "&&", ";", "\n")):
        return False
    return bool(_TARGET.match(cmd))


def _diffstat(text: str) -> list[str]:
    """Per-file +/- counts parsed from a unified diff (empty for non-diffs)."""
    stats: list[str] = []
    name = None
    added = removed = 0
    for line in text.splitlines():
        if line.startswith("diff --git "):
            if name is not None:
                stats.append(f"  {name}  +{added} -{removed}")
            # "diff --git a/path b/path" — the b/ side names the result.
            parts = line.split(" b/", 1)
            name = parts[1] if len(parts) == 2 else line[len("diff --git ") :]
            added = removed = 0
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    if name is not None:
        stats.append(f"  {name}  +{added} -{removed}")
    return stats


def _spill(root: str, tool_use_id: str, text: str) -> str:
    rel = os.path.join(".agents", "tmp", "tool_output")
    out_dir = os.path.join(root, rel)
    os.makedirs(out_dir, exist_ok=True)
    stamp = tool_use_id or str(int(time.time() * 1000))
    # Keep the name filesystem-safe regardless of the id's alphabet.
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", stamp)[:80]
    path = os.path.join(out_dir, f"bash-{safe}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return os.path.join(rel, f"bash-{safe}.txt")


def main() -> int:
    if os.environ.get("PI_COMPRESS_TOOL_OUTPUT", "1") == "0":
        return 0
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    response = payload.get("tool_response")
    if not isinstance(response, dict):
        return 0
    stdout = response.get("stdout")
    if not isinstance(stdout, str):
        return 0
    try:
        min_chars = int(os.environ.get("PI_COMPRESS_MIN_CHARS", DEFAULT_MIN_CHARS))
    except ValueError:
        min_chars = DEFAULT_MIN_CHARS
    if len(stdout) <= min_chars or not _target_command(command):
        return 0

    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    spill_path = _spill(root, str(payload.get("tool_use_id") or ""), stdout)

    lines = stdout.splitlines()
    stats = _diffstat(stdout)
    summary_parts = [
        f"[tool_output_compressor] {len(stdout):,}-char result compressed to save"
        f" per-turn context (PI-641). Full output: {spill_path} — Read specific"
        " line ranges there, or re-run with --stat / a path filter.",
    ]
    if stats:
        summary_parts.append(f"diffstat ({len(stats)} file(s)):")
        summary_parts.extend(stats)
    summary_parts.append(f"--- first {min(HEAD_LINES, len(lines))} of {len(lines)} lines ---")
    summary_parts.extend(lines[:HEAD_LINES])

    updated = dict(response)
    updated["stdout"] = "\n".join(summary_parts)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "updatedToolOutput": updated,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 — fail-open: never break the tool result
        sys.exit(0)
