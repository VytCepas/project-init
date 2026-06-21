"""PI-360: always-on hooks must run on macOS /bin/bash (bash 3.2) + BSD coreutils.

The commit gate and the SessionStart bootstrap fire on first commit / first
session, so a bash-4-only builtin or a GNU-only tool there breaks a macOS user
on contact. These are content contracts over both the source-of-truth fallback
templates and the derived plugin payload (kept in sync by tools/sync_plugin.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


@pytest.mark.parametrize("name", _ALWAYS_ON)
@pytest.mark.parametrize("builtin", _BASH4_BUILTINS)
def test_no_bash4_builtins(name: str, builtin: str):
    for path in _hook_files(name):
        assert path.exists(), f"missing always-on hook: {path}"
        assert builtin not in _code_lines(path.read_text()), (
            f"{path} uses bash-4 builtin {builtin!r} — breaks macOS bash 3.2"
        )


def test_session_setup_fingerprint_is_shasum_aware():
    """The bootstrap fingerprint must not assume GNU sha256sum exists."""
    for path in _hook_files("session_setup.sh"):
        text = path.read_text()
        assert "shasum -a 256" in text, f"{path}: no BSD shasum fallback for sha256"
        assert "command -v sha256sum" in text, f"{path}: must probe for sha256sum"


def test_commit_gate_builds_arrays_portably():
    """Staged-file lists are read with a while-loop, not mapfile."""
    for path in _hook_files("pre_commit_gate.sh"):
        code = _code_lines(path.read_text())
        assert "while IFS= read -r" in code, f"{path}: expected portable read loop"
        assert "STAGED_PY+=(" in code and "STAGED_JS+=(" in code
