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
    # uv is a pure no-op; git minimally emulates `clone <url> <dest>` by creating
    # <dest>/.git, so install.sh runs against a real clone directory instead of an
    # all-no-op stub that hides whether the clone path actually ran (PI-195 review).
    (bindir / "uv").write_text("#!/usr/bin/env bash\nexit 0\n")
    (bindir / "uv").chmod(0o755)
    git_stub = bindir / "git"
    git_stub.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = clone ]; then mkdir -p "${@: -1}/.git"; fi\n'
        "exit 0\n"
    )
    git_stub.chmod(0o755)

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
    # The clone branch must have run (not the "update existing clone" path).
    assert (tmp_path / "install" / ".git").is_dir(), "install.sh must clone into INSTALL_DIR"

    cmd = home / ".claude" / "commands" / "project-init.md"
    assert cmd.is_file(), "install.sh must write the /project-init slash command"
    assert "project-init" in cmd.read_text()
