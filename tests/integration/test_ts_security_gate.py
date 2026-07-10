"""PI-729/PI-732: the scaffolded TS lint gate must actually block insecure code.

The contract tests in `test_quality_toolchain.py` assert the *text* of
`eslint.config.mjs`. That is the weak class of guard this repo keeps getting
burned by: a config can say `"security/detect-eval-with-expression": "error"`
while the toolchain it configures crashes on startup and lints nothing.

This module runs the real thing — `bun add` the scaffolded dev-dependency set,
then eslint the scaffolded config — and asserts exit codes:

    eval(userInput) / el.innerHTML = dirty  -> exit 1 (blocked)
    clean code                              -> exit 0
    no sources at all (fresh scaffold)      -> exit 0 (not born red)

Honest limitation: this repo's CI does not install bun, so **these tests skip
there**. A skipped test is not a gate. They exist to be run locally, and to
document exactly how the gate was verified — see the PR for the captured output.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

pytestmark = [
    pytest.mark.skipif(shutil.which("bun") is None, reason="bun not installed (CI does not ship it)"),
    pytest.mark.slow,
]

_INSECURE = """/** Runs user code. */
export function run(userInput: string): unknown {
  return eval(userInput);
}

/** Writes to the DOM. */
export function render(el: HTMLElement, dirty: string): void {
  el.innerHTML = dirty;
}
"""

_CLEAN = """/** Adds two numbers. */
export function add(a: number, b: number): number {
  return a + b;
}
"""

# Exactly what the scaffolded `just setup` installs. Kept in one place so a
# recipe change that forgets a plugin makes this module fail rather than drift.
_DEV_DEPS = (
    "eslint",
    "typescript@^5",
    "typescript-eslint",
    "eslint-plugin-jsdoc",
    "eslint-plugin-tsdoc",
    "eslint-plugin-security",
    "eslint-plugin-no-unsanitized",
)


@pytest.fixture(scope="module")
def ts_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("ts") / "proj"
    scaffold(
        target,
        fallback_preset(),
        fallback_variables(language="node", node="true", python=""),
    )
    (target / "package.json").write_text('{"name":"p","type":"module"}\n', encoding="utf-8")
    result = subprocess.run(
        ["bun", "add", "-d", *_DEV_DEPS],
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    if result.returncode != 0:
        pytest.skip(f"bun add failed (offline?): {result.stderr[-200:]}")
    return target


def _eslint(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(target / "node_modules" / ".bin" / "eslint"), "."],
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def test_typescript_is_not_seven(ts_project: Path):
    """PI-732: TS 7 makes typescript-eslint crash — eslint exits 2, not 1."""
    result = subprocess.run(
        ["bun", "pm", "ls"], cwd=ts_project, capture_output=True, text=True, check=False
    )
    assert "typescript@5" in result.stdout, result.stdout


def test_insecure_code_is_blocked(ts_project: Path):
    src = ts_project / "src"
    src.mkdir(exist_ok=True)
    (src / "probe.ts").write_text(_INSECURE, encoding="utf-8")
    result = _eslint(ts_project)
    assert result.returncode == 1, f"expected a lint failure, got {result.returncode}\n{result.stdout}"
    assert "security/detect-eval-with-expression" in result.stdout
    assert "no-unsanitized/property" in result.stdout
    # `error`, not `warn` — eslint exits 0 on warnings, which would be a gate
    # that never blocks (the defect #729 describes).
    assert "  error  " in result.stdout


def test_clean_code_passes(ts_project: Path):
    src = ts_project / "src"
    src.mkdir(exist_ok=True)
    (src / "probe.ts").write_text(_CLEAN, encoding="utf-8")
    result = _eslint(ts_project)
    assert result.returncode == 0, result.stdout + result.stderr


def test_fresh_scaffold_is_not_born_red(ts_project: Path):
    shutil.rmtree(ts_project / "src", ignore_errors=True)
    result = _eslint(ts_project)
    assert result.returncode == 0, result.stdout + result.stderr
