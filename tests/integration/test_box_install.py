"""PI-1046: `just install` (tools/box_install.py), the box install of a checkout as a uv tool.

Each test copies the tool into a throwaway git repo with a bare `origin`, so the
branch, dirty-tree and sync gates run against real git. `uv` is a PATH stub that
answers `uv tool dir` with a temp dir and logs every call, so nothing touches the
real uv tool dir. The smoke test at the end runs the real uv into a temp dir,
which is what proves the layout `--check` reads is uv's own.
"""

from __future__ import annotations

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
esac
exit 0
"""


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
        self.env = {
            **git_env,
            "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
            "STUB_UV_LOG": str(self.uv_log),
            "STUB_TOOL_DIR": str(self.tools),
            "STUB_BIN_DIR": str(self.bin),
        }
        files = {
            "pyproject.toml": (_REPO_ROOT / "pyproject.toml").read_text(),
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

    def build_layout(self, dest: Path) -> None:
        """Lay out what `uv tool install` produces for this repo's HEAD, as uv does."""
        site = dest / "lib" / "python3.13" / "site-packages"
        mapping = {"src/project_init/": "project_init/", "templates/": "project_init/templates/"}
        mapping["schemas/"] = "project_init/schemas/"
        for rel in _git(self.repo, "ls-files").splitlines():
            for src, dst in mapping.items():
                if rel.startswith(src):
                    out = site / (dst + rel[len(src) :])
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(self.repo / rel, out)
        (site / "project_init" / "__pycache__").mkdir()
        (site / "project_init" / "__pycache__" / "cli.cpython-313.pyc").write_bytes(b"\0")
        (dest / "bin").mkdir(parents=True)
        (dest / "bin" / "project-init").write_text("#!/bin/sh\n")
        (dest / "uv-receipt.toml").write_text(
            "[tool]\n"
            f'requirements = [{{ name = "project-init", directory = "{self.repo.resolve()}" }}]\n'
            "entrypoints = [\n"
            f'    {{ name = "project-init", install-path = "{self.bin / "project-init"}", '
            'from = "project-init" },\n]\n'
        )

    def install_layout(self) -> Path:
        self.build_layout(self.env_dir)
        (self.bin / "project-init").symlink_to(self.env_dir / "bin" / "project-init")
        return self.env_dir / "lib" / "python3.13" / "site-packages" / "project_init"


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
    box.build_layout(layout)
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
        "PATH": f"{Path(uv).parent}{os.pathsep}{os.environ['PATH']}",
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
    guard = next(
        box.tools.glob(
            "project-init/lib/python3*/site-packages/project_init/templates/base/dot_agents/hooks/prod_guard.py"
        )
    )
    guard.write_text("# tampered\n")
    bad = subprocess.run(run, capture_output=True, text=True, env=real)
    assert bad.returncode == 1
    assert "modified: project_init/templates/base/dot_agents/hooks/prod_guard.py" in bad.stderr
