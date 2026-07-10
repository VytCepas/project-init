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

CI installs bun (`ci.yml`, `Install Bun`), so these tests RUN there. If bun ever
goes missing from the runner the guard below fails rather than skips: a skipped
test is not a gate, and this module is the only one that exercises the TS
toolchain instead of describing it (#733). Locally, a missing bun skips.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

pytestmark = [pytest.mark.slow]


def _require_bun() -> None:
    """Fail in CI, skip locally, when bun is absent.

    `skipif` would let a runner that quietly stopped installing bun report green
    forever — the same failure shape as #719, where the actionlint gate skipped
    in CI until actionlint became a declared dev dependency.
    """
    if shutil.which("bun") and shutil.which("bunx"):
        return
    message = "bun/bunx not on PATH"
    if os.environ.get("CI"):
        pytest.fail(
            f"{message} — CI must install bun (ci.yml `Install Bun`) or this gate "
            "silently tests nothing (#733)."
        )
    pytest.skip(f"{message} — install bun to run the TS toolchain gate locally")

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
    "@biomejs/biome",
)


def test_dev_deps_match_the_scaffolded_setup_recipe(tmp_path: Path):
    """_DEV_DEPS claims to be "exactly what `just setup` installs" — prove it.

    It silently omitted @biomejs/biome (PR #731 review). A drifting copy of the
    toolchain makes the behavioral tests exercise something the scaffold does not
    ship.
    """
    from project_init.scaffold import scaffold as _scaffold

    target = tmp_path / "n"
    _scaffold(target, fallback_preset(), fallback_variables(language="node", node="true", python=""))
    setup = (target / "justfile").read_text(encoding="utf-8").split("\nsetup:", 1)[1]
    setup = setup.split("\n\n", 1)[0]
    command = " ".join(
        ln.strip().rstrip("\\")
        for ln in setup.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    )
    installed = {tok.strip('"') for tok in command.split() if tok not in ("bun", "add", "-d")}
    assert installed == set(_DEV_DEPS), (
        f"_DEV_DEPS drifted from `just setup`\n  only in recipe: "
        f"{sorted(installed - set(_DEV_DEPS))}\n  only in test:   {sorted(set(_DEV_DEPS) - installed)}"
    )


@pytest.fixture(scope="module")
def ts_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    _require_bun()
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
        # Skip ONLY for a network failure. A dependency conflict, a bad package
        # name, or an unsatisfiable range is exactly the regression these tests
        # exist to catch — skipping there would hide it behind a green run
        # (PR #731 review, Codex P2).
        stderr = result.stderr.lower()
        offline = any(
            token in stderr
            for token in ("getaddrinfo", "enotfound", "econnrefused", "network", "timed out")
        )
        if offline:
            pytest.skip(f"npm registry unreachable: {result.stderr[-200:]}")
        raise AssertionError(
            "`bun add` failed for a non-network reason — the scaffolded dev-dep "
            f"set is broken:\n{result.stdout}\n{result.stderr}"
        )
    return target


def _eslint(target: Path, *extra: str) -> subprocess.CompletedProcess:
    # `bunx eslint .` — byte-for-byte what the scaffolded `just lint` runs
    # (justfile.tmpl). Not node_modules/.bin/eslint: that shim is a shell script
    # on POSIX and a .cmd/.ps1 on Windows (PR #731 review).
    return subprocess.run(
        ["bunx", "eslint", ".", *extra],
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def _severities(target: Path) -> dict[str, int]:
    """Map ruleId -> max severity eslint reported (1 = warn, 2 = error).

    Exit code alone cannot tell a downgraded rule from an enforced one: the probe
    trips several rules, so one surviving `error` keeps the exit at 1 while
    another has silently become a `warn`. That gap let this module stay green
    against a downgraded `detect-eval-with-expression` (#733). The JSON formatter
    is eslint's stable machine surface — unlike the text formatter's column
    spacing, which is what PR #731 rightly declined to assert on.
    """
    result = _eslint(target, "-f", "json")
    report = json.loads(result.stdout)
    severities: dict[str, int] = {}
    for file_report in report:
        for message in file_report["messages"]:
            rule = message.get("ruleId")
            if rule:
                severities[rule] = max(severities.get(rule, 0), message["severity"])
    return severities


def test_typescript_is_not_seven(ts_project: Path):
    """PI-732: TS 7 makes typescript-eslint crash — eslint exits 2, not 1."""
    result = subprocess.run(
        ["bun", "pm", "ls"],
        cwd=ts_project,
        capture_output=True,
        text=True,
        check=False,
        # Every other bun subprocess here is bounded; a hung `pm ls` would stall
        # the whole pytest run (PR #731 review).
        timeout=600,
    )
    assert "typescript@5" in result.stdout, result.stdout


def test_insecure_code_is_blocked(ts_project: Path):
    src = ts_project / "src"
    src.mkdir(exist_ok=True)
    (src / "probe.ts").write_text(_INSECURE, encoding="utf-8")
    result = _eslint(ts_project)
    assert result.returncode == 1, (
        f"expected a lint failure (1), got {result.returncode} — exit 2 means an eslint "
        f"crash, the #732 regression\n{result.stdout}\n{result.stderr}"
    )
    # Severity per rule, not just the exit code. Both rules must be `error`:
    # with several rules tripping at once, one left at `error` masks another
    # downgraded to `warn` and the exit code stays 1 either way (#733).
    severities = _severities(ts_project)
    for rule in ("security/detect-eval-with-expression", "no-unsanitized/property"):
        assert severities.get(rule) == 2, (
            f"{rule} reported severity {severities.get(rule)!r}, expected 2 (error). "
            f"A security rule downgraded to `warn` does not block a merge.\n{severities}"
        )


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
