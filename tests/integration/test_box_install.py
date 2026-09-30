"""PI-1046: `just install` (tools/box_install.py), the box install of a checkout as a uv tool.

Each test copies the tool into a throwaway git repo with a bare `origin`, so the
branch, dirty-tree and sync gates run against real git. `uv` is a PATH stub that
answers `uv tool dir` with a temp dir, `uv python find` with the layout's own
interpreter, and logs every call, so nothing touches the real uv tool dir. That
interpreter is a stub that reports its purelib and scripts dirs, which is what
lets a test lay out a Windows env on any OS. The test at the end runs the real
uv into a temp dir, which proves the layout and metadata `--check` reads are
uv's and hatchling's own.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import find_uv

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _REPO_ROOT / "tools" / "box_install.py"
_REAL_HOME = str(Path.home())  # read before any fixture points HOME at a temp dir

_UV_STUB = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$STUB_UV_LOG"
case "$1 $2" in
  "tool dir") if [ "${3:-}" = --bin ]; then echo "$STUB_BIN_DIR"; else echo "$STUB_TOOL_DIR"; fi ;;
  "tool install") [ -z "${STUB_LAYOUT:-}" ] || cp -R "$STUB_LAYOUT/." "$STUB_TOOL_DIR/project-init/" ;;
  "python find") cat "${@: -1}/.stub-python" 2>/dev/null || exit 2 ;;
esac
exit 0
"""

# Spellings the build backend normalises: names, spacing, quotes, specifier
# order, markers inside extras. The real-uv test proves hatchling agrees.
_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "project-init"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = ["tomli >= 2 ; python_version < '3.11'"]

[project.optional-dependencies]
Docs_Extra = ["mkdocs-material>=9.7.6", "colorama; sys_platform == \\"win32\\"", "Foo_Bar[X] >=1, <2"]

[project.scripts]
project-init = "project_init.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/project_init"]

