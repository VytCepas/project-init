"""The cross-repo test contract in the Python scaffold (PI-1044).

A scaffolded Python repo's root ``conftest.py`` makes every test hermetic (rule 1)
and ends every pytest run with ``<project>: N passed, M failed`` (rule 3); the
justfile's ``test`` recipe exits with pytest's own code (rule 2). Templates are the
product, so each property is checked by scaffolding into a temp dir and running
the scaffold's own tests there — never by reading the template's text.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.scaffold import _render, load_preset, scaffold
from project_init.upgrade import run_upgrade, write_scaffold_record
from tests.helpers import make_variables, memory_preset

REPO = Path(__file__).resolve().parents[2]
_CONTRACT_VARS = {
    "CLAUDE_CONFIG_DIR",
    "UV_CACHE_DIR",
    "UV_PYTHON_INSTALL_DIR",
    "UV_TOOL_DIR",
    "CARGO_HOME",
    "RUSTUP_HOME",
    "GOPATH",
    "GOCACHE",
    "BUN_INSTALL",
}
LINE = re.compile(r"^([A-Za-z0-9._-]+): (\d+) passed, (\d+) failed$", re.MULTILINE)

_PLANTED_HOME = """\
import os
import tempfile
from pathlib import Path


def test_home_is_not_the_real_home():
    real = Path(os.environ["REAL_HOME"])
    assert Path.home() != real
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
                "CLAUDE_CONFIG_DIR"):
        assert not Path(os.environ[var]).is_relative_to(real), var
    assert tempfile.gettempdir() == os.environ["TMPDIR"]
    assert os.environ["TMPDIR"] != os.environ["REAL_TMPDIR"]


def test_toolchain_caches_stay_real():
    assert Path(os.environ["UV_CACHE_DIR"]).is_relative_to(Path(os.environ["REAL_HOME"]))
"""

_PLANTED_MIXED = """\
import pytest


@pytest.fixture
def broken():
    raise RuntimeError("setup fails")


def test_one():
    assert True


def test_two():
    assert True


def test_fails():
    assert False


def test_errors(broken):
    assert True


@pytest.mark.skip(reason="a skip counts in neither")
def test_skipped():
    assert True
"""


def _python_scaffold(target: Path) -> Path:
    variables = make_variables()
    created = scaffold(target, load_preset("core"), variables)
    write_scaffold_record(target, "core", variables, created)
    return target


def _plant(target: Path, name: str, body: str) -> None:
    (target / "tests").mkdir(exist_ok=True)
    (target / "tests" / name).write_text(body)


def _pytest(target: Path, tmp: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the scaffold's own pytest with a HOME the scaffold must not reach."""
    real_home, real_tmp = tmp / "real-home", tmp / "real-tmp"
    real_home.mkdir(exist_ok=True)
    real_tmp.mkdir(exist_ok=True)
    # The child starts from a clean slate: nothing this suite's own fixture set may leak in.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("XDG_", "PYTEST_")) and k not in _CONTRACT_VARS
    }
    env |= {
        "HOME": str(real_home),
        "REAL_HOME": str(real_home),
        "TMPDIR": str(real_tmp),
        "REAL_TMPDIR": str(real_tmp),
    }
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=target,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=300,
    )


def _last_line(output: str) -> tuple[str, int, int] | None:
    found = LINE.findall(output)
    if not found:
        return None
    name, passed, failed = found[-1]
    return name, int(passed), int(failed)


class TestHermeticScaffold:
    def test_scaffolded_tests_cannot_read_the_real_home(self, tmp_path: Path) -> None:
        """#1044 done-when 1: a planted test asserting Path.home() is not the real
        home passes in a generated repo, because its conftest.py redirects it."""
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_home.py", _PLANTED_HOME)
        result = _pytest(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 2, 0), result.stdout

    def test_the_fixture_is_in_a_root_conftest_the_upgrade_owns(self, tmp_path: Path) -> None:
        target = _python_scaffold(tmp_path / "p")
        assert (target / "conftest.py").is_file()
        assert not (target / "tests" / "conftest.py").exists(), "tests/conftest.py is the user's"

    @pytest.mark.parametrize("language", ["node", "go", "rust"])
    def test_other_languages_get_no_python_conftest(self, tmp_path: Path, language: str) -> None:
        target = tmp_path / language
        scaffold(
            target,
            load_preset("core"),
            make_variables(language=language, python="", **{language: "true"}),
        )
        assert not (target / "conftest.py").exists()


