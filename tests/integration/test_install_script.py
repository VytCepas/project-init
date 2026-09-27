"""PI-195: execution coverage for install.sh (the curl|bash bootstrap).

It runs install.sh for real against a local upstream repo with real git, so
clone, fetch, checkout and pull behave as they do for a user. Only `uv` (a
no-op) and `curl` (the latest-release query) are stubbed, and HOME is a temp
dir, so there is no network and nothing outside tmp is written.

PI-1045: install.sh refuses a ref whose prod_guard lacks the symlink refusal,
and after checkout it refuses a clone whose working tree is not that verified
ref: local commits, uncommitted edits, or a skip-worktree edit git hides.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_SH = _REPO_ROOT / "install.sh"
_GUARD = "templates/base/dot_agents/hooks/prod_guard.py"


def _guard_with_refusal() -> str:
    return (_REPO_ROOT / _GUARD).read_text()


def _guard_without_refusal() -> str:
    # The real guard with the refusal taken out, as in v1.2.2 and older.
    return _guard_with_refusal().replace("is_symlink", "exists")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


class Bootstrap:
    """A local upstream (v1.2.2 without the refusal, v1.3.0 and main with it) and a temp HOME."""

    def __init__(self, tmp: Path, git_env: dict[str, str]):
        self.tmp = tmp
        self.home = tmp / "home"
        self.install = tmp / "install"
        self.upstream = tmp / "upstream"
        self.cmd = self.home / ".claude" / "commands" / "project-init.md"
        bindir = tmp / "bin"
        for d in (self.home, bindir, self.upstream):
            d.mkdir()
        stubs = {
            "uv": "#!/usr/bin/env bash\nexit 0\n",
            "curl": '#!/usr/bin/env bash\nprintf \'{"tag_name": "v1.2.2"}\\n\'\n',
        }
        for name, body in stubs.items():
            (bindir / name).write_text(body)
            (bindir / name).chmod(0o755)
        self.env = {
            **git_env,
            "HOME": str(self.home),
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "PROJECT_INIT_REPO": str(self.upstream),
            "PROJECT_INIT_HOME": str(self.install),
        }
        guard = self.upstream / _GUARD
        guard.parent.mkdir(parents=True)
        _git(self.upstream, "init", "-q", "-b", "main")
        for tag, text in (("v1.2.2", _guard_without_refusal()), ("v1.3.0", _guard_with_refusal())):
            guard.write_text(text)
            _git(self.upstream, "add", "-A")
            _git(self.upstream, "commit", "-q", "-m", tag)
            _git(self.upstream, "tag", tag)
        self.main = _git(self.upstream, "rev-parse", "HEAD")

    def run(self, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(_INSTALL_SH)],
            capture_output=True,
            text=True,
            env={**self.env, **extra},
        )

    def existing_clone(self) -> Path:
        _git(self.tmp, "clone", "-q", str(self.upstream), str(self.install))
        return self.install / _GUARD


@pytest.fixture
def boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Bootstrap:
    # Hermetic git: no global hooks, signing or identity leak into the temp repos.
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = t\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n"
        "[advice]\n\tdetachedHead = false\n"
    )
    git_env = {"GIT_CONFIG_GLOBAL": str(gitconfig), "GIT_CONFIG_NOSYSTEM": "1"}
    for key, value in git_env.items():
        monkeypatch.setenv(key, value)
    return Bootstrap(tmp_path, git_env)


def test_install_sh_syntax_is_valid():
    result = subprocess.run(["bash", "-n", str(_INSTALL_SH)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_install_sh_writes_slash_command(boot: Bootstrap):
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 0, result.stdout + result.stderr
    # The clone branch must have run (not the "update existing clone" path).
    assert _git(boot.install, "rev-parse", "HEAD") == boot.main

    # Claude Code's OWN config dir — NOT a project-init one. PI-606/#620 renamed
    # both install.sh and this assertion to ~/.agents/commands, so the test kept
    # passing while every fresh install produced a /project-init that Claude Code
    # never loaded (PI-877). Do not "fix" a failure here by renaming the path.
    assert boot.cmd.is_file(), "install.sh must write the /project-init slash command"
    assert "project-init" in boot.cmd.read_text()
    assert not (boot.home / ".agents" / "commands").exists(), (
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


def test_default_release_without_refusal_is_refused(boot: Bootstrap):
    """PI-1045: the latest release (v1.2.2) lacks the refusal, so the default install stops."""
    result = boot.run()
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ref 'v1.2.2'" in result.stderr and "symlink refusal" in result.stderr
    assert "PROJECT_INIT_REF=main" in result.stderr
    assert _git(boot.install, "rev-parse", "HEAD") == boot.main, "v1.2.2 must never be checked out"
    assert not boot.cmd.exists(), "a refused install must not write the slash command"


def test_existing_clone_is_not_moved_to_a_refused_ref(boot: Bootstrap):
    """A re-run that resolves a refused ref leaves the working clone and command alone."""
    boot.existing_clone()
    boot.cmd.parent.mkdir(parents=True)
    boot.cmd.write_text("sentinel\n")
    result = boot.run(PROJECT_INIT_REF="v1.2.2")
    assert result.returncode == 1, result.stdout + result.stderr
    assert _git(boot.install, "rev-parse", "HEAD") == boot.main
    assert boot.cmd.read_text() == "sentinel\n"


def test_ref_whose_guard_cannot_be_read_is_refused(boot: Bootstrap):
    """Fail closed: a ref without the guard file cannot have its refusal confirmed."""
    result = boot.run(PROJECT_INIT_REF="v9.9.9")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "cannot read" in result.stderr
    assert not boot.cmd.exists()


def test_release_with_refusal_installs(boot: Bootstrap):
    """A pinned tag whose guard carries the refusal is checked out and installed."""
    result = boot.run(PROJECT_INIT_REF="v1.3.0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(boot.install, "rev-parse", "HEAD") == _git(boot.upstream, "rev-parse", "v1.3.0")
    assert boot.cmd.is_file()


def test_existing_stale_clone_updates_to_the_verified_tip(boot: Bootstrap):
    """The branch is verified at origin/<ref>, the tip the pull lands on, not the stale local one."""
    boot.existing_clone()
    (boot.upstream / "README.md").write_text("newer\n")
    _git(boot.upstream, "add", "-A")
    _git(boot.upstream, "commit", "-q", "-m", "newer")
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(boot.install, "rev-parse", "HEAD") == _git(boot.upstream, "rev-parse", "HEAD")
    assert boot.cmd.is_file()


def test_local_commit_that_keeps_the_refusal_is_still_refused(boot: Bootstrap):
    """HEAD must be the verified origin commit: unreviewed local work is not installed either."""
    boot.existing_clone()
    (boot.install / "README.md").write_text("local\n")
    _git(boot.install, "add", "-A")
    _git(boot.install, "commit", "-q", "-m", "local, guard intact")
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not the verified" in result.stderr
    assert not boot.cmd.exists()


# ── PI-1045 review: verify what will actually be used, not only origin/<ref> ──


def test_local_commit_removing_the_refusal_is_refused(boot: Bootstrap):
    """`pull --ff-only` keeps a local commit, so origin/main passing proves nothing about HEAD."""
    guard = boot.existing_clone()
    guard.write_text(_guard_without_refusal())
    _git(boot.install, "commit", "-q", "-am", "local: drop the refusal")
    local = _git(boot.install, "rev-parse", "HEAD")
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not the verified" in result.stderr and "Nothing was reset" in result.stderr
    assert _git(boot.install, "rev-parse", "HEAD") == local, "the local commit must survive"
    assert not boot.cmd.exists()


def test_uncommitted_edit_removing_the_refusal_is_refused(boot: Bootstrap):
    guard = boot.existing_clone()
    guard.write_text(_guard_without_refusal())
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "uncommitted changes" in result.stderr and _GUARD in result.stderr
    assert "Nothing was reset" in result.stderr
    assert "is_symlink" not in guard.read_text(), "the edit must survive"
    assert not boot.cmd.exists()


def test_edit_hidden_by_skip_worktree_is_refused(boot: Bootstrap):
    """git reports the tree clean and HEAD verified; only the file on disk shows the edit."""
    guard = boot.existing_clone()
    _git(boot.install, "update-index", "--skip-worktree", _GUARD)
    guard.write_text(_guard_without_refusal())
    assert _git(boot.install, "status", "--porcelain") == ""
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "on disk" in result.stderr and "Nothing was reset" in result.stderr
    assert not boot.cmd.exists()
