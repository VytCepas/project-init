"""PI-195: execution coverage for install.sh (the curl|bash bootstrap).

It was previously only string-checked (read as text), never run. Here we run
it for real with stubbed `uv`/`git`/`curl` so no network or actual installs
happen, and assert it completes and writes the slash command.

PI-1045: install.sh refuses a ref whose prod_guard lacks the symlink refusal.
The git stub serves each ref's guard from a fixture file, so the tests pick
which refs carry the refusal and which do not.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_SH = _REPO_ROOT / "install.sh"
_GUARD = "templates/base/dot_agents/hooks/prod_guard.py"

# git stub: `clone` creates <dest>/.git; `show <ref>:<path>` prints
# $STUB_REFS/<ref with / as _>; `rev-parse ... refs/remotes/<x>` succeeds only
# when that fixture exists (a remote branch). Every call is logged.
_GIT_STUB = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$STUB_LOG"
[ "$1" = -C ] && shift 2
case "$1" in
  clone) mkdir -p "${@: -1}/.git" ;;
  show) spec="$2"; ref="${spec%%:*}"; f="$STUB_REFS/${ref//\//_}"
        [ -f "$f" ] || { echo "fatal: invalid object name $ref" >&2; exit 128; }
        cat "$f" ;;
  rev-parse) ref="${@: -1}"; ref="${ref#refs/remotes/}"
             [ -f "$STUB_REFS/${ref//\//_}" ] || exit 1 ;;
esac
exit 0
"""


def _guard_with_refusal() -> str:
    return (_REPO_ROOT / _GUARD).read_text()


def _guard_without_refusal() -> str:
    # The real guard with the refusal taken out, as in v1.2.2 and older.
    return _guard_with_refusal().replace("is_symlink", "exists")


def _run_install(tmp_path: Path, refs: dict[str, str], **env_extra: str):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir(exist_ok=True)
    for ref, text in refs.items():
        (refs_dir / ref.replace("/", "_")).write_text(text)
    # uv is a no-op; curl answers the latest-release query with v1.2.2.
    stubs = {
        "uv": "#!/usr/bin/env bash\nexit 0\n",
        "git": _GIT_STUB,
        "curl": '#!/usr/bin/env bash\nprintf \'{"tag_name": "v1.2.2"}\\n\'\n',
    }
    for name, body in stubs.items():
        (bindir / name).write_text(body)
        (bindir / name).chmod(0o755)
    env = {
        "HOME": str(home),
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "PROJECT_INIT_HOME": str(tmp_path / "install"),
        "STUB_REFS": str(refs_dir),
        "STUB_LOG": str(tmp_path / "git.log"),
        **env_extra,
    }
    result = subprocess.run(["bash", str(_INSTALL_SH)], capture_output=True, text=True, env=env)
    log = (tmp_path / "git.log").read_text() if (tmp_path / "git.log").exists() else ""
    return result, log, home / ".claude" / "commands" / "project-init.md"


def test_install_sh_syntax_is_valid():
    result = subprocess.run(["bash", "-n", str(_INSTALL_SH)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_install_sh_writes_slash_command_with_stubs(tmp_path: Path):
    # The git stub minimally emulates `clone <url> <dest>` by creating
    # <dest>/.git, so install.sh runs against a real clone directory instead of
    # an all-no-op stub that hides whether the clone path ran (PI-195 review).
    result, _log, cmd = _run_install(
        tmp_path, {"origin/main": _guard_with_refusal()}, PROJECT_INIT_REF="main"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # The clone branch must have run (not the "update existing clone" path).
    assert (tmp_path / "install" / ".git").is_dir(), "install.sh must clone into INSTALL_DIR"

    # Claude Code's OWN config dir — NOT a project-init one. PI-606/#620 renamed
    # both install.sh and this assertion to ~/.agents/commands, so the test kept
    # passing while every fresh install produced a /project-init that Claude Code
    # never loaded (PI-877). Do not "fix" a failure here by renaming the path.
    assert cmd.is_file(), "install.sh must write the /project-init slash command"
    assert "project-init" in cmd.read_text()
    assert not (tmp_path / "home" / ".agents" / "commands").exists(), (
        "install.sh must not write commands under ~/.agents (PI-877)"
    )


def test_installed_template_carries_the_symlink_refusal():
    """PI-1045: the file install.sh checks exists at HEAD and has the marker it greps.

    If a refactor renames the refusal or moves the file, install.sh would refuse
    every ref, main included. This fails first.
    """
    declared = re.search(r'^GUARD_FILE="([^"]+)"$', _INSTALL_SH.read_text(), re.MULTILINE)
    assert declared and declared.group(1) == _GUARD
    assert "is_symlink" in _guard_with_refusal()


def test_default_release_without_refusal_is_refused(tmp_path: Path):
    """PI-1045: the latest release (v1.2.2) lacks the refusal, so the default install stops."""
    result, log, cmd = _run_install(
        tmp_path, {"v1.2.2": _guard_without_refusal(), "origin/main": _guard_with_refusal()}
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "PROJECT_INIT_REF=main" in result.stderr
    assert "symlink refusal" in result.stderr
    assert "show v1.2.2:" + _GUARD in log, "the refusal must come from reading the ref's guard"
    assert "checkout" not in log, "a refused ref must never be checked out"
    assert not cmd.exists(), "a refused install must not write the slash command"


def test_existing_clone_is_not_moved_to_a_refused_ref(tmp_path: Path):
    """A re-run that resolves a refused ref leaves the working clone and command alone."""
    (tmp_path / "install" / ".git").mkdir(parents=True)
    cmd = tmp_path / "home" / ".claude" / "commands" / "project-init.md"
    cmd.parent.mkdir(parents=True)
    cmd.write_text("sentinel\n")
    result, log, _ = _run_install(
        tmp_path, {"v1.2.2": _guard_without_refusal()}, PROJECT_INIT_REF="v1.2.2"
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "fetch" in log, "the update path must have run"
    assert "checkout" not in log
    assert cmd.read_text() == "sentinel\n"


def test_ref_whose_guard_cannot_be_read_is_refused(tmp_path: Path):
    """Fail closed: no guard file at the ref means the refusal cannot be confirmed."""
    result, log, cmd = _run_install(tmp_path, {}, PROJECT_INIT_REF="v9.9.9")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "cannot read" in result.stderr
    assert "checkout" not in log
    assert not cmd.exists()


def test_release_with_refusal_installs(tmp_path: Path):
    """A pinned tag whose guard carries the refusal is checked out and installed."""
    result, log, cmd = _run_install(
        tmp_path, {"v1.3.0": _guard_with_refusal()}, PROJECT_INIT_REF="v1.3.0"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "checkout -q v1.3.0" in log
    assert cmd.is_file()
