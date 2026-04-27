---
description: Hook reference — what each hook does and how to invoke manually
globs: [".claude/settings.json", ".claude/hooks/**"]
alwaysApply: false
---

## Hooks in this project

All hooks fire automatically — do not invoke them manually in normal flow.

| Hook | Event | Trigger |
|---|---|---|
| `secret-guard.py` | PreToolUse | any Write / Edit / Bash |
| `bash-safety-guard.sh` | PreToolUse | Bash |
| `pre-commit-gate.sh` | PreToolUse | Bash containing `git commit` |
| `post-edit-lint.sh` | PostToolUse | Edit / Write / MultiEdit |
| `session-end.sh` | Stop | end of session (Obsidian preset only) |

**Manual invocation** (debugging or one-off runs only):
```bash
python3 .claude/hooks/secret-guard.py    # test secret detection
bash .claude/hooks/pre-commit-gate.sh    # run lint gate manually
bash .claude/hooks/post-edit-lint.sh     # run lint on last edited file
```

Do not read hook scripts to understand their logic — descriptions above are sufficient. Only open a hook file if you are modifying it. To add a new hook, run the `add-hook` skill.
