"""#1052/#1053: test-contract rules 2 and 4 are mechanised, here and in the scaffold.

`check_test_contract.py exit-codes` fails on an assertion that accepts any
non-zero exit. The ratchet is zero: every assertion in this repo names its code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "templates" / "base" / "dot_agents" / "scripts" / "check_test_contract.py"


def _check(*args: str, cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd, check=False
    )


def _plant(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "tests" / "test_planted.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


FLAGGED = [
    "assert proc.returncode != 0",
    "assert proc.returncode != 0, proc.stderr",
    "assert result.returncode > 0",
    "assert 0 != proc.returncode",
    "assert rc != 0",
    "assert exit_code != 0",
    "assert proc.returncode",
    "assert not proc.returncode == 0",
    "assert proc.returncode != 0 and 'x' in proc.stderr",
    "assert proc.returncode != 0  # test-contract: nonzero-ok:",
]
ALLOWED = [
    "assert proc.returncode == 1",
    "assert proc.returncode in (1, 2)",
    "assert proc.returncode == 0",
    "if proc.returncode != 0:\n    pass",
    "assert count != 0",
    "assert proc.returncode != 0  # test-contract: nonzero-ok: the signal number varies by OS",
]


class TestExitCodeCheck:
    def test_this_repos_tests_name_every_exit_code(self) -> None:
        """The ratchet: zero non-exact exit-code assertions under tests/."""
        result = _check("exit-codes", "tests")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_planted_assertion_in_a_copy_goes_red(self, tmp_path: Path) -> None:
        copy = tmp_path / "tests"
        shutil.copytree(REPO / "tests", copy, ignore=shutil.ignore_patterns("__pycache__"))
        clean = _check("exit-codes", str(copy))
        assert clean.returncode == 0, clean.stdout + clean.stderr
        planted = copy / "unit" / "test_planted.py"
        planted.write_text("def test_x(proc):\n    assert proc.returncode != 0\n")
        red = _check("exit-codes", str(copy))
        assert red.returncode == 1, red.stdout + red.stderr
        assert f"{planted}:2:" in red.stdout

    @pytest.mark.parametrize("line", FLAGGED)
    def test_flagged(self, tmp_path: Path, line: str) -> None:
        _plant(tmp_path, f"def test_x(proc, rc, exit_code):\n    {line}\n")
        result = _check("exit-codes", cwd=tmp_path)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "test_planted.py:2:" in result.stdout

    @pytest.mark.parametrize("line", ALLOWED)
    def test_allowed(self, tmp_path: Path, line: str) -> None:
        body = "\n".join(f"    {row}" for row in line.splitlines())
        _plant(tmp_path, f"def test_x(proc, count):\n{body}\n")
        result = _check("exit-codes", cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_no_tests_dir_is_clean(self, tmp_path: Path) -> None:
        assert _check("exit-codes", cwd=tmp_path).returncode == 0

    def test_a_named_path_that_does_not_exist_is_a_usage_error(self, tmp_path: Path) -> None:
        assert _check("exit-codes", "nope", cwd=tmp_path).returncode == 2


class TestScaffoldRunsIt:
    """A scaffolded Python repo's `just lint` runs the check (fails red on a plant)."""

    @staticmethod
    def _lint(target: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        if shutil.which("just") is None:
            pytest.skip("just is not on PATH")
        # A stub uv: `uv run python ...` runs the real interpreter, every other tool passes.
        stub = tmp_path / "stub"
        stub.mkdir(exist_ok=True)
        (stub / "uv").write_text(
            "#!/usr/bin/env bash\n"
            '[ "$1" = run ] && shift\n'
            'while [ "$1" = --with ]; do shift 2; done\n'
            f'if [ "$1" = python ]; then shift; exec "{sys.executable}" "$@"; fi\n'
            "exit 0\n"
        )
        (stub / "uv").chmod(0o755)
        env = {**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
        return subprocess.run(
            ["just", "lint"], cwd=target, capture_output=True, text=True, env=env, check=False
        )

    def test_scaffold_lint_goes_red_on_a_planted_nonzero_assertion(self, tmp_path: Path) -> None:
        target = tmp_path / "p"
        scaffold(target, load_preset("core"), make_variables())
        assert (target / ".agents" / "scripts" / "check_test_contract.py").is_file()
        (target / "tests").mkdir(exist_ok=True)
        planted = target / "tests" / "test_planted.py"
        planted.write_text("def test_x(proc):\n    assert proc.returncode == 1\n")
        green = self._lint(target, tmp_path)
        assert green.returncode == 0, green.stdout + green.stderr
        planted.write_text("def test_x(proc):\n    assert proc.returncode != 0\n")
        red = self._lint(target, tmp_path)
        assert red.returncode == 1, red.stdout + red.stderr
        assert "tests/test_planted.py:2:" in red.stdout


class TestDiscoveryCheck:
    """#1053: a file under tests/ defining a test that no full collection reaches."""

    def test_this_repo_has_no_undiscovered_test_file(self) -> None:
        result = _check("discovery", "tests")
        assert result.returncode == 0, result.stdout + result.stderr

    @pytest.mark.parametrize(
        "body",
        [
            "def test_x():\n    assert False\n",
            "class TestX:\n    def test_x(self):\n        assert False\n",
            "async def test_x():\n    assert False\n",
        ],
    )
    def test_a_planted_check_file_goes_red(self, tmp_path: Path, body: str) -> None:
        _plant(tmp_path, "def test_ok():\n    assert True\n")
        (tmp_path / "tests" / "check_x.py").write_text(body)
        result = _check("discovery", cwd=tmp_path)
        assert result.returncode == 1, result.stdout + result.stderr
        line = 2 if body.startswith("class") else 1
        assert (
            f"tests/check_x.py:{line}: defines a test that pytest never collects" in result.stdout
        )

    def test_collected_and_helper_files_are_clean(self, tmp_path: Path) -> None:
        _plant(tmp_path, "def test_ok():\n    assert True\n")
        (tmp_path / "tests" / "helpers.py").write_text("def make():\n    return 1\n")
        (tmp_path / "tests" / "widget_test.py").write_text("def test_w():\n    assert True\n")
        result = _check("discovery", cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_an_ignored_file_counts_as_unreached(self, tmp_path: Path) -> None:
        """Discovery is what pytest actually collects, not a filename pattern."""
        _plant(tmp_path, "def test_ok():\n    assert True\n")
        (tmp_path / "tests" / "test_skipped_dir.py").write_text("def test_s():\n    assert True\n")
        (tmp_path / "pytest.ini").write_text(
            "[pytest]\naddopts = --ignore=tests/test_skipped_dir.py\n"
        )
        result = _check("discovery", cwd=tmp_path)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "tests/test_skipped_dir.py" in result.stdout

    def test_a_collection_error_is_a_finding(self, tmp_path: Path) -> None:
        _plant(tmp_path, "import no_such_module\n\ndef test_ok():\n    assert True\n")
        result = _check("discovery", cwd=tmp_path)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "pytest --collect-only exited 2" in result.stdout

    def test_no_tests_dir_is_clean(self, tmp_path: Path) -> None:
        assert _check("discovery", cwd=tmp_path).returncode == 0

    def test_a_named_dir_that_does_not_exist_is_a_usage_error(self, tmp_path: Path) -> None:
        assert _check("discovery", "nope", cwd=tmp_path).returncode == 2

    def test_scaffold_lint_goes_red_on_a_planted_check_file(self, tmp_path: Path) -> None:
        target = tmp_path / "p"
        scaffold(target, load_preset("core"), make_variables())
        (target / "tests").mkdir(exist_ok=True)
        (target / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
        green = TestScaffoldRunsIt._lint(target, tmp_path)
        assert green.returncode == 0, green.stdout + green.stderr
        (target / "tests" / "check_x.py").write_text("def test_x():\n    assert False\n")
        red = TestScaffoldRunsIt._lint(target, tmp_path)
        assert red.returncode == 1, red.stdout + red.stderr
        assert "tests/check_x.py:1:" in red.stdout
