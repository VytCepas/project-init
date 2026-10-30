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

REPO = Path(__file__).resolve().parents[3]
_CONTRACT_VARS = {
    "CLAUDE_CONFIG_DIR",
    "UV_CACHE_DIR",
    "UV_PYTHON_INSTALL_DIR",
    "UV_TOOL_DIR",
    "CARGO_HOME",
    "RUSTUP_HOME",
    "GOPATH",
    "GOCACHE",
    "GOMODCACHE",
    "BUN_INSTALL",
    "BUN_INSTALL_CACHE_DIR",
    "UV_PYTHON_BIN_DIR",
    "UV_TOOL_BIN_DIR",
    "GOBIN",
    "TEMP",
    "TMP",
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

# Each read happens before any function-scoped fixture: at import, at collection,
# in a broader-scoped fixture.
_PLANTED_EARLY_CONFTEST = """\
from pathlib import Path

import pytest

AT_CONFTEST_IMPORT = (Path.home(),)


@pytest.fixture(scope="session")
def session_home():
    return (Path.home(),)


@pytest.fixture(scope="session")
def conftest_import_home():
    return AT_CONFTEST_IMPORT
"""

_PLANTED_EARLY = """\
import os
from pathlib import Path

import pytest

AT_COLLECTION = (Path.home(),)


@pytest.fixture(scope="module")
def module_home():
    return (Path.home(),)


def _real(*homes):
    real = Path(os.environ["REAL_HOME"])
    return [str(home) for home in homes if Path(home).is_relative_to(real)]


def test_a_module_level_read_at_collection():
    assert _real(*AT_COLLECTION) == []


def test_a_read_at_tests_conftest_import(conftest_import_home):
    assert _real(*conftest_import_home) == []


def test_a_session_fixture_read(session_home):
    assert _real(*session_home) == []


def test_a_module_fixture_read(module_home):
    assert _real(*module_home) == []


def test_each_test_still_gets_a_home_of_its_own(session_home):
    assert Path.home() != session_home[0]
"""

_PLANTED_CARGO = """\
import os
from pathlib import Path


def test_cargo_home_is_not_the_real_one():
    real = Path(os.environ["REAL_HOME"]) / ".cargo"
    assert Path(os.environ["CARGO_HOME"]) != real


def test_cargo_config_and_credentials_are_not_reachable():
    fake = Path(os.environ["CARGO_HOME"])
    assert not (fake / "credentials.toml").exists()
    assert not (fake / "config.toml").exists()


def test_cargo_registry_cache_is_still_reused():
    fake = Path(os.environ["CARGO_HOME"])
    assert (fake / "registry" / "marker.txt").read_text() == "cached\\n"
"""

_PLANTED_RUSTUP = """\
import os
from pathlib import Path


def test_rustup_home_is_not_the_real_one():
    real = Path(os.environ["REAL_HOME"]) / ".rustup"
    assert Path(os.environ["RUSTUP_HOME"]) != real


def test_rustup_settings_are_not_reachable():
    fake = Path(os.environ["RUSTUP_HOME"])
    assert not (fake / "settings.toml").exists()


def test_rustup_toolchains_and_downloads_are_still_reused():
    fake = Path(os.environ["RUSTUP_HOME"])
    assert (fake / "toolchains" / "marker.txt").read_text() == "cached\\n"
    assert (fake / "downloads" / "marker.txt").read_text() == "cached\\n"
"""

_PLANTED_PREEXISTING = """\
import os


def test_cargo_home_overrides_the_inherited_export():
    assert os.environ["CARGO_HOME"] != os.environ["DECOY_CARGO_HOME"]


def test_rustup_home_overrides_the_inherited_export():
    assert os.environ["RUSTUP_HOME"] != os.environ["DECOY_RUSTUP_HOME"]
"""

# #1065: a pre-push hook exports GIT_DIR (and more) into the suite it runs.
_PLANTED_GIT_SANDBOX = """\
import os
import subprocess


def test_git_in_tmp_path_acts_on_tmp_path(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.name", "t")
    git("config", "user.email", "t@example.com")
    git("commit", "-q", "--allow-empty", "-m", "init")
    assert (tmp_path / ".git").is_dir()


def test_no_hook_git_variable_reaches_a_test():
    assert [v for v in os.environ["HOOK_VARS"].split() if v in os.environ] == []
"""

_PLANTED_TEMP_TMP = """\
import os


def test_temp_matches_tmpdir():
    assert os.environ["TEMP"] == os.environ["TMPDIR"]


def test_tmp_matches_tmpdir():
    assert os.environ["TMP"] == os.environ["TMPDIR"]
"""

_PLANTED_INSTALL_ROOTS = """\
import os
from pathlib import Path


def _under_real_home(var):
    return Path(os.environ[var]).is_relative_to(Path(os.environ["REAL_HOME"]))


def test_python_install_dir_is_not_the_real_home():
    assert not _under_real_home("UV_PYTHON_INSTALL_DIR")


def test_tool_dir_is_not_the_real_home():
    assert not _under_real_home("UV_TOOL_DIR")


def test_gopath_is_not_the_real_home():
    assert not _under_real_home("GOPATH")


def test_bun_install_is_not_the_real_home():
    assert not _under_real_home("BUN_INSTALL")


def test_gomodcache_stays_real():
    assert _under_real_home("GOMODCACHE")


def test_bun_install_cache_dir_stays_real():
    assert _under_real_home("BUN_INSTALL_CACHE_DIR")
"""

_PLANTED_INHERITED_SOURCE = """\
import os
from pathlib import Path


def test_cargo_cache_comes_from_the_inherited_cargo_home():
    fake = Path(os.environ["CARGO_HOME"])
    assert (fake / "registry" / "marker.txt").read_text() == "custom-cargo\\n"


def test_rustup_cache_comes_from_the_inherited_rustup_home():
    fake = Path(os.environ["RUSTUP_HOME"])
    assert (fake / "toolchains" / "marker.txt").read_text() == "custom-rustup\\n"
"""

# #1062: a runner that exports an install root (bun's installer adds BUN_INSTALL
# to the shell profile) must not get it back inside a test.
_PLANTED_EXPORTED_ROOTS = """\
import os
import subprocess
from pathlib import Path

import pytest

REAL = Path(os.environ["REAL_HOME"])
ROOTS = (
    "UV_PYTHON_INSTALL_DIR", "UV_PYTHON_BIN_DIR", "UV_TOOL_DIR", "UV_TOOL_BIN_DIR",
    "GOPATH", "BUN_INSTALL", "XDG_BIN_HOME",
)


@pytest.mark.parametrize("var", ROOTS)
def test_an_exported_install_root_still_moves(var):
    assert not Path(os.environ[var]).is_relative_to(REAL), os.environ[var]


def test_an_exported_gobin_is_dropped():
    assert "GOBIN" not in os.environ, os.environ.get("GOBIN")


def test_caches_follow_the_runners_own_roots():
    assert os.environ["GOMODCACHE"] == str(REAL / "custom-go" / "pkg" / "mod")
    assert os.environ["BUN_INSTALL_CACHE_DIR"] == str(REAL / "custom-bun" / "install" / "cache")


@pytest.mark.parametrize("args", ["tool dir", "tool dir --bin", "python dir", "python dir --bin"])
def test_uv_itself_resolves_outside_the_real_home(args):
    out = subprocess.run(["uv", *args.split()], capture_output=True, text=True, check=True)
    assert not Path(out.stdout.strip()).is_relative_to(REAL), out.stdout
"""

# #1069: Go refuses a cross-compiled `go install` while GOBIN is set.
_PLANTED_GO_CROSS = """\
import os
import subprocess
from pathlib import Path


def test_a_cross_compiled_go_install_lands_in_the_isolated_gopath(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/hello\\n\\ngo 1.21\\n")
    (tmp_path / "main.go").write_text("package main\\n\\nfunc main() {}\\n")
    env = {**os.environ, "GOOS": "windows", "GOTOOLCHAIN": "local"}
    result = subprocess.run(
        ["go", "install", "."], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert list((Path(os.environ["GOPATH"]) / "bin").rglob("hello*"))
"""

_PLANTED_IMPORTS_CONFTEST = """\
import json

import pytest
from conftest import helper


def test_helper():
    assert helper() == json.loads("1")
    assert pytest
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


# The worker cap (PR #1104), asked through the whole `-n auto` hook chain of a
# scaffolded repo: xdist's own hook, the root conftest's wrapper, and a tryfirst
# plugin answering what xdist answered on the runner that failed (8). Memory cases
# sit on both sides of a 512 MiB multiple as literals, never as `_WORKER_BYTES * n`.
_PLANTED_WORKER_CAP = """\
from pathlib import Path

import pytest

RUNNER = {"cpu.max": "100000 100000", "memory.max": "1073741824"}
TOP = "0::/\\n"
CASES = [
    ("runner", RUNNER, TOP, 1),
    ("unlimited", {"cpu.max": "max 100000", "memory.max": "max"}, TOP, 8),
    ("half-cpu", {"cpu.max": "50000 100000"}, TOP, 1),
    ("one-and-a-half-cpus", {"cpu.max": "150000 100000"}, TOP, 1),
    ("two-cpus", {"cpu.max": "200000 100000"}, TOP, 2),
    ("512MiB-less-1", {"memory.max": "536870911"}, TOP, 1),
    ("1GiB-less-1", {"memory.max": "1073741823"}, TOP, 1),
    ("1GiB", {"memory.max": "1073741824"}, TOP, 2),
    ("1.5GiB-less-1", {"memory.max": "1610612735"}, TOP, 2),
    ("1.5GiB", {"memory.max": "1610612736"}, TOP, 3),
    ("2GiB", {"memory.max": "2147483648"}, TOP, 4),
    ("ancestor", {"a/cpu.max": "200000 100000", "a/b/cpu.max": "max 100000"}, "0::/a/b\\n", 2),
    ("cpu-child-tighter", {"cpu.max": "400000 100000", "a/cpu.max": "100000 100000"}, "0::/a\\n", 1),
    ("cpu-parent-tighter", {"cpu.max": "100000 100000", "a/cpu.max": "400000 100000"}, "0::/a\\n", 1),
    ("mem-child-tighter", {"memory.max": "2147483648", "a/memory.max": "1073741824"}, "0::/a\\n", 2),
    ("mem-parent-tighter", {"memory.max": "1073741824", "a/memory.max": "2147483648"}, "0::/a\\n", 2),
    ("never-raises-cpus", {"cpu.max": "1600000 100000"}, TOP, 8),
    ("never-raises-memory", {"memory.max": "17179869184"}, TOP, 8),
    ("garbage", {"cpu.max": "abc 100000", "memory.max": "lots"}, TOP, 8),
    ("zero-period", {"cpu.max": "100000 0"}, TOP, 8),
    ("no-period", {"cpu.max": "100000"}, TOP, 8),
    ("above-the-root", {"../cpu.max": "100000 100000"}, TOP, 8),
    ("cgroup-v1", RUNNER, "12:memory:/docker/abc\\n4:cpu,cpuacct:/docker/abc\\n", 8),
    ("not-utf8", RUNNER, b"0::/caf\\xe9.scope\\n", 8),
    ("no-proc-file", RUNNER, None, 8),
]


class EightCpus:
    @pytest.hookimpl(tryfirst=True)
    def pytest_xdist_auto_num_workers(self):
        return 8


def root_conftest(config):
    want = (config.rootpath / "conftest.py").resolve()
    for plugin in config.pluginmanager.get_plugins():
        if Path(getattr(plugin, "__file__", None) or "-").resolve() == want:
            return plugin
    raise AssertionError("the root conftest is not registered")


@pytest.fixture
def auto(pytestconfig, tmp_path, monkeypatch):
    hook = pytestconfig.hook.pytest_xdist_auto_num_workers
    assert hook.spec is not None, "xdist is not loaded, so this run proves nothing"
    module = root_conftest(pytestconfig)
    monkeypatch.delenv("PYTEST_XDIST_AUTO_NUM_WORKERS", raising=False)

    def ask(files, own=TOP, xdist_says=8):
        root = tmp_path / "cgroup"
        root.mkdir()
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text + "\\n")
        proc = tmp_path / "proc-self-cgroup"
        if own is not None:
            proc.write_bytes(own if isinstance(own, bytes) else own.encode())
        monkeypatch.setattr(module, "_CGROUP_ROOT", root)
        monkeypatch.setattr(module, "_PROC_SELF_CGROUP", proc)
        plugin = EightCpus() if xdist_says == 8 else None
        if plugin is not None:
            pytestconfig.pluginmanager.register(plugin, "planted-eight-cpus")
        try:
            return hook(config=pytestconfig)
        finally:
            if plugin is not None:
                pytestconfig.pluginmanager.unregister(plugin)

    return ask


