"""Post-scaffold bootstrap (#887).

The git/commit steps run against a real ``git`` (idempotency + the #888 trailer
are behavioural, so they use the real tool); the toolchain steps (uv/just) are
exercised through their skip branches or a faked ``_run`` so the suite never
shells out to uv/just/the network.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from project_init import bootstrap
from project_init.__main__ import main
from project_init.bootstrap import run_bootstrap

_TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


def _git(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=target, capture_output=True, text=True)


class TestGitInit:
    def test_creates_repo(self, tmp_path: Path):
        assert bootstrap._git_init(tmp_path).outcome == "done"

    def test_marks_git_dir(self, tmp_path: Path):
        bootstrap._git_init(tmp_path)
        assert (tmp_path / ".git").is_dir()

    def test_skips_existing_repo(self, tmp_path: Path):
        _git(tmp_path, "init")
        assert bootstrap._git_init(tmp_path).outcome == "skipped"

    def test_initial_branch_is_main(self, tmp_path: Path):
        # Regardless of the machine's init.defaultBranch, the lifecycle targets
        # main, so a bootstrapped repo must not land on master (#887 review).
        bootstrap._git_init(tmp_path)
        assert _git(tmp_path, "symbolic-ref", "--short", "HEAD").stdout.strip() == "main"


class TestInitialCommit:
    @staticmethod
    def _repo(tmp_path: Path) -> Path:
        _git(tmp_path, "init")
        # A local identity so `git commit` works on a runner with no global git
        # config (CI), independent of the ambient environment.
        _git(tmp_path, "config", "user.email", "t@example.com")
        _git(tmp_path, "config", "user.name", "t")
        (tmp_path / "f.txt").write_text("x", encoding="utf-8")
        return tmp_path

    def test_creates_commit(self, tmp_path: Path):
        assert bootstrap._initial_commit(self._repo(tmp_path), coauthor=False).outcome == "done"

    def test_trailer_present_when_coauthor(self, tmp_path: Path):
        t = self._repo(tmp_path)
        bootstrap._initial_commit(t, coauthor=True)
        assert _TRAILER in _git(t, "log", "-1", "--format=%B").stdout

    def test_trailer_absent_when_not_coauthor(self, tmp_path: Path):
        t = self._repo(tmp_path)
        bootstrap._initial_commit(t, coauthor=False)
        assert "Co-Authored-By" not in _git(t, "log", "-1", "--format=%B").stdout

    def test_subject_is_conventional(self, tmp_path: Path):
        t = self._repo(tmp_path)
        bootstrap._initial_commit(t, coauthor=False)
        assert (
            _git(t, "log", "-1", "--format=%s").stdout.strip()
            == "chore: initial project-init scaffold"
        )

    def test_skips_when_repo_has_commits(self, tmp_path: Path):
        t = self._repo(tmp_path)
        bootstrap._initial_commit(t, coauthor=False)
        (t / "g.txt").write_text("y", encoding="utf-8")
        assert bootstrap._initial_commit(t, coauthor=False).outcome == "skipped"

    def test_skips_without_git(self, tmp_path: Path):
        assert bootstrap._initial_commit(tmp_path, coauthor=False).outcome == "skipped"


class TestToolchainSkips:
    def test_uv_init_skips_non_python(self, tmp_path: Path):
        assert bootstrap._uv_init(tmp_path, "go").outcome == "skipped"

    def test_uv_init_skips_existing_pyproject(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        assert bootstrap._uv_init(tmp_path, "python").outcome == "skipped"

    def test_uv_init_passes_no_workspace(self, tmp_path: Path, monkeypatch):
        # --no-workspace stops uv from mutating a parent workspace's pyproject.
        captured: dict[str, list[str]] = {}

        def fake(cmd: list[str], target: Path) -> tuple[bool, str]:
            captured["cmd"] = cmd
            return True, ""

        monkeypatch.setattr(bootstrap, "_run", fake)
        bootstrap._uv_init(tmp_path, "python")
        assert "--no-workspace" in captured["cmd"]

    def test_install_deps_skips_without_justfile(self, tmp_path: Path):
        assert bootstrap._install_deps(tmp_path, "none").outcome == "skipped"

    def test_install_deps_python_skips_without_pyproject(self, tmp_path: Path):
        (tmp_path / "justfile").write_text("", encoding="utf-8")
        assert bootstrap._install_deps(tmp_path, "python").outcome == "skipped"

    def test_install_hooks_skips_without_script(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        assert bootstrap._install_hooks(tmp_path).outcome == "skipped"


class TestOrchestration:
    @staticmethod
    def _fake_run(monkeypatch):
        calls: list[list[str]] = []

        def fake(cmd: list[str], target: Path) -> tuple[bool, str]:
            calls.append(cmd)
            if cmd[:2] == ["git", "init"]:
                (target / ".git").mkdir(exist_ok=True)
                return True, ""
            if cmd[:3] == ["git", "rev-parse", "--verify"]:
                return False, ""  # no commits yet → initial commit proceeds
            return True, ""

        monkeypatch.setattr(bootstrap, "_run", fake)
        return calls

    def test_runs_all_steps_in_order(self, tmp_path: Path, monkeypatch):
        self._fake_run(monkeypatch)
        (tmp_path / "justfile").write_text("", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        steps = run_bootstrap(tmp_path, language="python", coauthor=True)
        assert [s.label for s in steps] == [
            "git init",
            "install hooks",
            "uv init",
            "install deps",
            "initial commit",
        ]

    def test_reports_failure_without_aborting(self, tmp_path: Path, monkeypatch):
        def fake(cmd: list[str], target: Path) -> tuple[bool, str]:
            if cmd[:2] == ["git", "init"]:
                return False, "boom"
            return True, ""

        monkeypatch.setattr(bootstrap, "_run", fake)
        steps = run_bootstrap(tmp_path, language="none", coauthor=False)
        assert steps[0].outcome == "failed"


class TestReport:
    _STEP = [bootstrap.BootstrapStep("initial commit", "failed", "boom")]

    def test_json_report_goes_to_stderr(self, capsys):
        bootstrap.print_bootstrap_report(self._STEP, stderr=True)
        captured = capsys.readouterr()
        assert "Bootstrap" in captured.err

    def test_json_report_keeps_stdout_clean(self, capsys):
        bootstrap.print_bootstrap_report(self._STEP, stderr=True)
        assert capsys.readouterr().out == ""

    def test_default_report_goes_to_stdout(self, capsys):
        bootstrap.print_bootstrap_report(self._STEP)
        assert "Bootstrap" in capsys.readouterr().out


class TestCliWiring:
    @staticmethod
    def _argv(target: Path, *extra: str) -> list[str]:
        return [
            str(target),
            "--non-interactive",
            "--preset",
            "core",
            "--name",
            "fx",
            "--description",
            "d",
            "--language",
            "none",
            *extra,
        ]

    def test_flag_invokes_bootstrap_with_coauthor(self, tmp_path: Path, monkeypatch):
        seen: dict[str, object] = {}

        def fake(target: Path, *, language: str, coauthor: bool) -> list:
            seen["language"] = language
            seen["coauthor"] = coauthor
            return []

        monkeypatch.setattr(bootstrap, "run_bootstrap", fake)
        assert main(self._argv(tmp_path / "p", "--bootstrap")) == 0
        assert seen == {"language": "none", "coauthor": True}

    def test_no_flag_skips_bootstrap(self, tmp_path: Path, monkeypatch):
        seen: dict[str, bool] = {}
        monkeypatch.setattr(
            bootstrap, "run_bootstrap", lambda *a, **k: seen.setdefault("ran", True) or []
        )
        assert main(self._argv(tmp_path / "p")) == 0
        assert "ran" not in seen
