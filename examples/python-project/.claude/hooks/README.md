# `.claude/hooks/`

Session hooks — deterministic bash or python scripts. The `settings.json` at `.claude/settings.json` wires them to Claude Code events (SessionStart, SessionEnd, PreToolUse, etc.).

Keep hooks fast, idempotent, and non-interactive.
