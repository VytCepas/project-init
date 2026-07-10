"""PI-725: the scaffolded rust lint gate must see test code.

Contract tests assert the *text* of the justfile. That is the weak class this
repo keeps getting burned by (#732: every TS test asserted config text while the
toolchain crashed). So this module runs the real thing.

Measured against clippy 0.1.97, a `tests/*.rs` containing an outright type error:

    cargo clippy                 -- ...   -> exit 0   (never sees tests/)
    cargo clippy --all-targets   -- ...   -> exit 101

And `-D missing_docs` cannot be combined with `--all-targets`: it then demands a
crate-level `//!` in every integration test file, which would make a clean
project red. Hence the two-pass recipe.

Honest limitation: skips where cargo is absent — including this repo's CI, which
installs no rust toolchain. A skipped test is not a gate; see #733 for the same
problem with bun, and the PR for the captured local output.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.skipif(shutil.which("cargo") is None, reason="no rust toolchain (CI ships none)"),
    pytest.mark.slow,
]

_CLEAN_LIB = '//! Probe.\n\n/// Adds two numbers.\n#[must_use]\npub fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n'
_CLEAN_TEST = "#[test]\nfn t() {\n    assert_eq!(probe::add(1, 2), 3);\n}\n"
# A type error, not a style nit: `&str` where `i32` is required.
_BROKEN_TEST = '#[test]\nfn t() {\n    let x: i32 = "not an integer";\n    assert_eq!(probe::add(1, 2), x);\n}\n'

_GATES = ["-D", "warnings", "-D", "clippy::pedantic", "-D", "clippy::cognitive_complexity"]
_DOCS = ["-D", "missing_docs"]

# Pass 1: docs enforced, default targets only.
_DOCS_PASS = ["cargo", "clippy", "--all-features", "--", *_GATES, *_DOCS]
# Pass 2: every target, no doc requirement (see the module docstring).
_ALL_TARGETS_PASS = ["cargo", "clippy", "--all-targets", "--all-features", "--", *_GATES]
# What the scaffold ran before #725 — kept to prove the bug was real.
_OLD_RECIPE = ["cargo", "clippy", "--", *_GATES, *_DOCS]
_TYPECHECK = ["cargo", "check", "--all-targets", "--all-features"]


@pytest.fixture(scope="module")
def crate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("crate")
    subprocess.run(["cargo", "init", "--name", "probe", "--lib", "-q"], cwd=root, check=True)
    (root / "src" / "lib.rs").write_text(_CLEAN_LIB, encoding="utf-8")
    (root / "tests").mkdir(exist_ok=True)
    return root


def _run(argv: list[str], crate: Path) -> int:
    return subprocess.run(argv, cwd=crate, capture_output=True, text=True, timeout=900).returncode


def test_old_recipe_never_saw_a_broken_test(crate: Path):
    """The bug: exit 0 on a test that does not even type-check."""
    (crate / "tests" / "probe.rs").write_text(_BROKEN_TEST, encoding="utf-8")
    assert _run(_OLD_RECIPE, crate) == 0, "expected the old recipe to miss it — has clippy changed?"


def test_all_targets_pass_catches_a_broken_test(crate: Path):
    (crate / "tests" / "probe.rs").write_text(_BROKEN_TEST, encoding="utf-8")
    assert _run(_ALL_TARGETS_PASS, crate) != 0


def test_clean_crate_passes_both_passes(crate: Path):
    """A clean project must not be born red."""
    (crate / "tests" / "probe.rs").write_text(_CLEAN_TEST, encoding="utf-8")
    assert _run(_DOCS_PASS, crate) == 0
    assert _run(_ALL_TARGETS_PASS, crate) == 0


def test_missing_docs_with_all_targets_would_break_a_clean_crate(crate: Path):
    """Why the recipe is two passes: `-D missing_docs` + `--all-targets` demands
    a crate-level `//!` in every tests/*.rs.
    """
    (crate / "tests" / "probe.rs").write_text(_CLEAN_TEST, encoding="utf-8")
    combined = [*_ALL_TARGETS_PASS, "-D", "missing_docs"]
    assert _run(combined, crate) != 0, "if this passes, the two-pass split is no longer needed"


def test_typecheck_recipe_catches_a_broken_test(crate: Path):
    (crate / "tests" / "probe.rs").write_text(_BROKEN_TEST, encoding="utf-8")
    assert _run(_TYPECHECK, crate) != 0
    (crate / "tests" / "probe.rs").write_text(_CLEAN_TEST, encoding="utf-8")
    assert _run(_TYPECHECK, crate) == 0