@pytest.mark.parametrize(("files", "own", "workers"), [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_auto(auto, files, own, workers):
    assert auto(files, own) == workers


def test_an_explicit_count_stands(auto, monkeypatch):
    monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", "6")
    assert auto(RUNNER, xdist_says=None) == 6


@pytest.mark.parametrize("value", ["", "abc", "auto"])
def test_a_count_xdist_ignores_is_still_capped(auto, monkeypatch, value):
    monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", value)
    assert auto(RUNNER) == 1


def test_the_kernels_files_are_read_by_default(pytestconfig):
    module = root_conftest(pytestconfig)
    assert module._CGROUP_ROOT == Path("/sys/fs/cgroup")
    assert module._PROC_SELF_CGROUP == Path("/proc/self/cgroup")
"""
# CASES, the explicit count, three ignored counts, the default paths.
_WORKER_CAP_TESTS = 25 + 1 + 3 + 1

# A `-p` plugin, so it is registered before the root conftest: it points the
# conftest at a fake cgroup the moment pytest registers it, answers 8 as xdist did
# on the runner, and prints the count xdist's own (tryfirst) pytest_cmdline_main
# settled on before ending the run ahead of collection.
_WORKER_PROBE = """\
from pathlib import Path

import pytest

ROOT, PROC = Path({root!r}), Path({proc!r})


def pytest_plugin_registered(plugin):
    if Path(getattr(plugin, "__file__", None) or "-").name == "conftest.py":
        plugin._CGROUP_ROOT, plugin._PROC_SELF_CGROUP = ROOT, PROC


@pytest.hookimpl(tryfirst=True)
def pytest_xdist_auto_num_workers():
    return 8


def pytest_cmdline_main(config):
    print(f"numprocesses={{config.option.numprocesses}}")
    return 0
"""


def _python_scaffold(target: Path) -> Path:
    variables = make_variables()
    created = scaffold(target, load_preset("core"), variables)
    write_scaffold_record(target, "core", variables, created)
    return target


def _plant(target: Path, name: str, body: str) -> None:
    (target / "tests").mkdir(exist_ok=True)
    (target / "tests" / name).write_text(body)


def _pytest(
    target: Path, tmp: Path, *args: str, **extra_env: str
) -> subprocess.CompletedProcess[str]:
    """Run the scaffold's own pytest with a HOME the scaffold must not reach.

    *extra_env* is applied last, after the contract vars are stripped from this
    process's own environment: it simulates a runner that already exports one
    (e.g. CARGO_HOME) before invoking pytest, which the fixture must still
    override for the vars that hold credentials or mutable state (#1056 review).
    """
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
    env |= extra_env
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

    @pytest.mark.parametrize("workers", [(), ("-n", "2")], ids=["serial", "xdist"])
    def test_home_is_moved_before_collection_and_broader_fixtures(
        self, tmp_path: Path, workers: tuple[str, ...]
    ) -> None:
        """PR #1056 review: a function-scoped fixture alone runs after collection
        imports and after session- and module-scoped fixtures."""
        if workers:
            pytest.importorskip("xdist")
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "conftest.py", _PLANTED_EARLY_CONFTEST)
        _plant(target, "test_early.py", _PLANTED_EARLY)
        _plant(target, "test_home.py", _PLANTED_HOME)
        result = _pytest(target, tmp_path, *workers)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 7, 0), result.stdout

    def test_cargo_home_isolates_config_and_credentials_but_reuses_the_cache(
        self, tmp_path: Path
    ) -> None:
        """PR #1056 review: CARGO_HOME has no separate cache-vs-config env var (unlike
        UV_CACHE_DIR), so the real ~/.cargo's config.toml/credentials.toml must never
        be reachable from a test, while its registry/ download cache is still reused."""
        real_cargo = tmp_path / "real-home" / ".cargo"
        (real_cargo / "registry").mkdir(parents=True)
        (real_cargo / "registry" / "marker.txt").write_text("cached\n")
        (real_cargo / "credentials.toml").write_text('[registries.crates-io]\ntoken = "secret"\n')
        (real_cargo / "config.toml").write_text("[net]\n")
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_cargo.py", _PLANTED_CARGO)
        result = _pytest(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 3, 0), result.stdout

    def test_rustup_home_isolates_settings_but_reuses_the_toolchains(self, tmp_path: Path) -> None:
        """#1056 review: RUSTUP_HOME's settings.toml is mutable preference state (the
        default toolchain), not just a cache, so the real ~/.rustup's settings.toml
        must never be reachable from a test, while toolchains/ and downloads/ are
        still reused."""
        real_rustup = tmp_path / "real-home" / ".rustup"
        (real_rustup / "toolchains").mkdir(parents=True)
        (real_rustup / "toolchains" / "marker.txt").write_text("cached\n")
        (real_rustup / "downloads").mkdir(parents=True)
        (real_rustup / "downloads" / "marker.txt").write_text("cached\n")
        (real_rustup / "settings.toml").write_text('default_toolchain = "stable"\n')
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_rustup.py", _PLANTED_RUSTUP)
        result = _pytest(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 3, 0), result.stdout

    def test_preexisting_cargo_and_rustup_home_are_still_overridden(self, tmp_path: Path) -> None:
        """#1056 review: when the runner already exports CARGO_HOME/RUSTUP_HOME, the
        fixture must still replace them with the isolated ones _cargo_home()/
        _rustup_home() build — the old code only set a toolchain var when it was
        absent from the environment, so an inherited export leaked real credentials
        and settings straight through."""
        decoy_cargo = tmp_path / "decoy-cargo"
        decoy_rustup = tmp_path / "decoy-rustup"
        decoy_cargo.mkdir()
        decoy_rustup.mkdir()
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_preexisting.py", _PLANTED_PREEXISTING)
        result = _pytest(
            target,
            tmp_path,
            CARGO_HOME=str(decoy_cargo),
            RUSTUP_HOME=str(decoy_rustup),
            DECOY_CARGO_HOME=str(decoy_cargo),
            DECOY_RUSTUP_HOME=str(decoy_rustup),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 2, 0), result.stdout

    def test_a_hook_exported_git_dir_cannot_reach_the_enclosing_repo(self, tmp_path: Path) -> None:
        """#1065: pytest run from a git hook inherits GIT_DIR (GIT_WORK_TREE and
        GIT_INDEX_FILE from a linked worktree, GIT_CONFIG_PARAMETERS from `git -c`),
        and a test's `git -C <tmp>` then writes to the repo the hook fired in."""
        enclosing = tmp_path / "enclosing"
        subprocess.run(["git", "init", "-q", str(enclosing)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(enclosing),
                "-c",
                "user.name=x",
                "-c",
                "user.email=x@x",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "base",
            ],
            check=True,
        )

        def state() -> list[str]:
            return [
                subprocess.run(
                    ["git", "-C", str(enclosing), *args],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
                for args in (
                    ["for-each-ref"],
                    ["config", "--local", "--list"],
                    ["worktree", "list"],
                )
            ]

        before = state()
        outside = tmp_path / "outside.cfg"
        outside.write_text("")
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_git_sandbox.py", _PLANTED_GIT_SANDBOX)
        hook_env = {
            "GIT_CONFIG": str(outside),
            "GIT_DIR": str(enclosing / ".git"),
            "GIT_WORK_TREE": str(enclosing),
            "GIT_INDEX_FILE": str(enclosing / ".git" / "index"),
            "GIT_PREFIX": "",
            "GIT_CONFIG_PARAMETERS": "'core.hookspath'='/nonexistent'",
        }
        result = _pytest(target, tmp_path, HOOK_VARS=" ".join(hook_env), **hook_env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 2, 0), result.stdout
        assert state() == before
        assert outside.read_text() == ""

    def test_cargo_and_rustup_caches_survive_under_xdist(self, tmp_path: Path) -> None:
        """Codex on #1056: an xdist worker re-imports the root conftest with HOME
        already moved by the controller; deriving CARGO_HOME/RUSTUP_HOME's cache
        source from Path.home() at that point answers with the fake home, so the
        worker loses the Rust toolchain. Codex reproduced it with `-n 2`; this runs
        real pytest -n 2 in a subprocess against a scaffolded sandbox, not a
        simulation."""
        pytest.importorskip("xdist")
        real_cargo = tmp_path / "real-home" / ".cargo"
        (real_cargo / "registry").mkdir(parents=True)
        (real_cargo / "registry" / "marker.txt").write_text("cached\n")
        real_rustup = tmp_path / "real-home" / ".rustup"
        (real_rustup / "toolchains").mkdir(parents=True)
        (real_rustup / "toolchains" / "marker.txt").write_text("cached\n")
        (real_rustup / "downloads").mkdir(parents=True)
        (real_rustup / "downloads" / "marker.txt").write_text("cached\n")
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_cargo.py", _PLANTED_CARGO)
        _plant(target, "test_rustup.py", _PLANTED_RUSTUP)
        result = _pytest(target, tmp_path, "-n", "2")
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 6, 0), result.stdout

    def test_inherited_cargo_and_rustup_home_are_the_cache_source(self, tmp_path: Path) -> None:
        """Codex on #1056 (P2): a runner whose CARGO_HOME/RUSTUP_HOME already point
        outside ~/.cargo, ~/.rustup must still see ITS toolchains — the cache
        links are taken from the inherited location, not from the default."""
        custom_cargo = tmp_path / "custom-cargo"
        (custom_cargo / "registry").mkdir(parents=True)
        (custom_cargo / "registry" / "marker.txt").write_text("custom-cargo\n")
        custom_rustup = tmp_path / "custom-rustup"
        (custom_rustup / "toolchains").mkdir(parents=True)
        (custom_rustup / "toolchains" / "marker.txt").write_text("custom-rustup\n")
        # A decoy at the default location proves the custom one wins, not ~/.rustup.
        real_cargo_default = tmp_path / "real-home" / ".cargo"
        (real_cargo_default / "registry").mkdir(parents=True)
        (real_cargo_default / "registry" / "marker.txt").write_text("default-cargo\n")
        real_rustup_default = tmp_path / "real-home" / ".rustup"
        (real_rustup_default / "toolchains").mkdir(parents=True)
        (real_rustup_default / "toolchains" / "marker.txt").write_text("default-rustup\n")
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_inherited_source.py", _PLANTED_INHERITED_SOURCE)
        result = _pytest(
            target, tmp_path, CARGO_HOME=str(custom_cargo), RUSTUP_HOME=str(custom_rustup)
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 2, 0), result.stdout

    def test_relative_cargo_and_rustup_home_still_reach_the_cache(self, tmp_path: Path) -> None:
        """Codex on #1067: a relative CARGO_HOME/RUSTUP_HOME is relative to the
        runner's cwd, but a relative symlink target resolves against the link's
        own directory, so the cache link dangled inside the fake home."""
        target = _python_scaffold(tmp_path / "p")
        (target / "relcargo" / "registry").mkdir(parents=True)
        (target / "relcargo" / "registry" / "marker.txt").write_text("custom-cargo\n")
        (target / "relrustup" / "toolchains").mkdir(parents=True)
        (target / "relrustup" / "toolchains" / "marker.txt").write_text("custom-rustup\n")
        _plant(target, "test_inherited_source.py", _PLANTED_INHERITED_SOURCE)
        result = _pytest(target, tmp_path, CARGO_HOME="relcargo", RUSTUP_HOME="relrustup")
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 2, 0), result.stdout

    def test_install_roots_move_but_shared_caches_stay_real(self, tmp_path: Path) -> None:
        """Codex on #1056 (P1): UV_PYTHON_INSTALL_DIR, UV_TOOL_DIR, GOPATH and
        BUN_INSTALL used to point at the real home, so `uv python install`,
        `uv tool install`, `go install` or `bun install -g` from a test wrote
        there. Only the shared caches (GOMODCACHE, bun's install cache) may
        stay real."""
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_install_roots.py", _PLANTED_INSTALL_ROOTS)
        result = _pytest(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 6, 0), result.stdout

    def test_exported_install_roots_still_move(self, tmp_path: Path) -> None:
        """#1062: the salvaged fix moved an install root only when the runner had not
        exported it, so an exported BUN_INSTALL, GOPATH, GOBIN, UV_*_DIR or
        XDG_BIN_HOME still let a test install into the real home. Caches follow the
        runner's own GOPATH/BUN_INSTALL instead of assuming ~/go and ~/.bun."""
        if shutil.which("uv") is None:
            pytest.skip("uv is not on PATH")
        real = tmp_path / "real-home"
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_exported_roots.py", _PLANTED_EXPORTED_ROOTS)
        result = _pytest(
            target,
            tmp_path,
            UV_PYTHON_INSTALL_DIR=str(real / ".local" / "share" / "uv" / "python"),
            UV_PYTHON_BIN_DIR=str(real / ".local" / "bin"),
            UV_TOOL_DIR=str(real / ".local" / "share" / "uv" / "tools"),
            UV_TOOL_BIN_DIR=str(real / ".local" / "bin"),
            GOPATH=str(real / "custom-go"),
            GOBIN=str(real / "custom-go" / "bin"),
            BUN_INSTALL=str(real / "custom-bun"),
            XDG_BIN_HOME=str(real / ".local" / "bin"),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 13, 0), result.stdout

    def test_a_cross_compiled_go_install_works_under_an_exported_gobin(
        self, tmp_path: Path
    ) -> None:
        """#1069: setting GOBIN made Go refuse `GOOS=<other> go install`. An inherited
        GOBIN is dropped instead, so the install lands in the isolated GOPATH/bin and
        never in the runner's own GOBIN."""
        if shutil.which("go") is None:
            pytest.skip("go is not on PATH")
        real_gobin = tmp_path / "real-home" / "go" / "bin"
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_go_cross.py", _PLANTED_GO_CROSS)
        result = _pytest(target, tmp_path, GOBIN=str(real_gobin))
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 1, 0), result.stdout
        assert not real_gobin.exists()

    def test_temp_and_tmp_match_tmpdir(self, tmp_path: Path) -> None:
        """Copilot on #1056/#1062: the per-test fixture set only TMPDIR; tempfile
        and some tools read TEMP/TMP, so point them at the same per-test dir."""
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_temp_tmp.py", _PLANTED_TEMP_TMP)
        result = _pytest(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 2, 0), result.stdout

    def test_the_session_home_is_removed_after_the_run(self, tmp_path: Path) -> None:
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_ok.py", "def test_ok():\n    assert True\n")
        result = _pytest(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        left = [p.name for p in (tmp_path / "real-tmp").iterdir()]
        assert [name for name in left if not name.startswith("pytest-of-")] == [], left

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


class TestScaffoldLint:
    def test_the_root_conftest_does_not_reorder_a_conftest_import(self, tmp_path: Path) -> None:
        """PO-316 CI: with a root conftest.py, ruff resolved ``conftest`` to it and
        called it first-party, so every test importing a helper from
        tests/conftest.py failed I001 in a repo that upgraded into the contract."""
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "conftest.py", "def helper():\n    return 1\n")
        _plant(target, "test_imports.py", _PLANTED_IMPORTS_CONFTEST)
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--no-cache", "."],
            cwd=target,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestSummaryLine:
    def test_mixed_run_counts_errors_as_failed_and_skips_as_neither(self, tmp_path: Path) -> None:
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_mixed.py", _PLANTED_MIXED)
        result = _pytest(target, tmp_path)
        assert result.returncode == 1, "pytest's own code for a failed test, exactly"
        assert _last_line(result.stdout) == ("my-project", 2, 2), result.stdout

    def test_the_line_prints_after_pytests_own_final_summary_line(self, tmp_path: Path) -> None:
        """PR #1056 review: a reader taking "the last line" must get the contract's.

        ``_last_line`` above finds the line anywhere in the output, so it cannot
        catch the line printing too early; this checks physical line order.
        """
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_ok.py", "def test_ok():\n    assert True\n")
        result = _pytest(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert lines[-1] == "my-project: 1 passed, 0 failed", result.stdout
        assert re.search(r"^1 passed in [\d.]+s$", lines[-2]), result.stdout

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


def _startup_workers(target: Path, tmp: Path) -> list[str]:
    """What `pytest -n auto` settles on in *target* at startup, on the 1-CPU/1-GiB runner."""
    cgroup, proc = tmp / "cgroup", tmp / "proc-self-cgroup"
    cgroup.mkdir(parents=True)
    (cgroup / "cpu.max").write_text("100000 100000\n")
    (cgroup / "memory.max").write_text("1073741824\n")
    proc.write_text("0::/\n")
    probe_dir = tmp / "probe"
    probe_dir.mkdir()
    probe = _WORKER_PROBE.format(root=str(cgroup), proc=str(proc))
    (probe_dir / "worker_probe.py").write_text(probe)
    result = _pytest(target, tmp, "-p", "worker_probe", "-n", "auto", PYTHONPATH=str(probe_dir))
    assert result.returncode == 0, result.stdout + result.stderr
    return [line for line in result.stdout.splitlines() if line.startswith("numprocesses=")]


class TestXdistWorkerCap:
    """`pytest -n auto` in a scaffolded repo starts no more workers than the cgroup
    holds (PR #1104): xdist asked os.cpu_count(), the HOST's 8 inside a 1-CPU/1-GiB
    runner container, and the workers were OOM-killed ("node down")."""

    def test_auto_is_held_to_the_cgroup(self, tmp_path: Path) -> None:
        pytest.importorskip("xdist")
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_worker_cap.py", _PLANTED_WORKER_CAP)
        result = _pytest(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", _WORKER_CAP_TESTS, 0), result.stdout

    def test_the_cap_is_registered_when_xdist_asks_at_startup(self, tmp_path: Path) -> None:
        """Through xdist's own caller, not a test calling the hook after startup:
        a cap registered any later than the root conftest would miss it."""
        pytest.importorskip("xdist")
        target = _python_scaffold(tmp_path / "p")
        assert _startup_workers(target, tmp_path) == ["numprocesses=1"]

    def test_a_run_without_xdist_still_loads_the_conftest(self, tmp_path: Path) -> None:
        """`-p no:xdist` leaves the hook without a spec; pytest must not reject the file."""
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_ok.py", "def test_ok():\n    assert True\n")
        result = _pytest(target, tmp_path, "-p", "no:xdist")
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 1, 0), result.stdout

    def test_upgrade_brings_the_cap_to_a_repo_scaffolded_before_it(self, tmp_path: Path) -> None:
        """A governed repo gets the cap from `project-init upgrade --apply`: its root
        conftest is the pre-cap render, recorded as the base, and is otherwise untouched."""
        pytest.importorskip("xdist")
        target = tmp_path / "p"
        variables = make_variables()
        created = scaffold(target, memory_preset("obsidian-only"), variables, strict=True)
        conftest = target / "conftest.py"
        before_cap = conftest.read_text().split("\n\n\n# The cgroup v2 files")[0] + "\n"
        assert "pytest_xdist_auto_num_workers" not in before_cap
        conftest.write_text(before_cap)
        write_scaffold_record(target, "obsidian-only", variables, created)
        # An unmanaged pin parks the #847 python-pin proposal, as TestUpgradePath does.
        (target / ".python-version").write_text("3.11\n")
        assert _startup_workers(target, tmp_path / "before") == ["numprocesses=8"]
        assert run_upgrade(target, apply=True) == 0
        assert _startup_workers(target, tmp_path / "after") == ["numprocesses=1"]


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
