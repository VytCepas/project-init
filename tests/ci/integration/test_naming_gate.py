"""harbor#967: every scaffold and upgrade carries harbor's naming gate, as a ratchet.

The gate is ``gates/naming-check.sh`` judging with the vendored package in
``vendor/naming/``. These tests run the real script on real scaffolds:

* a fresh ``project-init`` scaffold has the gate and passes on its own tree
  (the template's own findings are baselined at scaffold time);
* red check: plant a bad name -> NEW, red; remove it -> green; delete a baselined
  file -> STALE, red; every outcome is the script's exit code, not a text match
  on the script;
* with neither a vendored package nor a harbor checkout the gate says UNCHECKED
  and exits 3, and an edited vendored file is red, never a pass;
* an upgrade of a repo that predates the gate adds it with a baseline seeded from
  the repo's current findings, so it is not red on day one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.__main__ import main
from project_init.scaffold import scaffold
from project_init.upgrade import run_upgrade, write_scaffold_record
from tests.helpers import make_variables, memory_preset

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="the naming gate reads the tree through git"
)

_GATE = ["sh", "gates/naming-check.sh"]
_PLANTED = "Planted_Case.md"


def _gate(target: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    e = {**os.environ, **env}
    return subprocess.run(
        [*_GATE, *args],
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
        env=e,
    )


def _rows(target: Path) -> list[str]:
    text = (target / "gates/naming.baseline").read_text(encoding="utf-8")
    return [ln for ln in text.splitlines() if ln and not ln.startswith("#")]


@pytest.fixture(scope="module")
def fresh_scaffold(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A scaffold made by the real CLI path (which seeds the baseline)."""
    target = tmp_path_factory.mktemp("naming") / "fresh"
    rc = main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            "obsidian-only",
            "--name",
            "naming-gate-test",
            "--description",
            "naming gate",
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


