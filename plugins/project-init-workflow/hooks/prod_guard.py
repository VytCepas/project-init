"""Prod-safety guard (PI-168, ADR-012): deny destructive infra/DB commands.

PreToolUse hook on Bash. Deterministic deny-table — no LLM, no network.
Destructive operations that bypass the git/CI boundary (cloud deletes,
DROP DATABASE, terraform destroy, …) get:

- ``ask``   in interactive sessions — a human confirms or rejects;
- ``deny``  in fully autonomous sessions (``bypassPermissions``) — there is
  no human to ask, so the command is blocked outright.

Escape hatch: ``safety.allow`` in ``.claude/config.yaml`` holds a JSON list
of regex patterns; a command matching any of them is never flagged. Use it
for known-safe contexts (e.g. a dev-cluster kubectl context).

This is a guardrail, not the security boundary (ADR-007/ADR-012): a
sufficiently creative command can evade a deny-list. The guarantee comes
from credential separation — agent sessions must never hold production
credentials (see .claude/docs/guides/secrets.md).

Fail-open by design: any internal error lets the command proceed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# (pattern, label) — matched against the full command string.
DENY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bterraform\s+(destroy|apply\s+.*-destroy)\b"), "terraform destroy"),
    (re.compile(r"\bkubectl\s+delete\b"), "kubectl delete"),
    (re.compile(r"\bhelm\s+(uninstall|delete)\b"), "helm uninstall"),
    (re.compile(r"\baws\s+\S+\s+(delete|terminate|remove)\S*\b"), "aws delete/terminate"),
    (re.compile(r"\baws\s+s3\s+(rb|rm\s+.*--recursive)\b"), "aws s3 bucket/recursive removal"),
    (re.compile(r"\bgcloud\s+.*\bdelete\b"), "gcloud delete"),
    (re.compile(r"\baz\s+\S+.*\bdelete\b"), "az delete"),
    (re.compile(r"\bdrop\s+(table|database|schema)\b", re.IGNORECASE), "SQL DROP"),
    (re.compile(r"\btruncate\s+table\b", re.IGNORECASE), "SQL TRUNCATE"),
    (re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)[a-zA-Z]*\s+(/(?!tmp\b)|~)"),
     "recursive force-remove outside the project"),
    (re.compile(r"\bgh\s+repo\s+delete\b"), "gh repo delete"),
    (re.compile(r"\bdocker\s+(volume\s+prune|system\s+prune)\b"), "docker prune"),
]

# Fully autonomous mode: no human is watching the prompt, so "ask" is
# meaningless — block outright. Other modes (default, plan, acceptEdits)
# still surface an interactive permission prompt for Bash.
_AUTONOMOUS_MODES = {"bypassPermissions", "dangerouslySkipPermissions"}


def _allow_patterns(root: Path) -> list[re.Pattern[str]]:
    """Read the safety.allow JSON list from .claude/config.yaml (fail-open)."""
    config = root / ".claude" / "config.yaml"
    try:
        in_safety = False
        for line in config.read_text(encoding="utf-8").splitlines():
            if line.startswith("safety:"):
                in_safety = True
                continue
            if in_safety:
                if line.strip() and not line.startswith(" "):
                    break
                stripped = line.strip()
                if stripped.startswith("allow:"):
                    raw = stripped.split(":", 1)[1].strip()
                    return [re.compile(p) for p in json.loads(raw)]
    except (OSError, json.JSONDecodeError, re.error):
        pass
    return []


def evaluate(command: str, permission_mode: str, allow: list[re.Pattern[str]]) -> dict | None:
    """Return the hook verdict for *command*, or None to let it through."""
    if any(p.search(command) for p in allow):
        return None
    for pattern, label in DENY_RULES:
        if pattern.search(command):
            reason = (
                f"prod_guard: '{label}' is a destructive operation. "
                "If this is intentional and safe, add a matching regex to "
                "safety.allow in .claude/config.yaml, or run it yourself. "
                "(Guardrail only — real protection is credential separation, "
                "see .claude/docs/guides/secrets.md.)"
            )
            if permission_mode in _AUTONOMOUS_MODES:
                return {"decision": "block", "reason": reason}
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            }
    return None


def main() -> int:
    """Read the PreToolUse payload from stdin; print a verdict if any."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    command = ((payload.get("tool_input") or {}).get("command") or "").strip()
    if not command:
        return 0
    mode = payload.get("permission_mode") or payload.get("permissionMode") or ""
    root = Path(payload.get("cwd") or ".")
    try:
        verdict = evaluate(command, mode, _allow_patterns(root))
    except Exception:  # noqa: BLE001 — guardrail must never break the session
        return 0
    if verdict is not None:
        sys.stdout.write(json.dumps(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
