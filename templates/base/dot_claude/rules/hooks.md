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
| `bash_safety_guard.sh` | PreToolUse | Bash |
| `github_command_guard.sh` | PreToolUse | Bash — steers agents toward lifecycle scripts |
| `pre_commit_gate.sh` | PreToolUse | Bash containing `git commit` |
| `post_edit_lint.sh` | PostToolUse | Edit / Write / MultiEdit |
| `workflow_state_reminder.sh` | UserPromptSubmit | injects workflow lifecycle context |

**Manual invocation** (debugging or one-off runs only):
```bash
python3 .claude/hooks/secret-guard.py    # test secret detection
bash .claude/hooks/pre_commit_gate.sh    # run lint gate manually
bash .claude/hooks/post_edit_lint.sh     # run lint on last edited file
```

Do not read hook scripts to understand their logic — descriptions above are sufficient. Only open a hook file if you are modifying it. To add a new hook, run the `add_hook` skill.