class TestSummaryLine:
    def test_mixed_run_counts_errors_as_failed_and_skips_as_neither(self, tmp_path: Path) -> None:
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_mixed.py", _PLANTED_MIXED)
        result = _pytest(target, tmp_path)
        assert result.returncode == 1, "pytest's own code for a failed test, exactly"
        assert _last_line(result.stdout) == ("my-project", 2, 2), result.stdout

    def test_the_line_survives_xdist(self, tmp_path: Path) -> None:
        pytest.importorskip("xdist")
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_mixed.py", _PLANTED_MIXED)
        result = _pytest(target, tmp_path, "-n", "2")
        assert result.returncode == 1
        assert _last_line(result.stdout) == ("my-project", 2, 2), result.stdout

    def test_nothing_collected_keeps_pytest_exit_5(self, tmp_path: Path) -> None:
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_empty.py", "")
        result = _pytest(target, tmp_path)
        assert result.returncode == 5
        assert _last_line(result.stdout) == ("my-project", 0, 0), result.stdout


def _uv_stub(bin_dir: Path) -> None:
    """A `uv` that runs this interpreter's pytest with the recipe's own arguments."""
    stub = bin_dir / "uv"
    stub.write_text(
        "#!/bin/sh\n"
        'while [ $# -gt 0 ] && [ "$1" != pytest ]; do shift; done\n'
        "shift\n"
        f'exec "{sys.executable}" -m pytest -p no:cacheprovider "$@"\n'
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)


@pytest.mark.skipif(shutil.which("just") is None and not os.environ.get("CI"), reason="needs just")
class TestJustTestRecipe:
    """Rule 2 and 3 through the recipe itself: `just test` prints the line and
    exits with pytest's exact code. `uv` is a stub that runs this interpreter's
    pytest with the recipe's arguments, so the recipe is real and offline."""

    def _just_test(self, target: Path, tmp: Path) -> subprocess.CompletedProcess[str]:
        bin_dir = tmp / "bin"
        bin_dir.mkdir(exist_ok=True)
        _uv_stub(bin_dir)
        env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        return subprocess.run(
            ["just", "test"],
            cwd=target,
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=300,
        )

    def test_red_run_exits_1_with_the_line(self, tmp_path: Path) -> None:
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_mixed.py", _PLANTED_MIXED)
        result = self._just_test(target, tmp_path)
        assert result.returncode == 1, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 2, 2), result.stdout

    def test_green_run_exits_0_with_the_line(self, tmp_path: Path) -> None:
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_ok.py", "def test_ok():\n    assert True\n")
        result = self._just_test(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 1, 0), result.stdout

    def test_day_one_prints_a_zero_line(self, tmp_path: Path) -> None:
        target = _python_scaffold(tmp_path / "p")
        result = self._just_test(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "No test files yet" in result.stdout
        assert _last_line(result.stdout) == ("my-project", 0, 0), result.stdout


class TestUpgradePath:
    def test_upgrade_offers_the_conftest_to_a_repo_that_predates_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """#1044 done-when 3: the dry run lists the conftest for an existing repo,
        as its own addition group, and --accept-new test-contract brings it in."""
        target = tmp_path / "p"
        variables = make_variables()
        created = scaffold(target, memory_preset("obsidian-only"), variables, strict=True)
        write_scaffold_record(
            target, "obsidian-only", variables, [c for c in created if c != Path("conftest.py")]
        )
        (target / "conftest.py").unlink()
        # An unmanaged pin parks the #847 python-pin proposal, as test_consent does.
        (target / ".python-version").write_text("3.11\n")
        assert run_upgrade(target, apply=False) == 0
        out = " ".join(capsys.readouterr().out.split())
        assert "conftest.py" in out
        assert "test-contract" in out
        assert not (target / "conftest.py").exists(), "a dry run writes nothing"
        assert run_upgrade(target, apply=True, accept_new=["test-contract"]) == 0
        assert (target / "conftest.py").is_file()


class TestThisRepoAdoptsIt:
    def test_own_root_conftest_is_the_template_render(self) -> None:
        """PI-1044: this repo's suite runs under the same fixture it ships."""
        template = (REPO / "templates" / "base" / "conftest.py.tmpl").read_text()
        assert (REPO / "conftest.py").read_text() == _render(template, make_variables())

    def test_this_suite_is_hermetic(self) -> None:
        home = Path.home()
        assert "hermetic" in str(home), home
        assert Path(os.environ["CLAUDE_CONFIG_DIR"]).is_relative_to(home.parent)
