"""#1052: test-contract rule 2 (exact exit codes) is mechanised, here and in the scaffold.

`check_test_contract.py exit-codes` fails on an assertion that accepts any
non-zero exit. The ratchet is zero: every assertion in this repo names its code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables
from tools.sync_agents_from_templates import strip_conditional_wrapper

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "templates" / "base" / "dot_agents" / "scripts" / "check_test_contract.py.tmpl"
# The template is stored `{{#if python}}`-gated; render it (Python scaffold) once.
_RENDERED = Path(tempfile.mkdtemp(prefix="test-contract-")) / "check_test_contract.py"
_RENDERED.write_text(strip_conditional_wrapper(TEMPLATE.read_text()))
SCRIPT = _RENDERED


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
    "assert proc.returncode != 0 or 'x' in proc.stderr",
    "assert 'x' in proc.stderr or proc.returncode > 0",
    "assert ('x' in proc.stderr and proc.returncode != 0) or y",
    "assert proc.returncode != 0  # test-contract: nonzero-ok:",
]
ALLOWED = [
    "assert proc.returncode == 1",
    "assert proc.returncode in (1, 2)",
    "assert proc.returncode == 1 or proc.returncode == 2",
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


class TestScaffoldShipsItOnlyWherePythonRuns:
    """#1074 review: a Python-only helper is not copied into node/go/rust scaffolds."""

    @pytest.mark.parametrize("language", ["node", "go", "rust"])
    def test_non_python_scaffold_omits_it(self, tmp_path: Path, language: str) -> None:
        target = tmp_path / "p"
        scaffold(
            target,
            load_preset("core"),
            make_variables(language=language, python="", **{language: "true"}),
        )
        assert not (target / ".agents" / "scripts" / "check_test_contract.py").exists()


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
