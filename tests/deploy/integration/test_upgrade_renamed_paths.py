"""harbor#967: a repo scaffolded before the template renames ends on the new names after an upgrade.

The scaffold is made by the scaffolder AS IT WAS before the renames — its ``src/`` and
``templates/`` read out of this repo's git history at ``_BEFORE`` — and upgraded by the one
under test. Between the two the owner edits a renamed script and adds a decision record
of their own, the way a real repo drifts from its render. Then the upgraded repo's own
checks run: its naming gate, ``project-init doctor``, and every reference it wires by name
(hook commands in its settings, justfile recipes, CI workflows, docs) must resolve.

Without the migration the upgrade still renders the new names, but the old files stay
beside them, the owner's edit is stranded in the old file and the owner's decision record
stays in a directory nothing links any more; these tests go red.

Reading ``_BEFORE`` needs history: a shallow clone (CI's default ``fetch-depth: 1``) skips
these tests and says so.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from project_init.doctor import collect_checks
from project_init.renames import RENAMED_LEAVES, SHIMMED_OLD_PATHS, TEMPLATE_RENAMES, renamed
from project_init.upgrade import run_upgrade

_REPO = Path(__file__).resolve().parents[3]
# The last commit whose templates carry the old names.
_BEFORE = "89d7a97d965454b55c1821644de3779ed8e122de"
_EDIT = "# a local edit the rename must carry\n"
_OUR_RECORD = "# ADR-009: a decision the team wrote\n"
_SCAFFOLD_ARGS = [
    "--non-interactive",
    "--preset",
    "obsidian-only",
    "--name",
    "renames",
    "--description",
    "renamed paths",
    "--language",
    "python",
    "--no-plugin",
    "--governance",
    "--iac",
    "opentofu",
    "--agents",
    "claude,codex,junie",
]


def _git(*args: str, cwd: Path = _REPO) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)


def _have_before() -> bool:
    return (
        shutil.which("git") is not None
        and _git("cat-file", "-e", f"{_BEFORE}^{{commit}}").returncode == 0
    )


pytestmark = pytest.mark.skipif(
    not _have_before(),
    reason=f"needs commit {_BEFORE[:7]} in this clone's history (CI: actions/checkout fetch-depth: 0)",
)


def _scaffold_before(old: Path, target: Path) -> None:
    """Scaffold *target* with the scaffolder at ``_BEFORE``, run from its own source tree."""
    archive = _git("archive", _BEFORE, "src", "templates", "schemas")
    assert archive.returncode == 0, archive.stderr.decode()
    with tarfile.open(fileobj=BytesIO(archive.stdout)) as tar:
        tar.extractall(old, filter="data")
    src = old / "src"
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import project_init;"
        "assert project_init.__file__.startswith(sys.argv[1]), project_init.__file__;"
        "from project_init.__main__ import main; raise SystemExit(main(sys.argv[2:]))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(src), str(target), *_SCAFFOLD_ARGS],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]


def _commit(target: Path, message: str) -> None:
    for args in (
        ("add", "-A"),
        ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message),
    ):
        assert _git(*args, cwd=target).returncode == 0


def _exact(path: Path) -> bool:
    """True when *path* exists with this exact spelling (macOS file systems fold case)."""
    return path.exists() and path.name in os.listdir(path.parent)


def _files(target: Path) -> set[str]:
    return {p.relative_to(target).as_posix() for p in target.rglob("*") if ".git" not in p.parts}


@pytest.fixture(scope="module")
def upgraded(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, set[str]]:
    """``(project, paths it had before the upgrade)``: scaffolded before the renames, edited, upgraded."""
    root = tmp_path_factory.mktemp("renamed-paths")
    target = root / "project"
    _scaffold_before(root / "before", target)
    assert _git("init", "-q", cwd=target).returncode == 0
    _commit(target, "scaffold")
    with (target / ".agents/scripts/monitor_pr.sh").open("a", encoding="utf-8") as f:
        f.write(_EDIT)
    (target / ".agents/docs/adr/our-decision.md").write_text(_OUR_RECORD, encoding="utf-8")
    _commit(target, "the team's own changes")
    had = {rel for rel in _files(target) if _exact(target / rel)}

    assert run_upgrade(target, apply=True, accept_new=["all"]) == 0
    return target, had


def test_the_scaffold_before_had_the_old_names(upgraded: tuple[Path, set[str]]) -> None:
    """Guards the fixture: a scaffold that never had the old names proves nothing."""
    _target, had = upgraded
    for must in (".agents/scripts/monitor_pr.sh", ".agents/hooks/_py.sh", "PLAN.md", "infra"):
        assert must in had, f"the {_BEFORE[:7]} scaffold has no {must}"


def test_every_old_path_moved_to_its_new_name(upgraded: tuple[Path, set[str]]) -> None:
    target, had = upgraded
    olds = [old for old, _new in TEMPLATE_RENAMES if old in had]
    left = [old for old in olds if old not in SHIMMED_OLD_PATHS and _exact(target / old)]
    missing = [new for old in olds if not _exact(target / (new := renamed(old) or old))]
    assert not left, f"old names still in the tree: {sorted(left)}"
    assert not missing, f"renamed paths not at their new name: {sorted(missing)}"
    strays = sorted(p.relative_to(target).as_posix() for p in target.rglob("*.new"))
    assert not strays, f"the rename parked files as .new siblings: {strays}"


def test_a_local_edit_moves_with_its_file(upgraded: tuple[Path, set[str]]) -> None:
    target, _had = upgraded
    text = (target / ".agents/scripts/watch-pr.sh").read_text(encoding="utf-8")
    assert _EDIT in text, "the owner's edit to monitor_pr.sh was lost in the rename"
    assert "watch-pr.sh" in text, "the template's own change to the script was not merged in"


def test_an_unmanaged_file_moves_with_its_directory(upgraded: tuple[Path, set[str]]) -> None:
    target, _had = upgraded
    ours = target / ".agents/docs/decisions/our-decision.md"
    assert ours.is_file(), "the team's own decision record stayed behind in docs/adr/"
    assert ours.read_text(encoding="utf-8") == _OUR_RECORD


def test_the_shimmed_old_name_still_runs_the_new_one(upgraded: tuple[Path, set[str]]) -> None:
    target, _had = upgraded
    for old in SHIMMED_OLD_PATHS:
        shim = target / old
        assert shim.is_file() and os.access(shim, os.X_OK), f"{old}: no executable shim"
        new = dict(TEMPLATE_RENAMES)[old]
        assert Path(new).name in shim.read_text(encoding="utf-8"), f"{old} does not run {new}"


_OLD_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])("
    + "|".join(
        re.escape(o)
        for o, _n in sorted(RENAMED_LEAVES, key=lambda p: -len(p[0]))
        if f".agents/scripts/{o}" not in SHIMMED_OLD_PATHS
    )
    + r"|docs/adr/|skills/INDEX\.md|CODE_MAP\.md|NIST_RMF_CROSSWALK|AI_USAGE_POLICY"
    + r"|working-directory: infra|\"infra/\*\*\")(?![A-Za-z0-9_])"
)
# Never compared or touched by an upgrade, or not the project's own text.
_UNREAD = (".git/", ".agents/memory/", ".agents/vault/", "vendor/", "gates/naming.baseline")


def test_nothing_in_the_project_names_an_old_path(upgraded: tuple[Path, set[str]]) -> None:
    """Settings, justfile, CI workflows, docs: every file the scaffolder owns says the new name."""
    target, _had = upgraded
    hits: list[str] = []
    for f in sorted(p for p in target.rglob("*") if p.is_file()):
        rel = f.relative_to(target).as_posix()
        if rel.startswith(_UNREAD) or rel in SHIMMED_OLD_PATHS:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits += [f"{rel}: {m.group(1)}" for m in _OLD_TOKEN.finditer(text)]
    assert not hits, "old names still referenced:\n" + "\n".join(hits[:40])


_WIRED = re.compile(
    r"(?:\$CLAUDE_PROJECT_DIR/|\$\{CLAUDE_PROJECT_DIR\}/|\./)?(\.agents/[A-Za-z0-9_./-]+)"
)


def test_every_wired_path_resolves(upgraded: tuple[Path, set[str]]) -> None:
    """Hook commands, recipes and workflow steps that ran a file before still run one.

    A path the scaffold never had (a generated code map, a declaration the owner has not
    written yet) is not the upgrade's to provide; a path that existed before, under its
    old name or this one, must exist now.
    """
    target, had = upgraded
    existed = had | {renamed(rel) or rel for rel in had}
    wiring = [
        target / ".claude/settings.json",
        target / ".agents/settings.json",
        target / ".codex/hooks.json",
        target / "justfile",
        *sorted((target / ".github/workflows").glob("*.yml")),
        *sorted((target / ".github/hooks").glob("*")),
    ]
    json.loads((target / ".claude/settings.json").read_text(encoding="utf-8"))
    dead: list[str] = []
    for f in wiring:
        if not f.is_file():
            continue
        for path in _WIRED.findall(f.read_text(encoding="utf-8")):
            path = path.rstrip(".")
            if any(c in path for c in "*<{$") or path.endswith("/"):
                continue
            if path in existed and not (target / path).exists():
                dead.append(f"{f.relative_to(target)} -> {path}")
    assert not dead, "wired paths that do not exist:\n" + "\n".join(dead)


def test_the_project_s_own_checks_pass(upgraded: tuple[Path, set[str]]) -> None:
    target, _had = upgraded
    gate = subprocess.run(
        ["sh", "gates/naming-check.sh"],
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert gate.returncode == 0, gate.stdout[-3000:] + gate.stderr[-1000:]
    failed = [f"{c.title}: {c.message}" for c in collect_checks(target) if c.level == "FAIL"]
    assert not failed, "project-init doctor fails on the upgraded repo:\n" + "\n".join(failed)
