#!/usr/bin/env python3
"""DAG-based workflow enforcement for the GitHub lifecycle.

Subcommands:
  check <node>   exit 0 if every prerequisite of <node> is satisfied,
                 exit 2 otherwise (with a human-readable reason on stdout).
  guard          read PreToolUse hook input JSON from stdin, map the Bash
                 command to a target node, emit {decision: block, reason: ...}
                 if the command should not proceed.

Stateless code. Reads live state from `gh` / `git`. An optional cache at
.claude/.workflow-state.json may be written by lifecycle scripts to speed
checks; the cache is advisory and is always re-validated.

stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CACHE_PATH = Path(".claude/.workflow-state.json")

GRAPH: dict[str, list[str]] = {
    "issue.created": [],
    "branch.created": [],
    "branch.pushed": ["branch.created"],
    "pr.opened": ["branch.pushed", "issue.created"],
    "ci.green": ["pr.opened"],
    "review.approved": ["pr.opened"],
    "pr.merged": ["ci.green", "review.approved"],
}

ISSUE_RE = re.compile(r"PI-(\d+)", re.IGNORECASE)


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 1, ""
    return proc.returncode, proc.stdout


def _gh(args: list[str]) -> tuple[int, str]:
    return _run(["gh", *args])


def _git(args: list[str]) -> tuple[int, str]:
    return _run(["git", *args])


def _current_branch() -> str | None:
    code, out = _git(["branch", "--show-current"])
    branch = out.strip()
    return branch if code == 0 and branch else None


def _issue_from_branch(branch: str) -> int | None:
    m = ISSUE_RE.search(branch)
    return int(m.group(1)) if m else None


def check_issue_created() -> tuple[bool, str]:
    branch = _current_branch()
    if not branch:
        return False, "no current branch"
    n = _issue_from_branch(branch)
    if n is None:
        return True, f"branch '{branch}' has no PI-N ref (no-jira flow allowed)"
    code, out = _gh(["issue", "view", str(n), "--json", "number,state"])
    if code != 0:
        return False, f"issue #{n} not found via gh"
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return False, f"issue #{n}: malformed gh output"
    if data.get("number") != n:
        return False, f"issue #{n} not present"
    return True, f"issue #{n} exists ({data.get('state', 'UNKNOWN')})"


def check_branch_created() -> tuple[bool, str]:
    branch = _current_branch()
    if not branch:
        return False, "not in a git repo / no current branch"
    if branch in {"main", "master"}:
        return False, "must be on a feature branch, not main/master"
    return True, f"on branch '{branch}'"


def check_branch_pushed() -> tuple[bool, str]:
    branch = _current_branch()
    if not branch:
        return False, "no current branch"
    code, _ = _git(["rev-parse", "--verify", f"origin/{branch}"])
    if code != 0:
        return False, f"origin/{branch} does not exist (push the branch first)"
    code, out = _git(["rev-list", "--count", f"origin/{branch}..HEAD"])
    if code == 0 and out.strip() and out.strip() != "0":
        return False, f"branch has {out.strip()} unpushed commit(s)"
    return True, f"branch '{branch}' is pushed and up to date with origin"


def check_pr_opened() -> tuple[bool, str]:
    code, out = _gh(["pr", "view", "--json", "number,state"])
    if code != 0:
        return False, "no PR exists for the current branch"
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return False, "malformed gh pr view output"
    if data.get("state") != "OPEN":
        return False, f"PR is {data.get('state', 'unknown')}, not OPEN"
    return True, f"PR #{data.get('number')} is open"


def check_ci_green() -> tuple[bool, str]:
    code, out = _gh(["pr", "view", "--json", "number,statusCheckRollup"])
    if code != 0:
        return False, "cannot read PR / CI status"
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return False, "malformed gh statusCheckRollup output"
    n = data.get("number", "?")
    rollup = data.get("statusCheckRollup") or []
    pending = failing = 0
    for entry in rollup:
        name = (entry.get("name") or entry.get("context") or "").lower()
        if "review/decision" in name:
            continue
        status = (entry.get("status") or "").upper()
        conclusion = (entry.get("conclusion") or "").upper()
        if conclusion in {"FAILURE", "TIMED_OUT", "CANCELLED", "ERROR", "ACTION_REQUIRED"}:
            failing += 1
        elif status in {"PENDING", "QUEUED", "IN_PROGRESS", "WAITING"} or (
            not conclusion and not status
        ):
            pending += 1
    if failing:
        return False, f"PR #{n}: {failing} CI check(s) failing"
    if pending:
        return False, f"PR #{n}: {pending} CI check(s) still running"
    return True, f"PR #{n}: CI green"


def check_review_approved() -> tuple[bool, str]:
    code, out = _gh(["pr", "view", "--json", "number,reviewDecision"])
    if code != 0:
        return False, "cannot read PR review decision"
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return False, "malformed gh reviewDecision output"
    n = data.get("number", "?")
    decision = data.get("reviewDecision") or ""
    if decision == "APPROVED":
        return True, f"PR #{n}: review approved"
    if decision == "CHANGES_REQUESTED":
        return False, f"PR #{n}: review requested changes"
    return False, f"PR #{n}: review pending (decision={decision or 'none'})"


def check_pr_merged() -> tuple[bool, str]:
    code, out = _gh(["pr", "view", "--json", "number,state"])
    if code != 0:
        return False, "no PR for current branch"
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return False, "malformed gh output"
    if data.get("state") == "MERGED":
        return True, f"PR #{data.get('number')} is merged"
    return False, f"PR #{data.get('number')} state is {data.get('state')}"


CHECKS = {
    "issue.created": check_issue_created,
    "branch.created": check_branch_created,
    "branch.pushed": check_branch_pushed,
    "pr.opened": check_pr_opened,
    "ci.green": check_ci_green,
    "review.approved": check_review_approved,
    "pr.merged": check_pr_merged,
}


def prereqs_satisfied(node: str, _seen: set[str] | None = None) -> tuple[bool, str]:
    """Walk all ancestors of `node` and return (True, '') if every prereq passes,
    else (False, '<first failing prereq>: <reason>').
    """
    if node not in GRAPH:
        return False, f"unknown node: {node}"
    seen = _seen if _seen is not None else set()
    if node in seen:
        return True, ""
    seen.add(node)
    for prereq in GRAPH[node]:
        ok, reason = CHECKS[prereq]()
        if not ok:
            return False, f"{prereq}: {reason}"
        ok, reason = prereqs_satisfied(prereq, seen)
        if not ok:
            return False, reason
    return True, "all prerequisites satisfied"


# Steering rules: command pattern -> (target_node | None, redirect_message)
# The first matching rule wins. target_node=None means a hard block with no
# DAG validation; otherwise, prereqs of target_node are appended to the reason.
COMMAND_RULES: list[tuple[re.Pattern[str], str | None, str]] = [
    (
        re.compile(r"git\s+push\s+(?:\S+\s+)?(?:origin\s+)?(?:main|master)\b"),
        None,
        "Direct pushes to main/master are blocked. Open a feature branch and PR.",
    ),
    (
        re.compile(r"\bgh\s+api\s+repos/[^/\s]+/[^/\s]+/pulls/\d+/merge\b"),
        "pr.merged",
        "Use .claude/scripts/monitor-pr.sh <pr> --merge instead of `gh api .../merge` so CI and review gates are honored.",
    ),
    (
        re.compile(r"\bgh\s+pr\s+merge\b"),
        "pr.merged",
        "Use .claude/scripts/monitor-pr.sh <pr> --merge instead of `gh pr merge` so CI, review waits, and review cycles are handled.",
    ),
    (
        re.compile(r"\bgh\s+pr\s+checks\b.*--watch"),
        None,
        "Use .claude/scripts/monitor-pr.sh <pr> --merge instead of `gh pr checks --watch`.",
    ),
    (
        re.compile(r"\bgh\s+pr\s+ready\b"),
        "pr.opened",
        "Use .claude/scripts/promote-review.sh instead of `gh pr ready`.",
    ),
    (
        re.compile(r"\bgh\s+pr\s+create\b"),
        "pr.opened",
        "Use .claude/scripts/start-issue.sh (issue-backed) or .claude/scripts/create-nojira-pr.sh (no issue) instead of `gh pr create`.",
    ),
    (
        re.compile(r"\bgh\s+issue\s+create\b"),
        None,
        "Use .claude/scripts/create-issue.sh (or the start-task skill) so priority, references, and acceptance criteria are captured.",
    ),
    (
        re.compile(r"\bgit\s+push\b"),
        "branch.pushed",
        "Use .claude/scripts/push-branch.sh instead of raw `git push` so transient GitHub failures are retried and the remote SHA is verified.",
    ),
]


def _redirect_target_exists(reason: str) -> bool:
    """Best-effort: scan the redirect message for a `.claude/scripts/<name>`
    reference and check whether the file exists. If no reference is found,
    treat the rule as always-applicable (e.g. main/master block).
    """
    m = re.search(r"\.claude/scripts/([\w.-]+)", reason)
    if not m:
        return True
    return (Path(".claude/scripts") / m.group(1)).exists()


def guard(payload: dict) -> dict | None:
    cmd = ((payload.get("tool_input") or {}).get("command") or "").strip()
    if not cmd:
        return None

    for pattern, target, message in COMMAND_RULES:
        if not pattern.search(cmd):
            continue
        # If the redirect points at a wrapper script that doesn't exist in
        # this repo, skip (don't block — there's nothing to redirect to).
        if not _redirect_target_exists(message):
            continue

        reason = message
        if target is not None:
            ok, why = prereqs_satisfied(target)
            if not ok:
                reason = f"{message}\n\nDAG prerequisite for {target} not met: {why}."
        return {"decision": "block", "reason": reason}
    return None


def cmd_check(node: str) -> int:
    if node not in GRAPH:
        sys.stdout.write(f"unknown node: {node}\n")
        return 2
    ok, reason = prereqs_satisfied(node)
    if ok:
        # Also report the node's own check, for human consumption.
        own_ok, own_reason = CHECKS[node]()
        marker = "OK" if own_ok else "REACHABLE (state not yet satisfied)"
        sys.stdout.write(f"{marker}: {node} — {own_reason}\n")
        return 0 if own_ok else 0  # prereqs satisfied = transition allowed
    sys.stdout.write(f"BLOCKED: cannot reach {node}: {reason}\n")
    return 2


def cmd_guard() -> int:
    raw = sys.stdin.read()
    if not raw:
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    result = guard(payload)
    if result is not None:
        sys.stdout.write(json.dumps(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dag-workflow")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check", help="check whether a node is reachable")
    p_check.add_argument("node", help="DAG node name (e.g. pr.merged)")
    sub.add_parser("guard", help="PreToolUse hook entrypoint (reads stdin)")
    sub.add_parser("nodes", help="list all DAG nodes")
    args = parser.parse_args(argv)

    if args.cmd == "check":
        return cmd_check(args.node)
    if args.cmd == "guard":
        return cmd_guard()
    if args.cmd == "nodes":
        for node, prereqs in GRAPH.items():
            sys.stdout.write(f"{node}: requires={prereqs or '[]'}\n")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
