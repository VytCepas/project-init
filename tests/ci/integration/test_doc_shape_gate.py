"""harbor#1434, #1435: every scaffold carries the docs front matter shape, the generated-by header and their lint.

The judges are ``vendor/naming/doc-shape.sh`` and ``vendor/naming/doc-fresh-verify.sh`` (vendored from the standard),
run through ``gates/doc-check.sh``. These tests run the real scripts on a real scaffold:

* a scaffold made with an owner passes the lint strict, and its freshness verify is green;
* red check: a doc without front matter, a kind that disagrees with its folder, and a doc with no owner are each
  red under ``--strict`` and green once fixed; a generated file with the header and no ``fresh-checks.tsv`` row,
  and a row whose file lacks the header, are red;
* the shipped ``just docs-check`` recipe is wired into ``lint``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.__main__ import main

_GATE = ["sh", "gates/doc-check.sh"]


def _gate(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*_GATE, *args], cwd=target, capture_output=True, text=True, check=False, timeout=180
    )


@pytest.fixture(scope="module")
def fresh_scaffold(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A scaffold made by the real CLI path, with an owner so its docs carry one."""
    target = tmp_path_factory.mktemp("docshape") / "fresh"
    rc = main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            "obsidian-only",
            "--name",
            "doc-shape-test",
            "--description",
            "doc shape",
            "--language",
            "python",
            "--owner",
            "@fixture-owner",
        ]
    )
    assert rc == 0
    return target


@pytest.fixture
def repo(fresh_scaffold: Path, tmp_path: Path) -> Path:
    """A private copy of the fresh scaffold, so one test cannot touch another."""
    work = tmp_path / "repo"
    shutil.copytree(fresh_scaffold, work, symlinks=True)
    return work


class TestFreshScaffold:
    def test_ships_the_gate_the_judges_and_the_table(self, fresh_scaffold: Path):
        for rel in (
            "gates/doc-check.sh",
            "vendor/naming/doc-shape.sh",
            "vendor/naming/doc-fresh-verify.sh",
            "contracts/fresh-checks.tsv",
            "docs/how-to/index.md",
        ):
            assert (fresh_scaffold / rel).is_file(), rel
        just = (fresh_scaffold / "justfile").read_text(encoding="utf-8")
        assert "\ndocs-check:\n" in just
        assert "    just docs-check\n" in just

    def test_the_index_pages_carry_the_shape(self, fresh_scaffold: Path):
        text = (fresh_scaffold / "docs/how-to/index.md").read_text(encoding="utf-8")
        assert text.startswith("---\nkind: how-to\nowner: @fixture-owner\nstatus: current\n---\n")

    def test_passes_strict_on_its_own_tree(self, repo: Path):
        r = _gate(repo, "--strict")
        assert r.returncode == 0, r.stdout + r.stderr

    def test_the_freshness_verify_is_green(self, repo: Path):
        r = subprocess.run(
            ["sh", "vendor/naming/doc-fresh-verify.sh"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "vendor/naming/MANIFEST.tsv is current" in r.stdout + r.stderr


class TestRed:
    def test_a_doc_without_front_matter_is_red_then_green(self, repo: Path):
        doc = repo / "docs/how-to/bare.md"
        doc.write_text("# Bare\n", encoding="utf-8")
        red = _gate(repo, "--strict")
        assert red.returncode == 1, red.stdout + red.stderr
        assert "docs/how-to/bare.md" in red.stdout + red.stderr
        doc.write_text(
            "---\nkind: how-to\nowner: @fixture-owner\nstatus: draft\n---\n\n# Bare\n",
            encoding="utf-8",
        )
        assert _gate(repo, "--strict").returncode == 0

    def test_a_kind_that_disagrees_with_its_folder_is_red(self, repo: Path):
        (repo / "docs/how-to/wrong.md").write_text(
            "---\nkind: explanation\nowner: @fixture-owner\nstatus: draft\n---\n", encoding="utf-8"
        )
        red = _gate(repo, "--strict")
        assert red.returncode == 1, red.stdout + red.stderr
        assert "doc.kind-folder" in red.stdout + red.stderr

    def test_a_doc_with_no_owner_is_red(self, repo: Path):
        (repo / "docs/how-to/orphan.md").write_text(
            "---\nkind: how-to\nstatus: draft\n---\n", encoding="utf-8"
        )
        red = _gate(repo, "--strict")
        assert red.returncode == 1, red.stdout + red.stderr
        assert "no owner" in red.stdout + red.stderr

    def test_the_findings_are_born_warn_without_strict(self, repo: Path):
        (repo / "docs/how-to/bare.md").write_text("# Bare\n", encoding="utf-8")
        r = _gate(repo)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "docs/how-to/bare.md" in r.stdout + r.stderr

    def test_a_header_with_no_row_is_red(self, repo: Path):
        (repo / "out.txt").write_text("# generated-by: sh make-out.sh\nx\n", encoding="utf-8")
        red = _gate(repo, "--strict")
        assert red.returncode == 1, red.stdout + red.stderr
        assert "doc.fresh-registered" in red.stdout + red.stderr

    def test_a_row_whose_file_lacks_the_header_is_red(self, repo: Path):
        table = repo / "contracts/fresh-checks.tsv"
        table.write_text(
            table.read_text(encoding="utf-8") + "out.txt\ttrue\tsh make-out.sh\t\n",
            encoding="utf-8",
        )
        (repo / "out.txt").write_text("x\n", encoding="utf-8")
        red = _gate(repo, "--strict")
        assert red.returncode == 1, red.stdout + red.stderr
        assert "no generated-by header" in red.stdout + red.stderr


class TestCodeMapFreshness:
    """The code map is a generated file: it carries the header, has a row, and a hand edit turns the verify red."""

    _MAP = ".agents/docs/code-map.md"

    def _verify(self, repo: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", "vendor/naming/doc-fresh-verify.sh", "--root", "."],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )

    def _generate(self, repo: Path) -> None:
        r = subprocess.run(
            ["python3", ".agents/scripts/generate-code-map.py"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert r.returncode == 0, r.stdout + r.stderr

    def test_a_generated_map_is_green_and_a_hand_edit_is_red_then_green(self, repo: Path):
        self._generate(repo)
        head = (repo / self._MAP).read_text(encoding="utf-8")
        assert "<!-- generated-by: just code-map -->" in head
        assert _gate(repo, "--strict").returncode == 0
        green = self._verify(repo)
        assert green.returncode == 0, green.stdout + green.stderr
        assert f"{self._MAP} is current" in green.stdout + green.stderr
        (repo / self._MAP).write_text(head + "hand edit\n", encoding="utf-8")
        red = self._verify(repo)
        assert red.returncode == 1, red.stdout + red.stderr
        assert f"{self._MAP} is STALE" in red.stdout + red.stderr
        self._generate(repo)
        assert self._verify(repo).returncode == 0

    def test_no_map_yet_is_skipped_not_red(self, repo: Path):
        assert not (repo / self._MAP).exists()
        r = self._verify(repo)
        assert r.returncode == 0, r.stdout + r.stderr
