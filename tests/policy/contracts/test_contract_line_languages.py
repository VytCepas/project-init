"""#1054: the Node, Go and Rust templates' `just test` ends with the contract line.

Test contract rule 3: `<suite>: N passed, M failed` is the last line, and the
exit code is the runner's own. Each case scaffolds a repo, plants one passing
and one failing test, runs the real `just test`, and reads the last line.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

LINE = re.compile(r"^[A-Za-z0-9._-]+: [0-9]+ passed, [0-9]+ failed$")

BUN_TESTS = (
    'import { test, expect } from "bun:test";\n'
    'test("ok", () => { expect(1).toBe(1); });\n'
    'test("skipped", () => {});\n'
)
GO_TESTS = (
    'package p\n\nimport "testing"\n\n'
    "func TestOK(t *testing.T) {}\n"
    'func TestSub(t *testing.T) { t.Run("a", func(t *testing.T) {}) }\n'
)
RUST_LIB = "pub fn one() -> i32 { 1 }\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn ok() { assert_eq!(super::one(), 1); }\n"


def _scaffold(tmp_path: Path, language: str) -> Path:
    target = tmp_path / language
    scaffold(
        target,
        load_preset("core"),
        make_variables(language=language, python="", **{language: "true"}),
    )
    return target


def _just_test(target: Path, env: dict[str, str] | None = None) -> tuple[str, int]:
    proc = _just_test_full(target, env)
    lines = proc.stdout.strip().splitlines()
    return (lines[-1] if lines else ""), proc.returncode


def _just_test_full(
    target: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    if shutil.which("just") is None:
        pytest.skip("just is not on PATH")
    return subprocess.run(
        ["just", "test"],
        cwd=target,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        timeout=600,
        check=False,
    )


def _need(tool: str) -> None:
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} is not on PATH")


class TestNode:
    def _repo(self, tmp_path: Path, failing: bool) -> Path:
        _need("bun")
        target = _scaffold(tmp_path, "node")
        body = BUN_TESTS.replace('test("skipped"', 'test.skip("skipped"')
        if failing:
            body += 'test("bad", () => { expect(1).toBe(2); });\n'
        (target / "src").mkdir(exist_ok=True)
        (target / "src" / "a.test.ts").write_text(body)
        return target

    def test_one_pass_one_fail(self, tmp_path: Path) -> None:
        last, code = _just_test(self._repo(tmp_path, failing=True))
        assert (last, code) == ("my-project: 1 passed, 1 failed", 1)

    def test_all_pass(self, tmp_path: Path) -> None:
        last, code = _just_test(self._repo(tmp_path, failing=False))
        assert (last, code) == ("my-project: 1 passed, 0 failed", 0)

    def test_a_test_that_prints_summary_lookalikes_is_not_counted(self, tmp_path: Path) -> None:
        """#1076 review: a test's own `100 pass` / `7 errors` stdout is not bun's summary."""
        target = self._repo(tmp_path, failing=False)
        (target / "src" / "b.test.ts").write_text(
            'import { test } from "bun:test";\n'
            'test("chatty", () => { console.log("100 pass"); console.log("7 errors"); });\n'
        )
        last, code = _just_test(target)
        assert (last, code) == ("my-project: 2 passed, 0 failed", 0)


class TestGo:
    def _repo(self, tmp_path: Path, failing: bool) -> Path:
        _need("go")
        target = _scaffold(tmp_path, "go")
        (target / "go.mod").write_text("module example.com/p\n\ngo 1.21\n")
        body = GO_TESTS
        if failing:
            body += 'func TestBad(t *testing.T) { t.Log("why"); t.Fatal("boom") }\n'
        (target / "p_test.go").write_text(body)
        return target

    def test_one_pass_one_fail(self, tmp_path: Path) -> None:
        last, code = _just_test(self._repo(tmp_path, failing=True), {"GOTOOLCHAIN": "local"})
        assert (last, code) == ("my-project: 2 passed, 1 failed", 1)

    def test_all_pass(self, tmp_path: Path) -> None:
        last, code = _just_test(self._repo(tmp_path, failing=False), {"GOTOOLCHAIN": "local"})
        assert (last, code) == ("my-project: 2 passed, 0 failed", 0)

    def test_a_failing_subtest_keeps_its_log_and_counts_once(self, tmp_path: Path) -> None:
        """#1076 review: `TestSub/bad`'s assertion line is printed; only the parent counts."""
        target = self._repo(tmp_path, failing=False)
        (target / "p_test.go").write_text(
            GO_TESTS + 'func TestTable(t *testing.T) {\n\tt.Run("bad", func(t *testing.T) {'
            ' t.Errorf("got 1 want 2") })\n}\n'
        )
        proc = _just_test_full(target, {"GOTOOLCHAIN": "local"})
        assert "got 1 want 2" in proc.stdout
        assert proc.stdout.strip().splitlines()[-1] == "my-project: 2 passed, 1 failed"
        assert proc.returncode == 1

    def test_a_build_error_is_a_run_that_did_not_finish(self, tmp_path: Path) -> None:
        target = self._repo(tmp_path, failing=False)
        (target / "p_test.go").write_text("package p\n\nfunc broken( {\n")
        last, code = _just_test(target, {"GOTOOLCHAIN": "local"})
        assert last == "my-project: 0 passed, 0 failed"
        assert code == 1


