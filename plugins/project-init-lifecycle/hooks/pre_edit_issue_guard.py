"""Pre-edit issue guard (#606): keep work off the default branch.

Lifecycle PreToolUse hook on Edit|Write|MultiEdit. When an agent tries to edit
a file while its repository is on the default branch (``main``/``master``), the
edit is flagged — ``ask`` in interactive sessions, ``deny`` in fully autonomous
ones — steering the agent to create an issue and a branch first. This is the
earliest point to enforce "one issue -> one branch -> one PR": the ``pre-push``
hook and ``validate-pr.yml`` catch a missing linked issue only later, and never
stop an agent from doing the whole change on the default branch and back-filling
a compliant issue/branch/PR afterward.

Deliberately narrow: only the default branch is guarded. project-init supports
no-issue work (``create-pr-nojira``, scopeless commits), so feature branches —
issue-linked or not — are never blocked.

Fail-open by design: any internal error (not a git repo, git missing, an odd
payload) lets the edit proceed. A guardrail, not a boundary.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_DEFAULT_BRANCHES = {"main", "master"}

# Fully autonomous mode: no human is watching the prompt, so "ask" is
# meaningless — block outright. Other modes surface an interactive prompt.
_AUTONOMOUS_MODES = {"bypassPermissions", "dangerouslySkipPermissions"}


def _target_dir(file_path: Path, cwd: Path) -> Path:
    """Return an existing directory to run git in for the edited file.

    The file itself may not exist yet (a fresh ``Write``), so resolve a
    relative path against the tool's cwd and walk up to the nearest existing
    ancestor directory.
    """
    resolved = file_path if file_path.is_absolute() else cwd / file_path
    directory = resolved.parent
    while not directory.is_dir() and directory != directory.parent:
        directory = directory.parent
    return directory


def _current_branch(directory: Path) -> str | None:
    """Return the git branch checked out in ``directory``, or None.

    None when ``directory`` is not inside a work tree, HEAD is detached, or git
    is unavailable — all of which mean "not on a named default branch", so the
    edit is allowed.
    """
    try:
        result = subprocess.run(  # noqa: S603 — fixed git argv, never a shell string
            ["git", "-C", str(directory), "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607 — bare "git" resolves via PATH like every other hook
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def evaluate(file_path: Path, cwd: Path, permission_mode: str) -> dict | None:
    """Return the hook verdict for editing ``file_path``, or None to allow."""
    branch = _current_branch(_target_dir(file_path, cwd))
    if branch is None or branch not in _DEFAULT_BRANCHES:
        return None
    decision = "deny" if permission_mode in _AUTONOMOUS_MODES else "ask"
    reason = (
        f"pre_edit_issue_guard: editing on the default branch ('{branch}'). "
        "Create an issue and a branch first, then edit — every change stays "
        "traceable as one issue -> one branch -> one PR. Run: "
        '.agents/scripts/create_issue.sh <type> "<title>" (prints the issue '
        "number N), then .agents/scripts/start_issue.sh N <type> (branch + "
        "draft PR in one step); or use the start_task skill. "
        "(Guardrail only; pre-push and validate-pr also enforce this later.)"
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }


def main() -> int:
    """Read the PreToolUse payload from stdin; print a verdict if any."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0  # non-dict JSON (e.g. a list) → fail open
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0  # missing / non-dict tool_input → fail open
    raw_path = tool_input.get("file_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return 0
    cwd = Path(payload.get("cwd") or ".")
    try:
        verdict = evaluate(Path(raw_path), cwd, payload.get("permission_mode") or "")
    except Exception:  # noqa: BLE001 — guardrail must never break the session
        return 0
    if verdict is not None:
        sys.stdout.write(json.dumps(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