class TestFreshScaffold:
    def test_ships_the_gate_the_vendored_package_and_the_recipe(self, fresh_scaffold: Path):
        for rel in (
            "gates/naming-check.sh",
            "gates/naming.baseline",
            "vendor/naming/lint-name.sh",
            "vendor/naming/standard-vendor.sh",
            "vendor/naming/MANIFEST.tsv",
            "vendor/naming/registry/registers.tsv",
        ):
            assert (fresh_scaffold / rel).is_file(), rel
        assert os.access(fresh_scaffold / "gates/naming-check.sh", os.X_OK)
        just = (fresh_scaffold / "justfile").read_text(encoding="utf-8")
        assert "\nnaming:\n" in just

    @pytest.mark.skipif(shutil.which("just") is None, reason="just not installed")
    def test_lint_runs_the_gate(self, fresh_scaffold: Path):
        r = subprocess.run(
            ["just", "--dry-run", "lint"],
            cwd=fresh_scaffold,
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0, r.stderr
        assert "just naming" in r.stderr + r.stdout

    def test_passes_on_its_own_tree(self, repo: Path):
        r = _gate(repo)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "0 new, 0 stale" in r.stdout

    @pytest.mark.skipif(shutil.which("just") is None, reason="just not installed")
    def test_just_naming_is_green(self, repo: Path):
        r = subprocess.run(
            ["just", "naming"], cwd=repo, capture_output=True, text=True, check=False, timeout=180
        )
        assert r.returncode == 0, r.stdout + r.stderr


class TestRatchet:
    def test_planted_bad_name_is_red_then_green_when_removed(self, repo: Path):
        planted = repo / _PLANTED
        planted.write_text("x\n", encoding="utf-8")
        red = _gate(repo)
        assert red.returncode == 1, red.stdout + red.stderr
        assert "NEW" in red.stdout
        assert _PLANTED in red.stdout
        planted.unlink()
        green = _gate(repo)
        assert green.returncode == 0, green.stdout + green.stderr

    def test_fixing_a_baselined_finding_is_red_until_its_row_is_deleted(self, repo: Path):
        rows = _rows(repo)
        victim = "mypy.ini"
        mine = [r for r in rows if r.endswith(f"\t{victim}")]
        assert mine, "the scaffold baselines mypy.ini"
        (repo / victim).unlink()
        stale = _gate(repo)
        assert stale.returncode == 1, stale.stdout + stale.stderr
        assert "STALE" in stale.stdout and victim in stale.stdout
        base = repo / "gates/naming.baseline"
        base.write_text(
            "".join(f"{ln}\n" for ln in base.read_text().splitlines() if ln not in mine),
            encoding="utf-8",
        )
        assert _gate(repo).returncode == 0

    def test_a_missing_baseline_is_red_not_a_pass(self, repo: Path):
        (repo / "gates/naming.baseline").unlink()
        r = _gate(repo)
        assert r.returncode == 1
        assert "no baseline" in r.stderr

    def test_seed_refuses_to_overwrite_a_baseline_with_rows(self, repo: Path):
        before = (repo / "gates/naming.baseline").read_bytes()
        r = _gate(repo, "--seed")
        assert r.returncode == 2
        assert (repo / "gates/naming.baseline").read_bytes() == before

    def test_exemption_row_silences_a_name_the_repo_owns(self, repo: Path):
        (repo / _PLANTED).write_text("x\n", encoding="utf-8")
        assert _gate(repo).returncode == 1
        # Same columns as the vendored registry/exemptions.tsv.
        (repo / "naming-exemptions.tsv").write_text(
            "# repo-owned exemptions\n"
            f"repo-0001\tname.case\t{_PLANTED}\tworld-name\tnever\ta name a client's tool requires\n"
            f"repo-0002\tname.separator\t{_PLANTED}\tworld-name\tnever\tthe same name\n",
            encoding="utf-8",
        )
        r = _gate(repo)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_an_exemptions_file_with_no_rows_still_reaches_the_verdict(self, repo: Path):
        # grep -v over a header-only file matches nothing and exits 1; under `set -e` that must not end the gate.
        (repo / "naming-exemptions.tsv").write_text(
            "# repo-owned exemptions\nid\trule\tsubject\tkind\tremove_by\treason\n",
            encoding="utf-8",
        )
        r = _gate(repo)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "naming-check:" in r.stdout + r.stderr


class TestAnotherRoot:
    """NAMING_ROOT judges another tree with its own exemptions and baseline, the judge staying put."""

    def _other(self, tmp_path: Path) -> tuple[Path, Path]:
        other = tmp_path / "other"
        other.mkdir()
        (other / "notes.md").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=other, check=True)
        baseline = tmp_path / "other.baseline"
        baseline.write_text("", encoding="utf-8")
        return other, baseline

    def test_judges_that_root_red_then_green(self, repo: Path, tmp_path: Path):
        other, baseline = self._other(tmp_path)
        env = {"NAMING_ROOT": str(other), "NAMING_BASELINE": str(baseline)}
        green = _gate(repo, **env)
        assert green.returncode == 0, green.stdout + green.stderr
        assert "0 finding(s) now" in green.stdout, "the gate's own tree is not what was judged"
        (other / _PLANTED).write_text("x\n", encoding="utf-8")
        red = _gate(repo, **env)
        assert red.returncode == 1, red.stdout + red.stderr
        assert _PLANTED in red.stdout
        (other / _PLANTED).unlink()
        assert _gate(repo, **env).returncode == 0

    def test_reads_that_roots_exemptions(self, repo: Path, tmp_path: Path):
        other, baseline = self._other(tmp_path)
        (other / _PLANTED).write_text("x\n", encoding="utf-8")
        (other / "naming-exemptions.tsv").write_text(
            f"o-0001\tname.case\t{_PLANTED}\tworld-name\tnever\tthe other root owns it\n"
            f"o-0002\tname.separator\t{_PLANTED}\tworld-name\tnever\tthe same name\n",
            encoding="utf-8",
        )
        r = _gate(repo, NAMING_ROOT=str(other), NAMING_BASELINE=str(baseline))
        assert r.returncode == 0, r.stdout + r.stderr

    def test_a_root_that_is_not_a_directory_is_a_usage_error(self, repo: Path, tmp_path: Path):
        r = _gate(repo, NAMING_ROOT=str(tmp_path / "absent"))
        assert r.returncode == 2, r.stdout + r.stderr
        assert "NAMING_ROOT" in r.stderr


