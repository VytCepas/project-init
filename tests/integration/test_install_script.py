"""PI-195: execution coverage for install.sh (the curl|bash bootstrap).

It was previously only string-checked (read as text), never run. Here we run
it for real with stubbed `uv`/`git` and `PROJECT_INIT_REF=main` so no network
or actual installs happen, and assert it completes and writes the slash command.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_SH = _REPO_ROOT / "install.sh"


def test_install_sh_syntax_is_valid():
    result = subprocess.run(
        ["bash", "-n", str(_INSTALL_SH)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_install_sh_writes_slash_command_with_stubs(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # Stub the external tools so the bootstrap runs without network or installs.
    for tool in ("uv", "git"):
        stub = bindir / tool
        stub.write_text("#!/usr/bin/env bash\nexit 0\n")
        stub.chmod(0o755)

    env = {
        "HOME": str(home),
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "PROJECT_INIT_REF": "main",  # short-circuits the network ref resolution
        "PROJECT_INIT_HOME": str(tmp_path / "install"),
    }
    result = subprocess.run(
        ["bash", str(_INSTALL_SH)], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stdout + result.stderr

    cmd = home / ".claude" / "commands" / "project-init.md"
    assert cmd.is_file(), "install.sh must write the /project-init slash command"
    assert "project-init" in cmd.read_text()
