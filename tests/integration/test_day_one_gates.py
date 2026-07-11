"""PI-781: a freshly scaffolded go/rust project must be day-one green.

No `go.mod`/`Cargo.toml` is scaffolded (like node has no `package.json`), so
every recipe that shells out to the toolchain must skip cleanly until the user
runs `go mod init` / `cargo init`. Before this guard, `just test` ran
`go test ./...` / `cargo test` unconditionally and a fresh rust scaffold's `just
ci` (`cargo check` in `typecheck`) was day-one CI red, while go's `just fast-ci`
(`go test ./...`) failed the pre-push hook.

Contract tests assert the *text* of the justfile — the weak class this repo
keeps getting burned by (#732/#734). So this module runs the real `just`
recipes. It needs only `just`: every day-one recipe short-circuits *before*
calling go/cargo, so the guards are exercised without any language toolchain
installed. That is also why it would fail on the old code — `go test`/`cargo
test` would run and error (missing module, or command-not-found).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _require_just() -> None:
    """Fail in CI, skip locally, when `just` is absent — a skipped test is not a
    gate (#737). ci.yml installs `just`, so a missing one is a broken workflow.
    """
    if shutil.which("just"):
        return
    if os.environ.get("CI"):
        pytest.fail("just is not on PATH — CI must install it (ci.yml) or this gate tests nothing (#737).")
    pytest.skip("just not available — install it to run this gate locally")


def _scaffold(target: Path, language: str) -> None:
    flags = {"language": language, "python": "", language: "true"}
    scaffold(target, load_preset("core"), make_variables(**flags))


def _run(target: Path, *recipe: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["just", *recipe],
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


# (recipe, substring the day-one skip must print). Excludes `lint`, which also
# runs shellcheck/shfmt/lint_context_budget — covered by the `ci`/`fast-ci`
# aggregate assertions below.
_GO_SKIPS = [
    ("setup", "No Go sources yet"),
    ("typecheck", "No Go sources yet"),
    ("test", "No Go sources yet"),
    ("test-quick", "No Go sources yet"),
    ("test-cov", "No Go sources yet"),
    ("audit", "No Go sources yet"),
]
_RUST_SKIPS = [
    ("setup", "No Cargo project yet"),
    ("build", "No Cargo project yet"),
    ("typecheck", "No Cargo project yet"),
    ("test", "No Cargo project yet"),
    ("test-quick", "No Cargo project yet"),
    ("test-cov", "No Cargo project yet"),
    ("audit", "No Cargo project yet"),
]


@pytest.mark.parametrize("recipe, marker", _GO_SKIPS)
def test_go_recipe_skips_cleanly_day_one(tmp_path: Path, recipe: str, marker: str) -> None:
    _require_just()
    target = tmp_path / "go-proj"
    _scaffold(target, "go")
    result = _run(target, recipe)
    assert result.returncode == 0, f"just {recipe} failed day-one:\n{result.stdout}\n{result.stderr}"
    assert marker in result.stdout, f"just {recipe} did not skip cleanly:\n{result.stdout}"


@pytest.mark.parametrize("recipe, marker", _RUST_SKIPS)
def test_rust_recipe_skips_cleanly_day_one(tmp_path: Path, recipe: str, marker: str) -> None:
    _require_just()
    target = tmp_path / "rust-proj"
    _scaffold(target, "rust")
    result = _run(target, recipe)
    assert result.returncode == 0, f"just {recipe} failed day-one:\n{result.stdout}\n{result.stderr}"
    assert marker in result.stdout, f"just {recipe} did not skip cleanly:\n{result.stdout}"


@pytest.mark.parametrize("language", ["go", "rust"])
@pytest.mark.parametrize("recipe", ["ci", "fast-ci"])
def test_aggregate_gate_is_day_one_green(tmp_path: Path, language: str, recipe: str) -> None:
    """The capstone: `just ci` (the full gate) and `just fast-ci` (the pre-push
    hook) must both pass on a fresh scaffold, with no toolchain and no init.
    """
    _require_just()
    target = tmp_path / f"{language}-proj"
    _scaffold(target, language)
    result = _run(target, recipe)
    assert result.returncode == 0, f"{language} just {recipe} was day-one red:\n{result.stdout}\n{result.stderr}"
