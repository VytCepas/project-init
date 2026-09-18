"""#992: `--help` on any scaffolded `.agents/` script does no work.

An agent or a person sweeping a tree for usage information runs `<script>
--help` on everything in it. Before #992, that sweep wrote `CODE_MAP.md`,
installed git hooks, ran `uv sync`, installed cocoindex-code and graphify, ran
the multi-model installer (#1005), appended usage-log lines, and called `gh`
with `--help` as a PR number until it timed out.

The load-bearing assertion is that the tree and HOME are byte-identical
afterwards and no network or installer tool was invoked — not the help text.
Every script runs in its own copy of a maximal scaffold (every overlay that
ships scripts, `--no-plugin` so the hooks are in the tree too), under a
throwaway HOME, with no inherited environment, and with a PATH on which every
network and installer tool is a stub that only logs its argv.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.__main__ import main

# Tools a script could reach the network or install something with. Each is a
# stub that logs and fails, so even a regression cannot do real work.
_STUBBED = (
    "gh", "curl", "wget", "npm", "npx", "bun", "bunx", "pip", "pip3", "uv", "uvx",
    "pipx", "brew", "docker", "ollama", "ccr", "claude", "node", "graphify", "ccc",
    "cocoindex-code", "open", "osascript",
)  # fmt: skip
_REAL = (
    "bash", "sh", "git", "jq", "cat", "cp", "mv", "rm", "mkdir", "mktemp", "chmod",
    "date", "dirname", "basename", "grep", "sed", "awk", "tr", "head", "tail", "wc",
    "sort", "find", "env", "cmp", "tee", "xargs", "uname", "readlink", "stat", "cut",
    "ls", "touch", "sleep", "uniq", "diff", "od", "realpath", "id", "printf", "expr",
    "ln", "pwd", "true", "false", "test",
)  # fmt: skip

# Sourced by other scripts, never run: they have no usage to print, and a
# `--help` branch in a sourced file would read the CALLER's arguments. They
# still must not act when run directly.
_SOURCED = {"_usage_log.sh", "gh_host.sh"}

REPO_ROOT = Path(__file__).resolve().parents[2]


def _template_scripts() -> set[str]:
    """Every script any overlay can put under `.agents/`, read from templates/.

    Derived rather than listed, so a new template script — or a conditional one
    the fixture's flags do not render — fails the coverage check below instead
    of silently escaping the sweep (PR #1007 review: three conditional entry
    points did exactly that).
    """
    out = set()
    for p in (REPO_ROOT / "templates").glob("*/dot_agents/**/*"):
        # templates/<overlay>/dot_agents/<rest> renders to .agents/<rest>
        _overlay, _dot_agents, *rest = p.relative_to(REPO_ROOT / "templates").parts
        rendered = "/".join(rest).removesuffix(".tmpl")
        if p.is_file() and rendered.endswith((".sh", ".py")):
            out.add(rendered)
    return out


@pytest.fixture(scope="module")
def scaffolded(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("help") / "p"
    rc = main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            "obsidian-graphify",
            "--name",
            "probe",
            "--description",
            "probe",
            "--language",
            "python",
            "--memory",
            "obsidian-graphify-rag",
            "--lifecycle",
            "github",
            "--multi-model",
            "--governance",
            "--observability",
            "--no-plugin",
            # Conditional entry points: deploy scripts need a container deploy,
            # the guard adapter needs a non-Claude agent surface.
            "--delivery",
            "service",
            "--deploy",
            "cloud-run",
            "--agents",
            "claude,codex,antigravity,amp,junie",
        ]
    )
    assert rc == 0
    if not (target / ".git").exists():
        # install_hooks.sh needs a .git/hooks to write into, or its check is vacuous.
        subprocess.run(["git", "init", "-q", str(target)], check=True)
    return target


def _tree(root: Path) -> dict[str, object]:
    """Content AND permission bits: a `chmod` is a side effect too (PR #1007 review)."""
    out: dict[str, object] = {}
    for p in root.rglob("*"):
        key = p.relative_to(root).as_posix()
        mode = stat.S_IMODE(p.lstat().st_mode)
        if p.is_symlink():
            out[key] = ("link", os.readlink(p))
        elif p.is_file():
            out[key] = (mode, p.read_bytes())
        else:
            out[key] = ("dir", mode)
    return out


def _diff(before: dict[str, object], after: dict[str, object]) -> list[str]:
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


def _stub_path(root: Path, log: Path) -> Path:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    for name in _STUBBED:
        stub = bin_dir / name
        stub.write_text(f'#!/bin/sh\nprintf "%s\\n" "{name} $*" >>"{log}"\nexit 1\n')
        stub.chmod(0o755)
    (bin_dir / "python3").symlink_to(sys.executable)
    for name in _REAL:
        real = shutil.which(name)
        if real and not (bin_dir / name).exists():
            (bin_dir / name).symlink_to(real)
    return bin_dir


def _probe(scaffold: Path, rel: Path, work: Path) -> list[str]:
    """Run `<rel> --help` in a fresh copy of the scaffold; return the problems."""
    project, home, log = work / "p", work / "home", work / "stub.log"
    shutil.copytree(scaffold, project, symlinks=True)
    home.mkdir()
    bin_dir = _stub_path(work, log)
    before_p, before_h = _tree(project), _tree(home)
    interpreter = "python3" if rel.suffix == ".py" else "bash"
    try:
        proc = subprocess.run(
            [interpreter, str(project / rel), "--help"],
            cwd=project,
            env={
                "HOME": str(home),
                "PATH": str(bin_dir),
                "TMPDIR": str(work),
                "CLAUDE_PROJECT_DIR": str(project),
            },
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return ["still running after 30s"]

    problems = []
    if changed := _diff(before_p, _tree(project)):
        problems.append(f"changed the project: {changed[:5]}")
    if changed := _diff(before_h, _tree(home)):
        problems.append(f"changed HOME: {changed[:5]}")
    if log.exists():
        problems.append(f"invoked {log.read_text().splitlines()[:3]}")
    if rel.name not in _SOURCED:
        if proc.returncode != 0:
            problems.append(f"exit {proc.returncode}: {(proc.stderr or proc.stdout)[:120]!r}")
        if not proc.stdout.strip():
            problems.append("printed no help on stdout")
    return problems


def test_help_on_every_scaffolded_script_does_no_work(scaffolded: Path, tmp_path: Path):
    agents = scaffolded / ".agents"
    scripts = sorted(
        p.relative_to(scaffolded)
        for p in agents.rglob("*")
        if p.is_file() and p.suffix in (".sh", ".py")
    )
    covered = {p.relative_to(".agents").as_posix() for p in scripts}
    missed = _template_scripts() - covered
    assert not missed, f"the fixture renders no copy of these, so nothing sweeps them: {missed}"

    failures = {}
    for i, rel in enumerate(scripts):
        work = tmp_path / str(i)
        work.mkdir()
        if problems := _probe(scaffolded, rel, work):
            failures[rel.as_posix()] = problems
    assert not failures, "\n".join(f"{k}: {'; '.join(v)}" for k, v in failures.items())
