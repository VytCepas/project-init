# `.claude/hooks/`

Session hooks — deterministic bash or python scripts. The `settings.json` at `.claude/settings.json` wires them to Claude Code events (SessionStart, SessionEnd, PreToolUse, etc.).

Keep hooks fast, idempotent, and non-interactive.

## Hook Executability Convention

- **Shell hooks** (`.sh` files): Must have the executable bit (`+x`). They run directly via `bash path/to/hook.sh`.
- **Python hooks** (`.py` files): Do NOT need the executable bit. They are invoked via `python3 path/to/hook.py`.
