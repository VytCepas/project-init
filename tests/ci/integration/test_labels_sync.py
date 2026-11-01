"""gates/labels-sync.sh creates a scaffold's labels from the vendored register and from nothing else (harbor#1427)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[3] / "templates" / "base"
GH_STUB = """#!/bin/sh
# records every call; `label list` answers from $LIVE
printf '%s\\n' "$*" >> "$CALLS"
case "$1 $2" in
  "label list") cat "$LIVE" ;;
esac
exit 0
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A scaffold's relevant files: the gate and the vendored package, a gh stub beside them."""
    root = tmp_path / "scaffold"
    (root / "gates").mkdir(parents=True)
    shutil.copy(BASE / "gates" / "labels-sync.sh", root / "gates" / "labels-sync.sh")
    shutil.copytree(BASE / "vendor" / "naming", root / "vendor" / "naming")
    (tmp_path / "gh").write_text(GH_STUB, encoding="utf-8")
    (tmp_path / "gh").chmod(0o755)
    return root


def _run(repo: Path, live: str, *args: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    tmp = repo.parent
    (tmp / "live").write_text(live, encoding="utf-8")
    (tmp / "calls").write_text("", encoding="utf-8")
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(tmp),
        "TMPDIR": str(tmp),
        "LABELS_GH": str(tmp / "gh"),
        "LIVE": str(tmp / "live"),
        "CALLS": str(tmp / "calls"),
    }
    done = subprocess.run(
        ["sh", "gates/labels-sync.sh", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return done, (tmp / "calls").read_text(encoding="utf-8").splitlines()


def _register(repo: Path) -> set[str]:
    """The labels the vendored register lists, read by the vendored lint itself."""
    root = repo.parent / "gen"
    root.mkdir()
    pkg = repo / "vendor" / "naming"
    subprocess.run(
        [
            "sh",
            str(pkg / "lint-name.sh"),
            "--gen",
            "labels",
            "--root",
            str(root),
            "--registry",
            str(pkg / "registry"),
        ],
        capture_output=True,
        check=True,
    )
    rows = (root / "build" / "naming" / "labels.tsv").read_text(encoding="utf-8").splitlines()
    return {
        r.split("\t")[0] for r in rows if r and not r.startswith("#") and not r.startswith("name\t")
    }


def test_dry_run_lists_every_register_label_and_creates_nothing(repo: Path) -> None:
    done, calls = _run(repo, "")
    register = _register(repo)
    assert "type:bug" in register
    assert done.returncode == 1
    assert {line.split()[1] for line in done.stdout.splitlines()} == register
    assert [c for c in calls if c.startswith("label create")] == []


def test_apply_creates_exactly_the_register(repo: Path) -> None:
    done, calls = _run(repo, "", "--apply")
    created = {c.split()[2] for c in calls if c.startswith("label create")}
    assert done.returncode == 0
    assert created == _register(repo)


def test_a_label_the_register_does_not_list_is_neither_created_nor_removed(repo: Path) -> None:
    done, calls = _run(repo, "type:bug\nfoo\n", "--apply")
    assert done.returncode == 0
    assert not any(" foo" in c for c in calls)
    assert not any(c.startswith("label delete") for c in calls)
    assert "type:bug" not in {c.split()[2] for c in calls if c.startswith("label create")}


def test_a_repo_that_already_has_the_register_is_clean(repo: Path) -> None:
    done, _ = _run(repo, "\n".join(sorted(_register(repo))) + "\n")
    assert done.returncode == 0


def test_no_vendored_package_is_unchecked_not_a_pass(repo: Path) -> None:
    shutil.rmtree(repo / "vendor")
    done, _ = _run(repo, "")
    assert done.returncode == 3
