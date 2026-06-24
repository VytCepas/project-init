"""PI-360: always-on hooks must run on macOS /bin/bash (bash 3.2) + BSD coreutils.

The commit gate and the SessionStart bootstrap fire on first commit / first
session, so a bash-4-only builtin or a GNU-only tool there breaks a macOS user
on contact. These are content contracts over both the source-of-truth fallback
templates and the derived plugin payload (kept in sync by tools/sync_plugin.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Both trees that ship the always-on hooks: the --no-plugin fallback source of
# truth and the default plugin payload derived from it.
_HOOK_DIRS = (
    _REPO_ROOT / "templates" / "fallback" / "dot_claude" / "hooks",
    _REPO_ROOT / "plugins" / "project-init-workflow" / "hooks",
)
_ALWAYS_ON = ("pre_commit_gate.sh", "session_setup.sh")

# bash-4+ builtins absent from macOS's stock bash 3.2 (shell policy: floor 3.2).
_BASH4_BUILTINS = ("mapfile", "readarray", "declare -A")


def _hook_files(name: str) -> list[Path]:
    return [d / name for d in _HOOK_DIRS]


def _code_lines(text: str) -> str:
    """Strip comment-only lines so a builtin named in a comment doesn't trip."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


@pytest.mark.parametrize("name", _ALWAYS_ON)
@pytest.mark.parametrize("builtin", _BASH4_BUILTINS)
def test_no_bash4_builtins(name: str, builtin: str):
    for path in _hook_files(name):
        assert path.exists(), f"missing always-on hook: {path}"
        assert builtin not in _code_lines(path.read_text()), (
            f"{path} uses bash-4 builtin {builtin!r} — breaks macOS bash 3.2"
        )


def test_session_setup_fingerprint_is_shasum_aware():
    """The bootstrap fingerprint must not assume GNU sha256sum exists, and must
    stay defined on a host with neither hasher (POSIX cksum fallback)."""
    for path in _hook_files("session_setup.sh"):
        text = path.read_text()
        assert "command -v sha256sum" in text, f"{path}: must probe for sha256sum"
        assert "command -v shasum" in text, f"{path}: must probe for shasum"
        assert "shasum -a 256" in text, f"{path}: no BSD shasum fallback for sha256"
        assert "cksum" in text, f"{path}: no POSIX cksum fallback when neither exists"


def test_commit_gate_builds_arrays_portably():
    """Staged-file lists are read with a while-loop, not mapfile."""
    for path in _hook_files("pre_commit_gate.sh"):
        code = _code_lines(path.read_text())
        assert "while IFS= read -r" in code, f"{path}: expected portable read loop"
        assert "STAGED_PY+=(" in code and "STAGED_JS+=(" in code


def _command_hooks(hooks_block: dict) -> list[dict]:
    """Flatten every command-type hook object across all events."""
    out: list[dict] = []
    for event_entries in hooks_block.values():
        for entry in event_entries:
            for hook in entry.get("hooks", []):
                if hook.get("type") == "command":
                    out.append(hook)
    return out


def test_plugin_hooks_pin_bash_shell():
    """PI-463: every command hook pins shell:bash so native Windows uses Git
    Bash (and never silently falls back to PowerShell, which can't run a bash
    shebang or expand POSIX $CLAUDE_PLUGIN_ROOT)."""
    config = json.loads(
        (_REPO_ROOT / "plugins" / "project-init-workflow" / "hooks" / "hooks.json").read_text()
    )
    cmds = _command_hooks(config["hooks"])
    assert cmds, "plugin hooks.json must define at least one command hook"
    for hook in cmds:
        assert hook.get("shell") == "bash", (
            f'plugin hook {hook.get("command")!r} must set "shell": "bash"'
        )


def test_scaffolded_settings_hooks_pin_bash_shell(tmp_path: Path):
    """The --no-plugin scaffold wires hooks in settings.json; each must pin
    shell:bash for the same native-Windows reason (PI-463)."""
    target = tmp_path / "proj"
    scaffold(target, fallback_preset(), fallback_variables())
    settings = json.loads((target / ".claude" / "settings.json").read_text())
    cmds = _command_hooks(settings.get("hooks", {}))
    assert cmds, "no-plugin settings.json must wire command hooks"
    for hook in cmds:
        assert hook.get("shell") == "bash", (
            f'settings.json hook {hook.get("command")!r} must set "shell": "bash"'
        )
