#!/usr/bin/env python3
"""secret-guard.py — block API keys, private key material, and PII before they are written.

PreToolUse hook. Receives tool input JSON on stdin. Outputs
{"decision": "block", "reason": "..."} if a secret or personal data pattern
is found in the content being written or the command being run.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Patterns — (compiled_regex, human_label)
# ---------------------------------------------------------------------------

# High-confidence: known API key formats
_API_KEY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-ant-api0\d-[A-Za-z0-9_-]{85,}"), "Anthropic API key"),
    (re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{40,}"), "OpenAI API key"),
    (re.compile(r"ghp_[A-Za-z0-9]{36,}"), "GitHub personal access token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{80,}"), "GitHub fine-grained PAT"),
    (re.compile(r"ghs_[A-Za-z0-9]{36,}"), "GitHub app installation token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key ID"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "Private key material"),
    (re.compile(r"xox[baprs]-[0-9]{8,}-[A-Za-z0-9-]{24,}"), "Slack token"),
]

# Medium-confidence: generic hardcoded secret assignments.
# Matches _KEY=, _SECRET=, _TOKEN=, _PASSWORD= followed by a literal value
# (not a shell variable reference, function call, dict access, or placeholder).
# Excludes . [ ( from value chars so os.environ['KEY'] and get_key() are skipped.
_SECRET_ASSIGNMENT = re.compile(
    r"""(?:_KEY|_SECRET|_TOKEN|_PASSWORD)\s*=\s*(?![\$\{\<])(?!.*(?:your[_\-]?key|replace[_\-]?me|placeholder|example|fake|test|xxxx|here|todo))[^\s\$\{\[\.\(]{16,}""",
    re.IGNORECASE,
)

# Personal data
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "Social Security Number"),
    # Visa (16d), Mastercard (16d starting 51-55), Amex (15d starting 34/37)
    (
        re.compile(
            r"\b(?:4[0-9]{15}|5[1-5][0-9]{14}|3[47][0-9]{13})\b"
        ),
        "Credit/debit card number",
    ),
]

# Personal filesystem paths: detect the user's actual home directory being
# hardcoded into project files or commands. Built at import time from $HOME
# so it catches the exact path without knowing the username in advance.
def _home_path_patterns() -> list[tuple[re.Pattern[str], str]]:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
    if not home or len(home) < 4:
        return []
    escaped = re.escape(home.rstrip("/\\"))
    return [(re.compile(escaped + r"[/\\]\S+"), f"Personal home-directory path ({home}/...)")]

ALL_PATTERNS: list[tuple[re.Pattern[str], str]] = (
    _API_KEY_PATTERNS
    + [(_SECRET_ASSIGNMENT, "Hardcoded secret assignment")]
    + _PII_PATTERNS
    + _home_path_patterns()
)

# ---------------------------------------------------------------------------
# Exemptions
# ---------------------------------------------------------------------------

_EXEMPT_BASENAMES = {".env.example", ".env.sample", ".env.template", ".env.test"}

_PLACEHOLDER_RE = re.compile(
    r"(?:your[_\-]?key|replace[_\-]?me|placeholder|example|fake|xxxx|<[A-Z_]+>|todo|insert[_\-]?here)",
    re.IGNORECASE,
)


def _is_exempt_file(file_path: str) -> bool:
    name = Path(file_path).name.lower()
    return name in _EXEMPT_BASENAMES or name.endswith(".example")


def _scan(text: str, source: str) -> list[str]:
    """Return list of finding descriptions, empty if clean."""
    findings: list[str] = []
    for pattern, label in ALL_PATTERNS:
        match = pattern.search(text)
        if match:
            # Skip if the matched value is adjacent to a placeholder marker
            surrounding = text[max(0, match.start() - 40) : match.end() + 40]
            if _PLACEHOLDER_RE.search(surrounding):
                continue
            findings.append(f"{label} (matched: [REDACTED])")
    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        return 0

    tool_name: str = data.get("tool_name", "")
    tool_input: dict = data.get("tool_input", {})
    file_path: str = tool_input.get("file_path", "")

    if file_path and _is_exempt_file(file_path):
        return 0

    texts: list[tuple[str, str]] = []  # (text, source_label)

    if tool_name == "Write":
        texts.append((tool_input.get("content", ""), file_path or "file content"))
    elif tool_name == "Edit":
        texts.append((tool_input.get("new_string", ""), file_path or "edit"))
    elif tool_name == "MultiEdit":
        for edit in tool_input.get("edits", []):
            texts.append((edit.get("new_string", ""), file_path or "edit"))
    elif tool_name == "Bash":
        texts.append((tool_input.get("command", ""), "shell command"))
    else:
        return 0

    all_findings: list[str] = []
    for text, source in texts:
        all_findings.extend(_scan(text, source))

    if all_findings:
        unique = list(dict.fromkeys(all_findings))  # deduplicate, preserve order
        reason = (
            "Potential secret or personal data detected — refusing to proceed:\n\n"
            + "\n".join(f"  • {f}" for f in unique)
            + "\n\nRemediation:\n"
            + "  • Use environment variables (os.environ['KEY']) instead of hardcoded values\n"
            + "  • Store secrets in a .env file (gitignored) and load with python-dotenv\n"
            + "  • For placeholders in docs/examples, use obvious fakes: sk-fake-..., YOUR_KEY_HERE\n"
            + "  • .env.example files are exempt from this check"
        )
        print(json.dumps({"decision": "block", "reason": reason}))

    return 0


if __name__ == "__main__":
    sys.exit(main())
