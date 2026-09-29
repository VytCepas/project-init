"""PI-195: execution coverage for install.sh (the curl|bash bootstrap).

It runs install.sh for real against a local upstream repo with real git, so
clone, fetch, checkout and fast-forward behave as they do for a user. Only `uv` (a
no-op) and `curl` (the latest-release query) are stubbed, and HOME is a temp
dir, so there is no network and nothing outside tmp is written. The race test
wraps git in a shim that commits upstream mid-run, then execs the real git.

PI-1045: install.sh refuses a ref whose prod_guard lacks the symlink refusal,
and after checkout it refuses a clone whose working tree is not that verified
ref: local commits, uncommitted edits, or a skip-worktree edit git hides.
"""

from __future__ import annotations

import os
import re
import shutil
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
        self.bindir = bindir = tmp / "bin"
        for d in (self.home, bindir, self.upstream):
            d.mkdir()
        stubs = {
            "uv": "#!/usr/bin/env bash\nexit 0\n",
            # STUB_NO_RELEASE=1: no release published, so install.sh takes the default branch.
            "curl": '#!/usr/bin/env bash\n[ -z "${STUB_NO_RELEASE:-}" ] || exit 22\n'
            'printf \'{"tag_name": "v1.2.2"}\\n\'\n',
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
        # A minimal hatch wheel layout so refuse_ignored (PI-1047) has packaged
        # paths to check: one `packages` entry, one `force-include` entry.
        (self.upstream / "pyproject.toml").write_text(
            '[tool.hatch.build.targets.wheel]\npackages = ["src/project_init"]\n\n'
            "[tool.hatch.build.targets.wheel.force-include]\n"
            '"templates" = "project_init/templates"\n'
        )
        (self.upstream / ".gitignore").write_text("*.local\n")
        src = self.upstream / "src" / "project_init"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        # templates/ already exists: guard.parent.mkdir(parents=True) above made
        # templates/base/dot_agents/hooks/.
        (self.upstream / "templates" / "marker.txt").write_text("tracked\n")
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

    def commit_upstream(self, path: str, text: str, message: str) -> str:
        (self.upstream / path).write_text(text)
        _git(self.upstream, "add", "-A")
        _git(self.upstream, "commit", "-q", "-m", message)
        return _git(self.upstream, "rev-parse", "HEAD")

    def race_guard_removal_at_checkout(self) -> None:
        """Upstream drops the refusal between install.sh's check and its update step.

        A `git` shim on install.sh's PATH commits it on the first `checkout`,
        which runs after verify_guard and before the clone is moved.
        """
        unguarded = self.tmp / "unguarded.py"
        unguarded.write_text(_guard_without_refusal())
        real_git = shutil.which("git")
        assert real_git
        shim = self.bindir / "git"
        shim.write_text(
            "#!/usr/bin/env bash\n"
            f'case " $* " in *" checkout "*) if [ ! -e "{self.tmp}/raced" ]; then\n'
            f'  : >"{self.tmp}/raced"; cp "{unguarded}" "{self.upstream / _GUARD}"\n'
            f'  "{real_git}" -C "{self.upstream}" commit -qam "race: drop the refusal"\n'
            "fi ;; esac\n"
            f'exec "{real_git}" "$@"\n'
        )
        shim.chmod(0o755)


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
    """PI-1045: the file install.sh checks exists at HEAD, with the refusal in the shape it matches.

    If a refactor reshapes the refusal or moves the file, install.sh would refuse
    every ref, main included. This names the cause; test_release_with_refusal_installs
    runs the real guard through install.sh's match.
    """
    declared = re.search(r'^GUARD_FILE="([^"]+)"$', _INSTALL_SH.read_text(), re.MULTILINE)
    assert declared and declared.group(1) == _GUARD
    assert _MARKER + _REFUSAL in _guard_with_refusal()


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
    """The branch is verified at origin/<ref>, the tip the fast-forward lands on, not the stale local one."""
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
    """A fast-forward keeps a local commit, so origin/main passing proves nothing about HEAD."""
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


# ── PI-1045 review: the update lands on the verified commit, never a later fetch ──

# (env, the ref label install.sh logs): proves which of the two paths ran.
_BRANCH_PATHS = pytest.mark.parametrize(
    ("ref_env", "label"),
    [({"PROJECT_INIT_REF": "main"}, "main"), ({"STUB_NO_RELEASE": "1"}, "<default branch>")],
    ids=["explicit-branch", "default-branch"],
)


@_BRANCH_PATHS
def test_upstream_commit_landing_after_the_check_is_never_checked_out(
    boot: Bootstrap, ref_env: dict[str, str], label: str
):
    """A second fetch after verify_guard would move the clone past VERIFIED.

    The existing /project-init runs `uvx --from` the clone, so the clone moving
    to an unchecked commit is the harm, even when the run then exits 1.
    """
    boot.existing_clone()
    verified = boot.commit_upstream("README.md", "newer\n", "newer, guard intact")
    boot.race_guard_removal_at_checkout()
    result = boot.run(**ref_env)
    assert f"(ref: {label})" in result.stdout, result.stdout + result.stderr
    raced = _git(boot.upstream, "rev-parse", "HEAD")
    assert raced != verified, "the shim must have committed upstream during the run"
    assert "is_symlink" not in _git(boot.upstream, "show", f"{raced}:{_GUARD}")
    head = _git(boot.install, "rev-parse", "HEAD")
    assert head != raced, "the clone moved to an upstream commit that was never verified"
    assert head == verified, result.stdout + result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert "is_symlink" in (boot.install / _GUARD).read_text()
    assert boot.cmd.is_file()


def _diverge(boot: Bootstrap) -> str:
    """A clone with a local commit while upstream moved on; returns the local commit."""
    boot.existing_clone()
    (boot.install / "README.md").write_text("local\n")
    _git(boot.install, "add", "-A")
    _git(boot.install, "commit", "-q", "-m", "local work")
    boot.commit_upstream("OTHER.md", "upstream\n", "upstream work")
    return _git(boot.install, "rev-parse", "HEAD")


@_BRANCH_PATHS
def test_diverged_local_branch_is_refused_and_kept(
    boot: Bootstrap, ref_env: dict[str, str], label: str
):
    """Landing on VERIFIED is a fast-forward only: a diverged branch stops, nothing is reset."""
    local = _diverge(boot)
    result = boot.run(**ref_env)
    assert f"(ref: {label})" in result.stdout, result.stdout + result.stderr
    assert result.returncode != 0, result.stdout + result.stderr
    assert _git(boot.install, "rev-parse", "HEAD") == local, "the local commit must survive"
    assert (boot.install / "README.md").read_text() == "local\n"
    assert not boot.cmd.exists()


# ── PR #1047 review: a refused git step says why, and that nothing was reset ──


@_BRANCH_PATHS
def test_diverged_local_branch_refusal_says_why_and_that_nothing_was_reset(
    boot: Bootstrap, ref_env: dict[str, str], label: str
):
    """A failed fast-forward is install.sh's refusal, not raw git output under set -e."""
    _diverge(boot)
    result = boot.run(**ref_env)
    assert f"(ref: {label})" in result.stdout, result.stdout + result.stderr
    assert result.returncode == 1, result.stdout + result.stderr
    assert "cannot fast-forward" in result.stderr, result.stderr
    assert "Nothing was reset" in result.stderr, result.stderr


def test_checkout_git_refuses_says_why_and_that_nothing_was_reset(boot: Bootstrap):
    """A stale index.lock makes `git checkout` fail after every check has passed."""
    boot.existing_clone()
    (boot.install / ".git" / "index.lock").write_text("")
    result = boot.run(PROJECT_INIT_REF="v1.3.0")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "cannot check out ref 'v1.3.0'" in result.stderr, result.stderr
    assert "Nothing was reset" in result.stderr, result.stderr
    assert _git(boot.install, "rev-parse", "HEAD") == boot.main
    assert not boot.cmd.exists()


# ── PR #1047 review: the refusal must be code, not the word `is_symlink` ─────

_REFUSAL = "        if agents.is_symlink() or config.is_symlink():\n            continue\n"
_MARKER = '        agents = candidate / ".agents"\n        config = agents / "config.yaml"\n'


def _guard_where(variant: str) -> str:
    """The real guard with its refusal turned into something that is not the refusal."""
    real = _guard_with_refusal()
    assert real.count(_MARKER + _REFUSAL) == 1, "the refusal's shape moved: update this test"
    if variant == "comment":
        return real.replace(
            _REFUSAL, "".join(f"        # {ln.strip()}\n" for ln in _REFUSAL.splitlines())
        )
    if variant == "docstring":
        # The whole construct, marker included, inside a string in the loop body.
        return real.replace(_REFUSAL, f'        """\n{_MARKER}{_REFUSAL}        """\n')
    if variant == "dead-branch":
        nested = "".join(f"    {ln}\n" for ln in (_MARKER + _REFUSAL).splitlines())
        return real.replace(_MARKER + _REFUSAL, "        if False:\n" + nested)
    if variant == "dead-loop":
        # In _find_config, at the walk loop's depth, but in a loop that never runs.
        end = "    return None\n\n\ndef _unquote("
        assert real.count(end) == 1
        return real.replace(_REFUSAL, "").replace(
            end, "    while False:\n" + _MARKER + _REFUSAL + end
        )
    if variant == "unused-helper":
        helper = (
            "\n\ndef _unused(start: Path) -> None:\n    for candidate in (start, *start.parents):\n"
        )
        return real.replace(_REFUSAL, "") + helper + _MARKER + _REFUSAL
    if variant == "never-called":
        assert real.count("config = _find_config(root)") == 1
        return real.replace("config = _find_config(root)", "config = None")
    if variant == "trailing-comment":
        # The old check, with the refusal kept only as comments on its lines.
        return real.replace(
            _REFUSAL,
            "        if agents.exists() or config.exists():"
            '  # if agents.is_symlink() or config.is_symlink(): "PI-903"\n'
            "            continue  # continue\n",
        )
    raise AssertionError(variant)


_NOT_THE_REFUSAL = pytest.mark.parametrize(
    "variant",
    [
        "comment",
        "trailing-comment",
        "docstring",
        "dead-branch",
        "dead-loop",
        "unused-helper",
        "never-called",
    ],
)


@_NOT_THE_REFUSAL
def test_ref_whose_refusal_is_not_live_code_is_refused(boot: Bootstrap, variant: str):
    """verify_guard reads the git object: the word surviving the refusal is not enough."""
    guard = _guard_where(variant)
    assert "is_symlink" in guard
    boot.commit_upstream(_GUARD, guard, variant)
    _git(boot.upstream, "tag", "v1.4.0")
    result = boot.run(PROJECT_INIT_REF="v1.4.0")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "without the symlink refusal" in result.stderr, result.stderr
    assert not boot.cmd.exists()


@_NOT_THE_REFUSAL
def test_on_disk_guard_whose_refusal_is_not_live_code_is_refused(boot: Bootstrap, variant: str):
    """verify_checkout reads the file on disk, behind a skip-worktree edit git hides."""
    guard = boot.existing_clone()
    _git(boot.install, "update-index", "--skip-worktree", _GUARD)
    guard.write_text(_guard_where(variant))
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "on disk has no symlink refusal" in result.stderr, result.stderr
    assert not boot.cmd.exists()


def test_refusal_with_comments_around_it_is_still_the_refusal(boot: Bootstrap):
    """The match skips comments and blank lines, so annotating the refusal never refuses a ref."""
    real = _guard_with_refusal()
    noted = real.replace(_MARKER + _REFUSAL, _MARKER + "\n        # PI-903\n" + _REFUSAL)
    boot.commit_upstream(
        _GUARD, noted.replace("config.is_symlink():", "config.is_symlink():  # PI-903"), "noted"
    )
    _git(boot.upstream, "tag", "v1.4.0")
    result = boot.run(PROJECT_INIT_REF="v1.4.0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert boot.cmd.is_file()


def test_refusal_whose_comments_hold_quotes_is_still_the_refusal(boot: Bootstrap):
    """A quote in a trailing comment is comment text, not the start of a string (#1047)."""
    quoted = (
        '        agents = candidate / ".agents"  # it\'s the marker\n'
        '        config = agents / "config.yaml"  # "config"\n'
        '        if agents.is_symlink() or config.is_symlink():  # see "PI-903"\n'
        "            continue#don't follow a planted link\n"
    )
    boot.commit_upstream(_GUARD, _guard_with_refusal().replace(_MARKER + _REFUSAL, quoted), "q")
    _git(boot.upstream, "tag", "v1.4.0")
    result = boot.run(PROJECT_INIT_REF="v1.4.0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert boot.cmd.is_file()


def test_on_disk_guard_with_crlf_line_endings_keeps_its_refusal(boot: Bootstrap):
    """A Windows clone (core.autocrlf) writes the guard CRLF; that is still the refusal."""
    guard = boot.existing_clone()
    _git(boot.install, "config", "core.autocrlf", "true")
    guard.unlink()
    _git(boot.install, "checkout", "--", _GUARD)
    assert b"\r\n" in guard.read_bytes()
    assert _git(boot.install, "status", "--porcelain") == ""
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 0, result.stdout + result.stderr
    assert boot.cmd.is_file()


# ── PR #1047 review, round 3: git status skips flagged files, so flags refuse ──


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_hidden_edit_to_any_shipped_file_is_refused(boot: Bootstrap, flag: str):
    """`uvx --from` builds every file, so an edit hidden outside the guard refuses too."""
    scaffold = "src/project_init/scaffold.py"
    boot.commit_upstream(scaffold, "def scaffold():\n    refuse_symlinks()\n", "scaffold")
    boot.existing_clone()
    _git(boot.install, "update-index", flag, scaffold)
    edited = "def scaffold():\n    pass\n"
    (boot.install / scaffold).write_text(edited)
    assert _git(boot.install, "status", "--porcelain") == ""
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 1, result.stdout + result.stderr
    assert scaffold in result.stderr and "Nothing was reset" in result.stderr, result.stderr
    assert (boot.install / scaffold).read_text() == edited, "the edit must survive"
    assert not boot.cmd.exists()


# ── PR #1047 follow-up: an ignored file under a packaged path is refused ────


def test_ignored_file_under_a_packaged_path_is_refused(boot: Bootstrap):
    """`git status --porcelain` never lists an ignored file, so it must be checked separately."""
    boot.existing_clone()
    (boot.install / "templates" / "secret.local").write_text("unreviewed\n")
    assert _git(boot.install, "status", "--porcelain") == ""
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ignored files under a packaged path" in result.stderr, result.stderr
    assert "templates/secret.local" in result.stderr, result.stderr
    assert "clean -fdX" in result.stderr, result.stderr
    assert "Nothing was reset" in result.stderr, result.stderr
    assert (boot.install / "templates" / "secret.local").exists(), "nothing must be cleaned up"
    assert not boot.cmd.exists()


def test_ignored_file_outside_a_packaged_path_is_not_refused(boot: Bootstrap):
    """An ignored file that the wheel would never pick up (e.g. a root .venv) is not the harm."""
    boot.existing_clone()
    (boot.install / "unpackaged.local").write_text("irrelevant\n")
    assert _git(boot.install, "status", "--porcelain") == ""
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 0, result.stdout + result.stderr
    assert boot.cmd.is_file()


# ── PR #1047 review, round 4: a local clean filter can hide an edit from status ──


def test_clean_filter_hidden_edit_to_a_packaged_file_is_refused(boot: Bootstrap):
    """A `.git/info/attributes` clean filter can smudge an equal-length edit back to its
    blob's bytes, so both `git status --porcelain` and `ls-files -v` read clean while
    `uvx` still builds the edited working-tree bytes. Only a raw byte compare catches it."""
    target = "templates/marker.txt"  # tracked upstream as "tracked\n" (8 bytes)
    boot.existing_clone()
    clean_filter = boot.tmp / "clean_filter.sh"
    clean_filter.write_text("#!/usr/bin/env bash\nprintf 'tracked\\n'\n")
    clean_filter.chmod(0o755)
    _git(boot.install, "config", "filter.hide.clean", str(clean_filter))
    _git(boot.install, "config", "filter.hide.smudge", "cat")
    (boot.install / ".git" / "info" / "attributes").write_text(f"{target} filter=hide\n")
    edited = "edited1\n"  # 8 bytes: same length as the tracked content
    (boot.install / target).write_text(edited)
    assert _git(boot.install, "status", "--porcelain") == ""
    assert _git(boot.install, "ls-files", "-v", "--", target).startswith("H")
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 1, result.stdout + result.stderr
    assert target in result.stderr and "Nothing was reset" in result.stderr, result.stderr
    assert (boot.install / target).read_text() == edited, "the edit must survive"


# ── #1060: the same smuggle on pyproject.toml itself ────────────────────────


def test_clean_filter_hidden_edit_to_pyproject_is_refused(boot: Bootstrap):
    """packaged_paths() reads pyproject.toml straight off disk to learn the layout, so a
    clean filter that hides an edit there — a rewritten force-include, dependency or entry
    point — must be caught before that file is trusted for anything (project-init#1060).

    The edit keeps the file's byte length: git's stat-based fast path marks a
    path modified on a bare size mismatch without ever running the clean
    filter (verified empirically), so only a same-length edit reaches the
    filtered comparison this attack, and this check, both depend on.
    """
    target = "pyproject.toml"
    boot.existing_clone()
    original = (boot.install / target).read_text()
    clean_filter = boot.tmp / "clean_filter_pyproject.sh"
    orig_file = boot.tmp / "pyproject.orig.toml"
    orig_file.write_text(original)
    clean_filter.write_text(f"#!/usr/bin/env bash\ncat {orig_file}\n")
    clean_filter.chmod(0o755)
    _git(boot.install, "config", "filter.hidepy.clean", str(clean_filter))
    _git(boot.install, "config", "filter.hidepy.smudge", "cat")
    (boot.install / ".git" / "info" / "attributes").write_text(f"{target} filter=hidepy\n")
    # force-include's destination is rewritten in place, same length: "project_init" -> "PROJECT_INIT".
    edited = original.replace(
        '"templates" = "project_init/templates"\n', '"templates" = "PROJECT_INIT/templates"\n'
    )
    assert len(edited) == len(original) and edited != original
    (boot.install / target).write_text(edited)
    assert _git(boot.install, "status", "--porcelain") == ""
    assert _git(boot.install, "ls-files", "-v", "--", target).startswith("H")
    result = boot.run(PROJECT_INIT_REF="main")
    assert result.returncode == 1, result.stdout + result.stderr
    assert target in result.stderr and "Nothing was reset" in result.stderr, result.stderr
    assert (boot.install / target).read_text() == edited, "the edit must survive"
    assert not boot.cmd.exists()
