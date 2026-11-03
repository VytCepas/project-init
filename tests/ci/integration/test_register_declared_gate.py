"""harbor#1424 item 7: a scaffolded repo goes red on a ``.tsv`` register that declares no schema.

The judge is the vendored naming package's ``lint-name.sh`` (``standard.register-declared``), run through the
scaffold's own ``gates/naming-check.sh`` ratchet. These tests run the real scripts on a real scaffold:

* an undeclared ``.tsv`` is red, with the rule and the file named, and green once the repo declares it in
  ``naming-schemas.tsv`` (the schema rows the repo owns beside the vendored table);
* the declaring row is not a free pass: a register whose header differs from the one it declares is red;
* the shipped ``contracts/fresh-checks.tsv`` is itself a declared register, so a fresh scaffold is green.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.__main__ import main

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="the naming gate reads the tree through git"
)

_GATE = ["sh", "gates/naming-check.sh"]
_RULE = "standard.register-declared"
_HEADER = "id\theader\tcolumns\tkey\trefs\towner\tread_by\tnote\n"


def _gate(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _GATE, cwd=target, capture_output=True, text=True, check=False, timeout=180
    )


def _declare(repo: Path, register: str, header: str, columns: str) -> None:
    """Add this repo's own schema row for ``register`` to naming-schemas.tsv."""
    row = f"{register}\t{header}\t{columns}\t{columns.split()[0]}\t\tdoc\tthe fixture\ta fixture register\n"
    path = repo / "naming-schemas.tsv"
    if not path.exists():
        path.write_text(_HEADER, encoding="utf-8")
    path.write_text(path.read_text(encoding="utf-8") + row, encoding="utf-8")


@pytest.fixture(scope="module")
def fresh_scaffold(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A scaffold made by the real CLI path, with its baseline seeded."""
    target = tmp_path_factory.mktemp("register") / "fresh"
    rc = main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            "obsidian-only",
            "--name",
            "register-gate-test",
            "--description",
            "register gate",
            "--language",
            "python",
        ]
    )
    assert rc == 0
    return target


@pytest.fixture
def repo(fresh_scaffold: Path, tmp_path: Path) -> Path:
    """A private git copy of the fresh scaffold, so one test cannot touch another."""
    work = tmp_path / "repo"
    shutil.copytree(fresh_scaffold, work, symlinks=True)
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    return work


class TestUndeclaredRegister:
    def test_the_fresh_scaffold_is_green(self, repo: Path):
        r = _gate(repo)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "0 new, 0 stale" in r.stdout

    def test_an_undeclared_tsv_is_red_then_green_once_declared(self, repo: Path):
        register = repo / "ledger.tsv"
        register.write_text("id\tnote\nfirst\tone\n", encoding="utf-8")
        red = _gate(repo)
        assert red.returncode == 1, red.stdout + red.stderr
        assert f"{_RULE}\tregister:ledger.tsv" in red.stdout
        _declare(repo, "ledger.tsv", "row", "id note")
        green = _gate(repo)
        assert green.returncode == 0, green.stdout + green.stderr
        assert _RULE not in green.stdout

    def test_a_declared_register_with_another_header_is_red(self, repo: Path):
        (repo / "ledger.tsv").write_text("id\tcomment\nfirst\tone\n", encoding="utf-8")
        _declare(repo, "ledger.tsv", "row", "id note")
        red = _gate(repo)
        assert red.returncode == 1, red.stdout + red.stderr
        assert f"{_RULE}\tregister:ledger.tsv" in red.stdout

    def test_removing_the_register_is_green_again(self, repo: Path):
        register = repo / "ledger.tsv"
        register.write_text("id\tnote\nfirst\tone\n", encoding="utf-8")
        assert _gate(repo).returncode == 1
        register.unlink()
        assert _gate(repo).returncode == 0
