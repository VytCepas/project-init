"""Refuse a native Windows shell before anything runs (#1070, ADR-030).

project-init supports macOS and Linux; on Windows it runs only inside WSL2.
Native means ``uname -s`` starts with MINGW, MSYS or CYGWIN (Git Bash, MSYS2,
Cygwin), or Python's ``platform.system()`` is ``Windows``.
"""

from __future__ import annotations

import platform
import shutil
import subprocess

_NATIVE_PREFIXES = ("MINGW", "MSYS", "CYGWIN")
REFUSAL_EXIT = 1


def native_windows_shell() -> str | None:
    """Return the native Windows system name this process runs under, else None."""
    system = platform.system()
    if system == "Windows" or system.upper().startswith(_NATIVE_PREFIXES):
        return system
    uname = shutil.which("uname")
    if uname is None:
        return None
    try:
        out = subprocess.run(
            [uname, "-s"], capture_output=True, text=True, timeout=10, check=False
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out if out.upper().startswith(_NATIVE_PREFIXES) else None


def refusal(system: str) -> str:
    """The message naming WSL2 as the way in."""
    return (
        f"project-init: native Windows shell ({system}) is not supported.\n"
        "Run it inside WSL2 (https://learn.microsoft.com/windows/wsl/install), "
        "from the WSL filesystem (~/...), not /mnt/c/.\n"
    )