[tool.hatch.build.targets.wheel.force-include]
"templates" = "project_init/templates"
"schemas" = "project_init/schemas"
"""

# What hatchling writes for _PYPROJECT (measured by the real-uv test).
_METADATA = """\
Metadata-Version: 2.4
Name: project-init
Version: 0.0.1
Requires-Python: >=3.11
Requires-Dist: tomli>=2; python_version < '3.11'
Provides-Extra: docs-extra
Requires-Dist: colorama; (sys_platform == 'win32') and extra == 'docs-extra'
Requires-Dist: foo-bar[x]<2,>=1; extra == 'docs-extra'
Requires-Dist: mkdocs-material>=9.7.6; extra == 'docs-extra'
"""
_ENTRY_POINTS = "[console_scripts]\nproject-init = project_init.cli:main\n"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


class Box:
    """A temp checkout with the tool, a bare origin, a stub uv, and a tool dir."""

    def __init__(self, tmp: Path, git_env: dict[str, str], object_format: str = "sha1"):
        self.tmp = tmp
        self.repo = tmp / "repo"
        self.tools = tmp / "uv-tools"
        self.bin = tmp / "uv-bin"
        self.env_dir = self.tools / "project-init"
        self.uv_log = tmp / "uv.log"
        stub_dir = tmp / "stub"
        for d in (self.repo, self.tools, self.bin, stub_dir):
            d.mkdir()
        (stub_dir / "uv").write_text(_UV_STUB)
        (stub_dir / "uv").chmod(0o755)
        # The tool bin dir precedes the inherited PATH, as ~/.local/bin does on a box.
        self.env = {
            **git_env,
            "PATH": os.pathsep.join([str(stub_dir), str(self.bin), os.environ["PATH"]]),
            "STUB_UV_LOG": str(self.uv_log),
            "STUB_TOOL_DIR": str(self.tools),
            "STUB_BIN_DIR": str(self.bin),
        }
        files = {
            "pyproject.toml": _PYPROJECT,
            "tools/box_install.py": _TOOL.read_text(),
            "src/project_init/__init__.py": "__version__ = '0'\n",
            "src/project_init/cli.py": "def main():\n    return 0\n",
            "templates/base/dot_agents/hooks/prod_guard.py": "# is_symlink\n",
            "templates/base/hook.sh": "#!/usr/bin/env bash\necho hi\n",
            ".gitattributes": (_REPO_ROOT / ".gitattributes").read_text(),
            "schemas/s.json": "{}\n",
            "README.md": "not shipped\n",
        }
        for rel, text in files.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text)
        (self.repo / "templates/base/hook.sh").chmod(0o755)  # a 100755 blob, as a hook is
        fmt = f"--object-format={object_format}"
        _git(tmp, "init", "-q", "--bare", "-b", "main", fmt, "origin.git")
        _git(self.repo, "init", "-q", "-b", "main", fmt)
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "init")
        _git(self.repo, "remote", "add", "origin", str(tmp / "origin.git"))
        _git(self.repo, "push", "-q", "-u", "origin", "main")

    def run(self, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.repo / "tools" / "box_install.py"), *args],
            capture_output=True,
            text=True,
            env={**self.env, **extra},
            cwd=self.tmp,
        )

    def uv_calls(self) -> list[str]:
        return self.uv_log.read_text().splitlines() if self.uv_log.exists() else []

    def build_layout(self, dest: Path, *, at: Path | None = None) -> Path:
        """Lay out what `uv tool install` produces for this repo's HEAD, in *dest*.

        *at* is where the env will finally live (its interpreter reports paths
        there).
        """
        at = at or dest
        site_rel, scripts_rel = Path("lib/python3.13/site-packages"), Path("bin")
        site, scripts = dest / site_rel, dest / scripts_rel
        mapping = {"src/project_init/": "project_init/", "templates/": "project_init/templates/"}
        mapping["schemas/"] = "project_init/schemas/"
        for rel in _git(self.repo, "ls-files").splitlines():
            for src, dst in mapping.items():
                if rel.startswith(src):
                    out = site / (dst + rel[len(src) :])
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(self.repo / rel, out)  # with its mode, as uv installs it
        (site / "project_init" / "__pycache__").mkdir()
        (site / "project_init" / "__pycache__" / "cli.cpython-313.pyc").write_bytes(b"\0")
        dist = site / "project_init-0.0.1.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(_METADATA)
        (dist / "entry_points.txt").write_text(_ENTRY_POINTS)
        # uv's RECORD: every installed file relative to site-packages, the script outside it.
        owned = sorted(p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file())
        rows = [*owned, f"{dist.name}/RECORD", f"../../../{scripts_rel.as_posix()}/project-init"]
        (dist / "RECORD").write_text("".join(f"{row},,\n" for row in rows))
        scripts.mkdir(parents=True)
        (scripts / "project-init").write_text("#!/bin/sh\n")
        (scripts / "project-init").chmod(0o755)
        python = scripts / "python"
        paths = {"purelib": str(at / site_rel), "scripts": str(at / scripts_rel)}
        python.write_text(f"#!/bin/sh\nprintf '%s\\n' '{json.dumps(paths)}'\n")
        python.chmod(0o755)
        (dest / ".stub-python").write_text(str(at / python.relative_to(dest)))
        (dest / "uv-receipt.toml").write_text(
            "[tool]\n"
            f'requirements = [{{ name = "project-init", directory = "{self.repo.resolve()}" }}]\n'
            "entrypoints = [\n"
            f'    {{ name = "project-init", install-path = "{self.bin / "project-init"}", '
            'from = "project-init" },\n]\n'
        )
        return scripts_rel

    def install_layout(self) -> Path:
        scripts_rel = self.build_layout(self.env_dir)
        (self.bin / "project-init").symlink_to(self.env_dir / scripts_rel / "project-init")
        return self.env_dir / "lib/python3.13/site-packages" / "project_init"

    def commit_pyproject(self, old: str, new: str) -> None:
        path = self.repo / "pyproject.toml"
        assert old in path.read_text()
        path.write_text(path.read_text().replace(old, new))
        _git(self.repo, "commit", "-q", "-am", "pyproject only")


def _make_box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, object_format: str) -> Box:
    # Hermetic git: no global hooks, signing or identity leak into the temp repos.
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = t\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n"
    )
    git_env = {
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(tmp_path),
    }
    for key, value in git_env.items():
        monkeypatch.setenv(key, value)
    return Box(tmp_path, git_env, object_format)


@pytest.fixture
def box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Box:
    return _make_box(tmp_path, monkeypatch, "sha1")


def _no_install(box: Box) -> None:
    assert not [c for c in box.uv_calls() if c.startswith("tool install")], box.uv_calls()


# ── dry run ──────────────────────────────────────────────────────────────────


def test_dry_run_on_clean_synced_main_prints_the_plan_and_exits_0(box: Box):
    result = box.run()
    assert result.returncode == 0, result.stdout + result.stderr
    head = _git(box.repo, "rev-parse", "HEAD")
    out = result.stdout
    assert "DRY RUN" in out
    assert f"source    {box.repo.resolve()}" in out
    assert head in out
    assert str(box.env_dir) in out and str(box.bin / "project-init") in out
    assert f"tool install --reinstall {box.repo.resolve()}" in out
    assert "--apply would proceed" in out
    _no_install(box)
    assert not box.env_dir.exists()


def test_dry_run_exits_1_when_apply_would_refuse(box: Box):
    _git(box.repo, "switch", "-q", "-c", "feat/x")
    result = box.run()
    assert result.returncode == 1
    assert "--apply would refuse" in result.stdout and "not main" in result.stdout
    _no_install(box)


def test_dry_run_exits_0_when_the_session_is_the_only_reason(box: Box):
    # deploy checks for a session itself, and dry runs are expected inside one.
    result = box.run(CLAUDECODE="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--apply would refuse" in result.stdout
    assert "inside a Claude Code session" in result.stdout
    _no_install(box)


def test_dry_run_exits_1_when_a_session_comes_with_another_reason(box: Box):
    _git(box.repo, "switch", "-q", "-c", "feat/x")
    result = box.run(CLAUDECODE="1")
    assert result.returncode == 1
    assert "inside a Claude Code session" in result.stdout and "not main" in result.stdout


def test_dirty_listing_keeps_the_porcelain_status_column(box: Box):
    (box.repo / "README.md").write_text("edited\n")
    result = box.run("--apply")
    assert result.returncode == 1
    # ` M README.md`, not `M README.md`: the first line keeps its leading space.
    assert "unreviewed:\n       M README.md" in result.stderr, result.stderr
    _no_install(box)


def test_unknown_flag_is_a_usage_error(box: Box):
    assert box.run("--bogus").returncode == 2
    assert box.run("--apply", "--check").returncode == 2
    _no_install(box)


# ── --apply gate ─────────────────────────────────────────────────────────────


def test_apply_refuses_off_main(box: Box):
    _git(box.repo, "switch", "-q", "-c", "feat/x")
    result = box.run("--apply")
    assert result.returncode == 1
    assert "on 'feat/x', not main" in result.stderr
    _no_install(box)


def test_apply_refuses_a_dirty_tree(box: Box):
    (box.repo / "templates" / "base" / "stray.txt").write_text("unreviewed\n")
    result = box.run("--apply")
    assert result.returncode == 1
    assert "uncommitted changes" in result.stderr and "stray.txt" in result.stderr
    _no_install(box)


# ls-files -v label -> the update-index flags that set it. Set one call per flag:
# update-index applies only one of the two when both are given in one call.
_HIDING = {
    "skip-worktree": ("--skip-worktree",),
    "assume-unchanged": ("--assume-unchanged",),
    "skip-worktree, assume-unchanged": ("--skip-worktree", "--assume-unchanged"),
}


@pytest.mark.parametrize("label", sorted(_HIDING))
def test_apply_refuses_an_edit_git_status_skips(box: Box, label: str):
    """status reads clean, yet uv would build and install the edited bytes (#1047 review)."""
    for flag in _HIDING[label]:
        _git(box.repo, "update-index", flag, "templates/base/hook.sh")
    (box.repo / "templates/base/hook.sh").write_text("#!/usr/bin/env bash\necho unreviewed\n")
    assert _git(box.repo, "status", "--porcelain", "--untracked-files=all") == ""
    shown = f"one call per flag:\n      {label}: templates/base/hook.sh"
    result = box.run("--apply")
    assert result.returncode == 1
    assert "files git status skips would be installed unreviewed" in result.stderr
    assert shown in result.stderr, result.stderr
    _no_install(box)
    dry = box.run()
    assert dry.returncode == 1
    assert "--apply would refuse" in dry.stdout and shown in dry.stdout, dry.stdout
    # The commands the refusal names clear the flags, and status then sees the edit.
    for flag in _HIDING[label]:
        _git(box.repo, "update-index", f"--no-{flag[2:]}", "--", "templates/base/hook.sh")
    after = box.run("--apply")
    assert "git status skips" not in after.stderr and "M templates/base/hook.sh" in after.stderr
    _no_install(box)


# ── PR #1047 review round 4 / #1060: a local clean filter can hide an edit ──


def _clean_filter(box: Box, name: str, path: str) -> None:
    """Configure a local clean filter that maps any edit to *path* back to its blob at HEAD.

    `git status`/`diff` run a clean filter over the working-tree copy only to
    compare it with the index — the filter's output never touches the file on
    disk, so the edited bytes stay there for uv to build (project-init#1060).
    """
    original = box.tmp / f"{name}.orig"
    original.write_bytes((box.repo / path).read_bytes())
    script = box.tmp / f"{name}.sh"
    script.write_text(f"#!/usr/bin/env bash\ncat {original}\n")
    script.chmod(0o755)
    _git(box.repo, "config", f"filter.{name}.clean", str(script))
    _git(box.repo, "config", f"filter.{name}.smudge", "cat")
    attrs = box.repo / ".git" / "info" / "attributes"
    attrs.write_text((attrs.read_text() if attrs.exists() else "") + f"{path} filter={name}\n")


def test_apply_refuses_a_clean_filter_hidden_edit_to_a_packaged_file(box: Box):
    """A clean filter smudges the edit back to HEAD for status/diff, so only a raw byte
    compare — bypassing filters — catches it before uv builds the edited bytes (#1060).

    The edit keeps the file's byte length: git's stat-based fast path marks a
    path modified on a bare size mismatch without ever running the clean
    filter, so only a same-length edit reaches the filtered comparison this
    attack (and this check) both depend on.
    """
    _clean_filter(box, "hide", "templates/base/hook.sh")
    original = (box.repo / "templates/base/hook.sh").read_text()
    edited = original.replace("echo hi\n", "echo rm\n")
    assert len(edited) == len(original) and edited != original
    (box.repo / "templates/base/hook.sh").write_text(edited)
    assert _git(box.repo, "status", "--porcelain", "--untracked-files=all") == ""
    assert _git(box.repo, "ls-files", "-v", "--", "templates/base/hook.sh").startswith("H")
    result = box.run("--apply")
    assert result.returncode == 1
    assert "on-disk bytes do not match" in result.stderr
    assert "templates/base/hook.sh" in result.stderr, result.stderr
    _no_install(box)
    dry = box.run()
    assert dry.returncode == 1 and "templates/base/hook.sh" in dry.stdout, dry.stdout


def test_apply_refuses_a_clean_filter_hidden_edit_to_pyproject(box: Box):
    """The same smuggle on pyproject.toml itself: force-include, dependencies or entry
    points can be rewritten there, and nothing but pyproject.toml's own raw bytes catch
    it — the layout used to pick packaged paths is read from HEAD, never disk (#1060)."""
    _clean_filter(box, "hidepy", "pyproject.toml")
    original = (box.repo / "pyproject.toml").read_text()
    # Same byte length (see the packaged-file test above for why that matters):
    # the force-include destination is rewritten in place.
    edited = original.replace(
        '"schemas" = "project_init/schemas"\n', '"schemas" = "project_init/SCHEMAS"\n'
    )
    assert len(edited) == len(original) and edited != original
    (box.repo / "pyproject.toml").write_text(edited)
    assert _git(box.repo, "status", "--porcelain", "--untracked-files=all") == ""
    assert _git(box.repo, "ls-files", "-v", "--", "pyproject.toml").startswith("H")
    result = box.run("--apply")
    assert result.returncode == 1
    assert "on-disk bytes do not match" in result.stderr
    assert "pyproject.toml" in result.stderr, result.stderr
    _no_install(box)


def _clean_and_smudge_filter(box: Box, name: str, path: str, *, clean: str, smudge: str) -> None:
    """A clean filter that maps *path* back to *clean* for status/diff, paired with a
    smudge filter that plays *smudge* back for a checkout — e.g. ``git archive``, the
    trusted side of stage 2 before #1064 (Codex P1, reproduced on git 2.43: a smudge
    driver a repo's own `.gitattributes` configures runs during `archive` too, so its
    output — not the blob — is what confirmation compared the edit against)."""
    clean_src = box.tmp / f"{name}.clean.src"
    clean_src.write_bytes(clean.encode())
    clean_sh = box.tmp / f"{name}.clean.sh"
    clean_sh.write_text(f"#!/usr/bin/env bash\ncat {clean_src}\n")
    clean_sh.chmod(0o755)
    smudge_src = box.tmp / f"{name}.smudge.src"
    smudge_src.write_bytes(smudge.encode())
    smudge_sh = box.tmp / f"{name}.smudge.sh"
    smudge_sh.write_text(f"#!/usr/bin/env bash\ncat {smudge_src}\n")
    smudge_sh.chmod(0o755)
    _git(box.repo, "config", f"filter.{name}.clean", str(clean_sh))
    _git(box.repo, "config", f"filter.{name}.smudge", str(smudge_sh))
    attrs = box.repo / ".git" / "info" / "attributes"
    attrs.write_text((attrs.read_text() if attrs.exists() else "") + f"{path} filter={name}\n")


def test_apply_refuses_an_edit_a_clean_and_smudge_pair_hides(box: Box):
    """A clean filter alone (the tests above) only defeats git status/diff. Pair it with
    a smudge filter that reproduces the edited bytes, and a stage-2 confirmation reading
    a checkout (`git archive`) — not the object store — sees the edit as 'trusted' too,
    since archive runs the same smudge driver a real checkout would (#1064, Codex P1)."""
    target = "templates/base/hook.sh"
    original = (box.repo / target).read_text()
    edited = original.replace("echo hi\n", "echo rm\n")
    assert len(edited) == len(original) and edited != original
    _clean_and_smudge_filter(box, "evil", target, clean=original, smudge=edited)
    (box.repo / target).write_text(edited)
    assert _git(box.repo, "status", "--porcelain", "--untracked-files=all") == ""
    assert _git(box.repo, "ls-files", "-v", "--", target).startswith("H")
    result = box.run("--apply")
    assert result.returncode == 1
    assert "on-disk bytes do not match" in result.stderr
    assert target in result.stderr, result.stderr
    _no_install(box)


def test_apply_refuses_a_crlf_variant_of_an_eol_lf_packaged_file(box: Box):
    """A CRLF variant of an `eol=lf`-pinned file (`*.sh` here) is not the checkout
    allowance the CRLF form exists for — a real checkout never produces it — so it
    must still refuse, matching modified_paths()'s eol=lf gate (#1064 review). No
    clean filter is needed to show this: CRLF injection changes the file's length,
    which a clean filter cannot survive (see the two tests above), and apply_problems()
    reads the raw disk bytes directly regardless of what git status reports."""
    target = "templates/base/hook.sh"
    original = (box.repo / target).read_bytes()
    (box.repo / target).write_bytes(original.replace(b"\n", b"\r\n"))
    result = box.run("--apply")
    assert result.returncode == 1
    assert "on-disk bytes do not match" in result.stderr
    assert target in result.stderr, result.stderr
    _no_install(box)


def test_apply_refuses_crlf_from_a_local_eol_override(box: Box):
    """Codex on #1068: `.git/info/attributes` overriding the committed `*.sh eol=lf`
    with `eol=crlf` makes a checkout write CRLF while git status stays clean. The
    eol policy must come from the committed tree, not from a local attribute file."""
    target = "templates/base/hook.sh"
    (box.repo / ".git" / "info").mkdir(exist_ok=True)
    (box.repo / ".git" / "info" / "attributes").write_text("*.sh eol=crlf\n")
    (box.repo / target).unlink()
    _git(box.repo, "checkout", "--", target)
    assert b"\r\n" in (box.repo / target).read_bytes()
    assert _git(box.repo, "status", "--porcelain", "--untracked-files=all") == ""
    result = box.run("--apply")
    assert result.returncode == 1
    assert "on-disk bytes do not match" in result.stderr
    assert target in result.stderr, result.stderr
    _no_install(box)


# Every place an ignore rule can live. Each hides the file from git status.
_IGNORE_FILES = (".gitignore", "templates/.gitignore", ".git/info/exclude")
_CLEAN = "git clean -fdX -- src/project_init templates schemas"


def _ignore(box: Box, rules: str, where: str = ".gitignore") -> None:
    path = box.repo / where
    path.write_text(path.read_text() + rules if path.exists() else rules)
    if not where.startswith(".git/"):
        _git(box.repo, "add", where)
        _git(box.repo, "commit", "-q", "-m", "ignore")
        _git(box.repo, "push", "-q")


@pytest.mark.parametrize("where", _IGNORE_FILES)
def test_apply_refuses_an_ignored_file_the_wheel_packages(box: Box, where: str):
    """status reads clean, yet force-include ships the ignored file (#1047 review)."""
    _ignore(box, "__pycache__/\n", ".git/info/exclude")
    _ignore(box, "*.local\n", where)
    (box.repo / "templates/base/extra.local").write_text("unreviewed\n")
    # hatchling never packages a bytecode cache, so this one is no reason to refuse.
    (box.repo / "src/project_init/__pycache__").mkdir()
    (box.repo / "src/project_init/__pycache__/cli.cpython-313.pyc").write_bytes(b"\0")
    assert _git(box.repo, "status", "--porcelain", "--untracked-files=all") == ""
    result = box.run("--apply")
    assert result.returncode == 1
    assert "ignored files the wheel packages" in result.stderr
    assert "\n      templates/base/extra.local\n" in result.stderr, result.stderr
    assert "__pycache__" not in result.stderr
    _no_install(box)
    dry = box.run()
    assert dry.returncode == 1 and "templates/base/extra.local" in dry.stdout, dry.stdout
    # The command the refusal names removes it, and the dry run then proceeds.
    assert f"`{_CLEAN}`" in dry.stdout
    subprocess.run(_CLEAN.split(), cwd=box.repo, check=True, capture_output=True)
    after = box.run()
    assert after.returncode == 0 and "--apply would proceed" in after.stdout, after.stdout


def test_ignored_file_check_reads_the_packaged_paths_from_pyproject(box: Box):
    _ignore(box, "*.local\n")
    (box.repo / "assets").mkdir()
    (box.repo / "assets/extra.local").write_text("unreviewed\n")
    assert box.run().returncode == 0  # not packaged, so not a reason to refuse
    box.commit_pyproject('"schemas" = ', '"assets" = "project_init/assets"\n"schemas" = ')
    _git(box.repo, "push", "-q")
    dry = box.run()
    assert dry.returncode == 1 and "\n      assets/extra.local\n" in dry.stdout, dry.stdout


def test_apply_refuses_when_not_in_sync_with_origin(box: Box):
    (box.repo / "README.md").write_text("local only\n")
    _git(box.repo, "commit", "-q", "-am", "unpushed")
    result = box.run("--apply")
    assert result.returncode == 1
    assert "not in sync with origin/main (ahead 1, behind 0)" in result.stderr
    _no_install(box)


def test_apply_refuses_inside_a_claude_session(box: Box):
    result = box.run("--apply", CLAUDECODE="1")
    assert result.returncode == 1
    assert "from a terminal" in result.stderr
    _no_install(box)


def test_apply_from_clean_synced_main_installs_then_verifies(box: Box):
    layout = box.tmp / "layout"
    box.build_layout(layout, at=box.env_dir)
    (box.bin / "project-init").symlink_to(box.env_dir / "bin" / "project-init")
    box.env_dir.mkdir()
    result = box.run("--apply", STUB_LAYOUT=str(layout))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"tool install --reinstall {box.repo.resolve()}" in box.uv_calls()
    assert "installed and verified" in result.stdout


# ── --check ──────────────────────────────────────────────────────────────────


def test_check_passes_on_a_matching_install(box: Box):
    box.install_layout()
    result = box.run("--check")
    assert result.returncode == 0, result.stderr
    assert "(5 files)" in result.stdout
    _no_install(box)


def test_check_names_a_modified_installed_file(box: Box):
    pkg = box.install_layout()
    (pkg / "templates" / "base" / "dot_agents" / "hooks" / "prod_guard.py").write_text("# old\n")
    result = box.run("--check")
    assert result.returncode == 1
    assert (
        "modified: project_init/templates/base/dot_agents/hooks/prod_guard.py "
        "(tree: templates/base/dot_agents/hooks/prod_guard.py)"
    ) in result.stderr
    assert result.stderr.count("    - ") == 1, result.stderr
    _no_install(box)


def test_check_catches_crlf_that_git_attributes_would_normalise(box: Box):
    # The repo's `*.sh text eol=lf` would make hash-object's filters turn this
    # CRLF copy back into the committed blob; the installed bytes must be hashed as is.
    pkg = box.install_layout()
    hook = pkg / "templates" / "base" / "hook.sh"
    hook.write_bytes(hook.read_bytes().replace(b"\n", b"\r\n"))
    result = box.run("--check")
    assert result.returncode == 1
    assert "modified: project_init/templates/base/hook.sh" in result.stderr


def test_check_passes_in_a_sha256_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Blob ids come from the repo's own object format, never a hard-coded hash.
    probe = subprocess.run(
        ["git", "init", "-q", "--object-format=sha256", str(tmp_path / "probe")],
        capture_output=True,
    )
    if probe.returncode != 0:
        pytest.skip("this git cannot create a SHA-256 repository")
    box = _make_box(tmp_path, monkeypatch, "sha256")
    box.install_layout()
    result = box.run("--check")
    assert result.returncode == 0, result.stderr
    assert "(5 files)" in result.stdout


def test_check_names_missing_and_extra_files(box: Box):
    pkg = box.install_layout()
    (pkg / "cli.py").unlink()
    (pkg / "templates" / "leftover.txt").write_text("removed from the tree\n")
    result = box.run("--check")
    assert result.returncode == 1
    assert "missing: project_init/cli.py (tree: src/project_init/cli.py)" in result.stderr
    assert "not in tree: project_init/templates/leftover.txt" in result.stderr


def test_check_flags_a_tree_change_the_install_lacks(box: Box):
    box.install_layout()
    (box.repo / "src" / "project_init" / "cli.py").write_text("def main():\n    return 1\n")
    _git(box.repo, "commit", "-q", "-am", "change")
    result = box.run("--check")
    assert result.returncode == 1
    assert "modified: project_init/cli.py" in result.stderr


def test_check_flags_an_install_from_another_source(box: Box):
    box.install_layout()
    receipt = box.env_dir / "uv-receipt.toml"
    receipt.write_text(receipt.read_text().replace(str(box.repo.resolve()), "/elsewhere"))
    result = box.run("--check")
    assert result.returncode == 1
    assert "source: installed from /elsewhere" in result.stderr


def test_check_flags_an_entrypoint_that_points_elsewhere(box: Box):
    box.install_layout()
    link = box.bin / "project-init"
    link.unlink()
    link.symlink_to(box.tmp / "stale-clone" / "project-init")
    result = box.run("--check")
    assert result.returncode == 1
    assert "entrypoint:" in result.stderr


def test_check_on_no_install_fails(box: Box):
    result = box.run("--check")
    assert result.returncode == 1
    assert "not installed" in result.stderr


# ── the real uv layout ───────────────────────────────────────────────────────


@pytest.mark.skipif(find_uv() is None, reason="uv not available")
def test_check_against_a_real_uv_tool_install(box: Box):
    """Install the temp repo with the real uv into temp dirs; --check must match, then catch a tamper."""
    uv = find_uv()
    assert uv
    # Reuse the real uv cache so the build needs no network when warm.
    cache = subprocess.run(
        [uv, "cache", "dir"], capture_output=True, text=True, env={**os.environ, "HOME": _REAL_HOME}
    ).stdout.strip()
    real = {
        **box.env,
        "UV_CACHE_DIR": cache,
        "PATH": os.pathsep.join([str(box.bin), str(Path(uv).parent), os.environ["PATH"]]),
        "UV_TOOL_DIR": str(box.tools),
        "UV_TOOL_BIN_DIR": str(box.bin),
        "UV_PYTHON": sys.executable,
    }
    installed = subprocess.run(
        [uv, "tool", "install", "--reinstall", str(box.repo)],
        capture_output=True,
        text=True,
        env=real,
        timeout=300,
    )
    if installed.returncode != 0:
        pytest.skip(f"uv tool install unavailable here: {installed.stderr[-300:]}")
    run = [sys.executable, str(box.repo / "tools" / "box_install.py"), "--check"]
    ok = subprocess.run(run, capture_output=True, text=True, env=real)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "(5 files)" in ok.stdout
    # The metadata the stub layouts carry is what hatchling really writes.
    fields = ("Name:", "Version:", "Requires-Python:", "Provides-Extra:", "Requires-Dist:")
    real_meta = next(box.tools.glob("project-init/lib/python3*/site-packages/*.dist-info/METADATA"))
    real_lines = {ln for ln in real_meta.read_text().splitlines() if ln.startswith(fields)}
    assert real_lines == {ln for ln in _METADATA.splitlines() if ln.startswith(fields)}
    # uv keeps a 100755 blob executable and writes a RECORD, as the stub layouts do.
    site = real_meta.parent.parent
    assert os.access(site / "project_init/templates/base/hook.sh", os.X_OK)
    assert "project_init/templates/base/hook.sh," in (real_meta.parent / "RECORD").read_text()
    guard = next(
        box.tools.glob(
            "project-init/lib/python3*/site-packages/project_init/templates/base/dot_agents/hooks/prod_guard.py"
        )
    )
    guard.write_text("# tampered\n")
    bad = subprocess.run(run, capture_output=True, text=True, env=real)
    assert bad.returncode == 1
    assert "modified: project_init/templates/base/dot_agents/hooks/prod_guard.py" in bad.stderr


# ── review round (#1047): metadata, platform paths, PATH, recipe ─────────────


def test_check_flags_a_dependency_change_in_pyproject_only(box: Box):
    box.install_layout()
    box.commit_pyproject('dependencies = ["tomli', 'dependencies = ["rich>=13.7", "tomli')
    result = box.run("--check")
    assert result.returncode == 1
    assert "metadata: dependency rich>=13.7 is in pyproject, not installed" in result.stderr
    assert result.stderr.count("metadata:") == 1, result.stderr


def test_check_flags_a_scripts_change_in_pyproject_only(box: Box):
    box.install_layout()
    box.commit_pyproject('"project_init.cli:main"', '"project_init.cli:run"')
    result = box.run("--check")
    assert result.returncode == 1
    assert (
        "metadata: console script project-init = project_init.cli:run is in pyproject, not installed"
    ) in result.stderr
    assert (
        "metadata: console script project-init = project_init.cli:main is installed, not in pyproject"
    ) in result.stderr


def test_check_flags_a_version_change_in_pyproject_only(box: Box):
    box.install_layout()
    box.commit_pyproject('version = "0.0.1"', 'version = "0.0.2"')
    result = box.run("--check")
    assert result.returncode == 1
    assert "metadata: Version installed 0.0.1, pyproject says 0.0.2" in result.stderr
    assert result.stderr.count("metadata:") == 1, result.stderr


def test_check_names_a_shadowing_executable_on_path(box: Box):
    box.install_layout()
    shadow = box.tmp / "shadow"
    shadow.mkdir()
    (shadow / "project-init").write_text("#!/bin/sh\necho a stale copy\n")
    (shadow / "project-init").chmod(0o755)
    result = box.run("--check", PATH=f"{shadow}{os.pathsep}{box.env['PATH']}")
    assert result.returncode == 1
    assert f"PATH: project-init runs {shadow / 'project-init'}, which shadows" in result.stderr


def _venv_with_the_tool(box: Box, venv: Path) -> Path:
    uv = find_uv()
    assert uv
    subprocess.run([uv, "venv", "-q", "--python", sys.executable, str(venv)], check=True)
    own = venv / "bin"
    (own / "project-init").write_text("#!/bin/sh\necho a dev entrypoint\n")
    (own / "project-init").chmod(0o755)
    return own


def _uv_run_check(box: Box, cwd: Path, *, nested: bool = False, **env: str):
    """`--check` the way the recipe runs it: under the real `uv run --no-project`."""
    uv = find_uv()
    assert uv
    run = [uv, "run", "--no-python-downloads", "--no-project", "--python", ">=3.11"]
    return subprocess.run(
        [
            *run,
            *(run if nested else []),
            "python",
            str(box.repo / "tools/box_install.py"),
            "--check",
        ],
        capture_output=True,
        text=True,
        env={**box.env, **env},
        cwd=cwd,
        timeout=120,
    )


@pytest.mark.skipif(find_uv() is None, reason="uv not available")
@pytest.mark.parametrize("nested", [False, True], ids=["uv-run", "uv-run-in-uv-run"])
def test_check_skips_the_venv_uv_run_puts_first_on_path(box: Box, nested: bool):
    """`uv run` finds the cwd's .venv, never activated, and prepends its scripts dir to PATH."""
    work = box.tmp / "work"
    _venv_with_the_tool(box, work / ".venv")
    box.install_layout()
    result = _uv_run_check(box, work, nested=nested)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(find_uv() is None, reason="uv not available")
def test_check_names_the_tool_in_a_venv_the_caller_activated(box: Box):
    """An activated venv was first on the shell's PATH before `uv run` prepended it again."""
    active = _venv_with_the_tool(box, box.tmp / "active")
    box.install_layout()
    path = f"{active}{os.pathsep}{box.env['PATH']}"
    result = _uv_run_check(box, box.tmp, VIRTUAL_ENV=str(active.parent), PATH=path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"PATH: project-init runs {active / 'project-init'}, which shadows" in result.stderr


# ── review round 3 (#1047): executable bits, files a past build owned ─────────


@pytest.mark.parametrize(
    ("rel", "mode", "want"),
    [
        ("templates/base/hook.sh", 0o644, "installed 644, tree 100755"),
        ("src/project_init/cli.py", 0o755, "installed 755, tree 100644"),
    ],
    ids=["exec-bit-dropped", "exec-bit-added"],
)
def test_check_flags_an_installed_file_whose_exec_bit_differs(
    box: Box, rel: str, mode: int, want: str
):
    """The scaffolder copies a template's exec bit, so a blob match alone is not a match."""
    pkg = box.install_layout()
    installed = pkg / rel.replace("src/project_init/", "")
    installed.chmod(mode)
    result = box.run("--check")
    assert result.returncode == 1, result.stdout
    dest = installed.relative_to(pkg.parent).as_posix()
    assert result.stderr.count("    - ") == 1, result.stderr
    assert f"mode: {dest} {want} (tree: {rel})" in result.stderr


def test_check_flags_an_exec_bit_only_head_changed(box: Box):
    box.install_layout()
    _git(box.repo, "update-index", "--chmod=-x", "templates/base/hook.sh")
    _git(box.repo, "commit", "-q", "-m", "hook.sh is not executable")
    result = box.run("--check")
    assert result.returncode == 1
    assert (
        "mode: project_init/templates/base/hook.sh installed 755, tree 100644"
        " (tree: templates/base/hook.sh)"
    ) in result.stderr


def test_check_scans_what_the_installed_record_owns(box: Box):
    """A build from before HEAD dropped a mapping left files HEAD's layout never visits."""
    pkg = box.install_layout()
    site = pkg.parent
    (site / "retired_pkg").mkdir()
    (site / "retired_pkg" / "old.py").write_text("stale\n")
    (site / "retired.py").write_text("stale\n")
    record = site / "project_init-0.0.1.dist-info" / "RECORD"
    record.write_text(record.read_text() + "retired_pkg/old.py,,\nretired.py,,\n")
    result = box.run("--check")
    assert result.returncode == 1
    assert "not in tree: retired_pkg/old.py" in result.stderr
    assert "not in tree: retired.py" in result.stderr
    assert result.stderr.count("    - ") == 2, result.stderr


def test_check_flags_an_install_without_a_record(box: Box):
    """No RECORD, no list of what the build installed: that is drift, not a pass."""
    pkg = box.install_layout()
    (pkg.parent / "project_init-0.0.1.dist-info" / "RECORD").unlink()
    result = box.run("--check")
    assert result.returncode == 1
    assert "record: project_init-0.0.1.dist-info has no RECORD" in result.stderr


_DIST = "project_init-0.0.1.dist-info"
_UNCOMPARED = ", so the installed metadata is not compared"


@pytest.mark.parametrize(
    ("name", "damage", "line"),
    [
        ("METADATA", None, f"{_DIST}/METADATA cannot be read (No such file or directory)"),
        ("METADATA", b"\xff\xfe", f"{_DIST}/METADATA cannot be read (not UTF-8)"),
        ("entry_points.txt", b"\xff", f"{_DIST}/entry_points.txt cannot be read (not UTF-8)"),
        ("RECORD", b"\xff", f"{_DIST}/RECORD cannot be read (not UTF-8)"),
    ],
    ids=["no-metadata", "binary-metadata", "binary-entry-points", "binary-record"],
)
def test_check_reports_an_unreadable_dist_info_file_and_carries_on(
    box: Box, name: str, damage: bytes | None, line: str
):
    """A missing or unreadable dist-info file is one drift line, never a traceback (po#318)."""
    pkg = box.install_layout()
    path = pkg.parent / _DIST / name
    if damage is None:
        path.unlink()
    else:
        path.write_bytes(damage)
    (pkg / "cli.py").write_text("tampered\n")  # a later comparison must still run
    result = box.run("--check")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr, result.stderr
    items = [row[6:] for row in result.stderr.splitlines() if row.startswith("    - ")]
    first = (
        f"record: {line}, so what it installed is unknown"
        if name == "RECORD"
        else f"metadata: {line}{_UNCOMPARED}"
    )
    assert items == [first, "modified: project_init/cli.py (tree: src/project_init/cli.py)"]


@pytest.mark.skipif(shutil.which("just") is None, reason="just not installed")
def test_recipe_never_downloads_a_python(tmp_path: Path):
    """`uv run` honours .python-version and would fetch a missing interpreter."""
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "uv").write_text('#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$UV_LOG"\n')
    (stub / "uv").chmod(0o755)
    log = tmp_path / "uv.log"
    env = {**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}", "UV_LOG": str(log)}
    env.pop("XDG_RUNTIME_DIR", None)
    subprocess.run(
        ["just", "--justfile", str(_REPO_ROOT / "justfile"), "install", "--check"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert log.read_text().split()[:2] == ["run", "--no-python-downloads"], log.read_text()


@pytest.mark.skipif(shutil.which("just") is None, reason="just not installed")
def test_recipe_asks_uv_for_a_python_with_tomllib(tmp_path: Path):
    """Outside the project env no requires-python applies, so the recipe states the script's floor."""
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "uv").write_text('#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$UV_LOG"\n')
    (stub / "uv").chmod(0o755)
    log = tmp_path / "uv.log"
    env = {**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}", "UV_LOG": str(log)}
    subprocess.run(
        ["just", "--justfile", str(_REPO_ROOT / "justfile"), "install", "--check"],
        capture_output=True,
        env=env,
        check=True,
    )
    argv = log.read_text().split()
    assert "--python" in argv, argv
    assert argv[argv.index("--python") + 1] == ">=3.11", argv


# ── review round 2 (#1047): read-only recipe, CRLF checkouts ─────────────────


@pytest.mark.skipif(shutil.which("just") is None or find_uv() is None, reason="just or uv missing")
@pytest.mark.parametrize(
    ("args", "ran"),
    [((), "DRY RUN, nothing written"), (("--check",), "not installed:")],
    ids=["dry-run", "check"],
)
def test_recipe_creates_no_venv_and_needs_no_network(box: Box, args: tuple[str, ...], ran: str):
    """A fresh checkout, offline, with an empty uv cache: `uv run` must not sync the project."""
    uv = find_uv()
    assert uv
    env = {
        **box.env,
        "PATH": os.pathsep.join([str(Path(uv).parent), str(Path(sys.executable).parent)])
        + os.pathsep
        + os.environ["PATH"],
        "UV_OFFLINE": "1",
        "UV_CACHE_DIR": str(box.tmp / "empty-uv-cache"),
        "UV_TOOL_DIR": str(box.tools),
        "UV_TOOL_BIN_DIR": str(box.bin),
    }
    justfile = ["just", "--justfile", str(_REPO_ROOT / "justfile")]
    result = subprocess.run(
        [*justfile, "--working-directory", str(box.repo), "install", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert not (box.repo / ".venv").exists(), result.stdout + result.stderr
    assert ran in result.stdout + result.stderr, result.stdout + result.stderr


def _autocrlf_checkout(box: Box) -> None:
    """A CRLF checkout: `* text=auto` committed, core.autocrlf=true, a fresh checkout."""
    attributes = box.repo / ".gitattributes"
    attributes.write_text("* text=auto\n" + attributes.read_text())
    _git(box.repo, "commit", "-q", "-am", "text=auto")
    _git(box.repo, "config", "core.autocrlf", "true")
    for rel in _git(box.repo, "ls-files").splitlines():
        (box.repo / rel).unlink()
    _git(box.repo, "checkout", "--", ".")
    assert b"\r\n" in (box.repo / "src" / "project_init" / "cli.py").read_bytes()
    assert b"\r\n" not in (box.repo / "templates" / "base" / "hook.sh").read_bytes()


def test_check_passes_an_install_built_from_a_crlf_checkout(box: Box):
    # The wheel copies the working tree, so it is CRLF where the blobs are LF.
    _autocrlf_checkout(box)
    box.install_layout()
    result = box.run("--check")
    assert result.returncode == 0, result.stderr
    assert "(5 files)" in result.stdout


def test_check_still_catches_crlf_in_an_eol_lf_file_under_autocrlf(box: Box):
    # A checkout writes `*.sh text eol=lf` as LF even here, so CRLF is not its form.
    _autocrlf_checkout(box)
    pkg = box.install_layout()
    hook = pkg / "templates" / "base" / "hook.sh"
    hook.write_bytes(hook.read_bytes().replace(b"\n", b"\r\n"))
    result = box.run("--check")
    assert result.returncode == 1
    assert "modified: project_init/templates/base/hook.sh" in result.stderr
    assert result.stderr.count("    - ") == 1, result.stderr


def test_check_still_catches_an_edit_under_autocrlf(box: Box):
    _autocrlf_checkout(box)
    pkg = box.install_layout()
    (pkg / "cli.py").write_bytes(b"def main():\r\n    return 1\r\n")
    result = box.run("--check")
    assert result.returncode == 1
    assert "modified: project_init/cli.py (tree: src/project_init/cli.py)" in result.stderr
    assert result.stderr.count("    - ") == 1, result.stderr
