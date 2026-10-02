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
# in a broader-scoped fixture. ntpath.expanduser is Path.home() on Windows.
_PLANTED_EARLY_CONFTEST = """\
import ntpath
from pathlib import Path

import pytest

AT_CONFTEST_IMPORT = (Path.home(), ntpath.expanduser("~"))


@pytest.fixture(scope="session")
def session_home():
    return Path.home(), ntpath.expanduser("~")


@pytest.fixture(scope="session")
def conftest_import_home():
    return AT_CONFTEST_IMPORT
"""

_PLANTED_EARLY = """\
import ntpath
import os
from pathlib import Path

import pytest

AT_COLLECTION = (Path.home(), ntpath.expanduser("~"))


@pytest.fixture(scope="module")
def module_home():
    return Path.home(), ntpath.expanduser("~")


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

_PLANTED_WINDOWS = """\
import ntpath
import os
from pathlib import Path


def _is_real(path):
    assert path != "~", "nothing to expand from: the variable is unset"
    return Path(path).is_relative_to(Path(os.environ["REAL_HOME"]))


def test_userprofile_is_redirected():
    assert not _is_real(ntpath.expanduser("~"))


def test_homedrive_homepath_are_redirected(monkeypatch):
    monkeypatch.delenv("USERPROFILE")
    assert not _is_real(ntpath.expanduser("~"))


def test_appdata_is_redirected():
    assert not _is_real(os.environ["APPDATA"])


def test_localappdata_is_redirected():
    assert not _is_real(os.environ["LOCALAPPDATA"])
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
import sys
from pathlib import Path


def test_a_cross_compiled_go_install_lands_in_the_isolated_gopath(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/hello\\n\\ngo 1.21\\n")
    (tmp_path / "main.go").write_text("package main\\n\\nfunc main() {}\\n")
    goos = "linux" if sys.platform == "win32" else "windows"
    env = {**os.environ, "GOOS": goos, "GOTOOLCHAIN": "local"}
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
    drive = Path(real_home).drive
    env |= {
        "HOME": str(real_home),
        "USERPROFILE": str(real_home),
        "HOMEDRIVE": drive,
        "HOMEPATH": str(real_home)[len(drive) :],
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

    def test_windows_home_variables_are_redirected(self, tmp_path: Path) -> None:
        """PR #1056 review: Path.home() on Windows reads USERPROFILE, then
        HOMEDRIVE + HOMEPATH, and never HOME."""
        target = _python_scaffold(tmp_path / "p")
        _plant(target, "test_windows.py", _PLANTED_WINDOWS)
        result = _pytest(target, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _last_line(result.stdout) == ("my-project", 4, 0), result.stdout

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
        """Copilot on #1056/#1062: the per-test fixture set only TMPDIR; Windows
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