def _rustup_toolchain() -> dict[str, str]:
    """Name a toolchain for the rustup proxy: conftest's isolated RUSTUP_HOME has no
    settings.toml, so without one `cargo` exits 1 ("no default is configured")."""
    toolchains = Path(os.environ.get("RUSTUP_HOME", "")) / "toolchains"
    names = sorted(p.name for p in toolchains.iterdir()) if toolchains.is_dir() else []
    pick = next((n for n in names if n.startswith("stable")), names[0] if names else "")
    return {"RUSTUP_TOOLCHAIN": pick} if pick else {}


class TestRust:
    def _repo(self, tmp_path: Path, failing: bool) -> Path:
        target = _scaffold(tmp_path, "rust")
        (target / "Cargo.toml").write_text(
            '[package]\nname = "p"\nversion = "0.1.0"\nedition = "2021"\n'
        )
        (target / "src").mkdir(exist_ok=True)
        body = RUST_LIB
        if failing:
            body += "    #[test]\n    fn bad() { assert_eq!(super::one(), 2); }\n"
        (target / "src" / "lib.rs").write_text(body + "}\n")
        return target

    def test_one_pass_one_fail_real_cargo(self, tmp_path: Path) -> None:
        _need("cargo")
        last, code = _just_test(self._repo(tmp_path, failing=True), _rustup_toolchain())
        assert (last, code) == ("my-project: 1 passed, 1 failed", 101)

    def test_one_pass_one_fail_stub_cargo(self, tmp_path: Path) -> None:
        """cargo's documented `test result:` lines (lib + doc-tests), exit 101,
        through the real recipe, for hosts without a Rust toolchain."""
        target = self._repo(tmp_path, failing=True)
        stub = tmp_path / "stub"
        stub.mkdir()
        (stub / "cargo").write_text(
            "#!/bin/sh\n"
            "echo 'running 2 tests'\n"
            "echo 'test tests::ok ... ok'\n"
            "echo 'test tests::bad ... FAILED'\n"
            "echo 'test result: FAILED. 1 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out'\n"
            "echo '   Doc-tests p' >&2\n"
            "echo 'test result: ok. 2 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out'\n"
            "exit 101\n"
        )
        (stub / "cargo").chmod(0o755)
        last, code = _just_test(target, {"PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"})
        assert (last, code) == ("my-project: 3 passed, 1 failed", 101)

    def test_a_failing_tests_printed_summary_is_not_counted(self, tmp_path: Path) -> None:
        """#1076 review: cargo echoes a failing test's stdout verbatim; a `test result:`
        line in it is not a harness summary. Stub mirrors cargo's failure report."""
        target = self._repo(tmp_path, failing=True)
        stub = tmp_path / "stub"
        stub.mkdir()
        (stub / "cargo").write_text(
            "#!/bin/sh\n"
            "echo 'running 1 test'\n"
            "echo 'test tests::bad ... FAILED'\n"
            "echo ''\n"
            "echo 'failures:'\n"
            "echo ''\n"
            "echo '---- tests::bad stdout ----'\n"
            "echo 'test result: ok. 100 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out'\n"
            "echo 'thread panicked at src/lib.rs:1:1'\n"
            "echo ''\n"
            "echo 'failures:'\n"
            "echo '    tests::bad'\n"
            "echo ''\n"
            "echo 'test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out'\n"
            "exit 101\n"
        )
        (stub / "cargo").chmod(0o755)
        last, code = _just_test(target, {"PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"})
        assert (last, code) == ("my-project: 0 passed, 1 failed", 101)


@pytest.mark.parametrize("language", ["node", "go", "rust"])
def test_no_tests_yet_still_ends_with_the_line(tmp_path: Path, language: str) -> None:
    last, code = _just_test(_scaffold(tmp_path, language))
    assert (last, code) == ("my-project: 0 passed, 0 failed", 0)
    assert LINE.match(last)