class TestUnchecked:
    def test_no_vendored_package_and_no_source_checkout_is_unchecked_exit_3(
        self, repo: Path, tmp_path: Path
    ):
        shutil.rmtree(repo / "vendor")
        r = _gate(repo, NAMING_SOURCE=str(tmp_path / "no-source"))
        assert r.returncode == 3, r.stdout + r.stderr
        assert "UNCHECKED" in r.stderr

    def test_a_scaffold_that_is_not_a_repository_yet_is_judged_not_skipped(
        self, fresh_scaffold: Path, tmp_path: Path
    ):
        work = tmp_path / "nogit"
        shutil.copytree(fresh_scaffold, work, symlinks=True)
        assert not (work / ".git").exists()
        env = {"GIT_CEILING_DIRECTORIES": str(tmp_path)}
        green = _gate(work, **env)
        assert green.returncode == 0, green.stdout + green.stderr
        (work / _PLANTED).write_text("x\n", encoding="utf-8")
        red = _gate(work, **env)
        assert red.returncode == 1, red.stdout + red.stderr
        assert _PLANTED in red.stdout

    def test_an_edited_vendored_file_is_red(self, repo: Path):
        lint = repo / "vendor/naming/registry/terms.tsv"
        lint.write_text(lint.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")
        r = _gate(repo)
        assert r.returncode == 1, r.stdout + r.stderr
        assert "MANIFEST" in r.stderr


class TestUpgradeAddsTheGate:
    def _predates_gate(self, tmp_path: Path) -> Path:
        """A repo scaffolded before the gate existed, with a finding of its own."""
        target = tmp_path / "old"
        v = make_variables()
        created = scaffold(target, memory_preset("obsidian-only"), v, strict=True)
        gate_files = {
            p
            for p in created
            if p.parts[0] in ("gates", "vendor") or p.as_posix() == "naming-exemptions.tsv"
        }
        assert gate_files, "the template ships no gate files"
        write_scaffold_record(
            target, "obsidian-only", v, [c for c in created if c not in gate_files]
        )
        shutil.rmtree(target / "gates")
        shutil.rmtree(target / "vendor")
        (target / ".python-version").write_text("3.11\n")  # park the #847 proposal
        (target / "Legacy_Notes.md").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=target, check=True)
        return target

    def test_upgrade_adds_the_gate_with_a_seeded_baseline_and_is_green(self, tmp_path: Path):
        target = self._predates_gate(tmp_path)
        assert run_upgrade(target, apply=True, accept_new=["naming-gate"]) == 0
        assert (target / "gates/naming-check.sh").is_file()
        assert (target / "vendor/naming/MANIFEST.tsv").is_file()
        assert any(r.endswith("\tLegacy_Notes.md") for r in _rows(target)), (
            "the repo's own finding is baselined"
        )
        r = _gate(target)
        assert r.returncode == 0, r.stdout + r.stderr
        # And it is a real gate there too: a new bad name goes red.
        (target / _PLANTED).write_text("x\n", encoding="utf-8")
        assert _gate(target).returncode == 1

    def test_a_declined_group_adds_nothing_and_a_second_upgrade_keeps_the_baseline(
        self, tmp_path: Path
    ):
        target = self._predates_gate(tmp_path)
        assert run_upgrade(target, apply=True, decline_new=["naming-gate"]) == 0
        assert not (target / "gates").exists()
        assert run_upgrade(target, apply=True, accept_new=["naming-gate"]) == 0
        seeded = (target / "gates/naming.baseline").read_bytes()
        assert run_upgrade(target, apply=True) == 0
        assert (target / "gates/naming.baseline").read_bytes() == seeded
