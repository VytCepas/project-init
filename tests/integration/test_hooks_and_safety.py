from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


def _run_hook(hook: Path, stdin: str = "", env: dict[str, str] | None = None):
    import shutil

    bash = shutil.which("bash") or "/bin/bash"
    return subprocess.run(
        [bash, str(hook)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env if env is not None else os.environ.copy(),
    )


class TestHookExecutability:
    """PI-22: Shell hooks must be executable; Python hooks must not be."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = fallback_preset()
        variables = fallback_variables()
        scaffold(tmp_target, preset, variables)

    @pytest.mark.skipif(sys.platform == "win32", reason="executable bits don't work on Windows")
    def test_shell_hooks_are_executable(self):
        hooks_dir = self.target / ".claude" / "hooks"
        for sh in hooks_dir.glob("*.sh"):
            assert sh.stat().st_mode & 0o111, f"{sh.name} must be executable"

    @pytest.mark.skipif(sys.platform == "win32", reason="executable bits don't work on Windows")
    def test_python_hooks_are_not_executable(self):
        hooks_dir = self.target / ".claude" / "hooks"
        for py in hooks_dir.glob("*.py"):
            assert not (py.stat().st_mode & 0o111), (
                f"{py.name} should not be executable (invoked via python3)"
            )

    def test_hooks_readme_documents_convention(self):
        readme = self.target / ".claude" / "hooks" / "README.md"
        content = readme.read_text()
        assert "executable" in content.lower() or "executable bit" in content.lower()
        assert ".sh" in content or "Shell" in content


class TestSecurityEnforcementMigration:
    """ADR-007: custom safety hooks replaced by plugin + git/CI enforcement."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        scaffold(tmp_target, fallback_preset(), fallback_variables())

    def test_legacy_safety_hooks_removed(self):
        hooks_dir = self.target / ".claude" / "hooks"
        assert not (hooks_dir / "secret-guard.py").exists()
        assert not (hooks_dir / "bash_safety_guard.sh").exists()

    def test_settings_drops_legacy_hook_references(self):
        content = (self.target / ".claude" / "settings.json").read_text()
        assert "secret-guard" not in content
        assert "bash_safety_guard" not in content

    def test_settings_enables_security_guidance_plugin(self):
        data = json.loads((self.target / ".claude" / "settings.json").read_text())
        assert data["enabledPlugins"]["security-guidance@claude-plugins-official"] is True
        marketplace = data["extraKnownMarketplaces"]["claude-plugins-official"]
        assert marketplace["source"] == {
            "source": "github",
            "repo": "anthropics/claude-plugins-official",
        }

    def test_dag_workflow_hooks_unchanged(self):
        """The genuinely custom workflow guards stay wired."""
        hooks_dir = self.target / ".claude" / "hooks"
        for name in (
            "github_command_guard.sh",
            "dag_workflow.py",
            "pre_commit_gate.sh",
            "post_edit_lint.sh",
            "workflow_state_reminder.sh",
        ):
            assert (hooks_dir / name).is_file(), f"{name} must survive ADR-007"

        data = json.loads((self.target / ".claude" / "settings.json").read_text())
        commands = [
            h["command"]
            for groups in data["hooks"].values()
            for group in groups
            for h in group["hooks"]
        ]
        for wired in (
            "github_command_guard.sh",
            "pre_commit_gate.sh",
            "post_edit_lint.sh",
            "workflow_state_reminder.sh",
        ):
            assert any(wired in c for c in commands), f"{wired} must stay wired"


class TestGitleaksPreCommitHook:
    """ADR-007: secret scanning is a git pre-commit hook, fail-open locally."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        self.hook = self.target / ".github" / "hooks" / "pre-commit"

    def test_hook_exists_and_executable(self):
        assert self.hook.is_file()
        assert self.hook.stat().st_mode & 0o111

    def test_hook_scans_staged_changes(self):
        content = self.hook.read_text()
        assert "gitleaks git --pre-commit --staged" in content

    def test_fails_open_when_gitleaks_missing(self, tmp_path: Path):
        """Without gitleaks the commit proceeds with a warning — CI is the backstop."""
        empty_bin = tmp_path / "bin"
        empty_bin.mkdir()
        env = {"PATH": str(empty_bin), "HOME": os.environ.get("HOME", "/tmp")}
        result = _run_hook(self.hook, env=env)
        assert result.returncode == 0
        assert "gitleaks not installed" in result.stderr

    def test_invokes_gitleaks_and_propagates_findings_exit(self, tmp_path: Path):
        """With gitleaks on PATH the hook delegates and propagates its exit code."""
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        log = tmp_path / "args.log"
        fake = fake_bin / "gitleaks"
        fake.write_text(f'#!/bin/bash\necho "$@" > "{log}"\nexit 1\n')
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        result = _run_hook(self.hook, env=env)
        assert result.returncode == 1, "findings exit code must abort the commit"
        assert "--staged" in log.read_text()


class TestPrePushLifecycleGate:
    """ADR-007: pre-push enforces branch naming with the same rule as dag_workflow.py."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        self.hook = self.target / ".github" / "hooks" / "pre-push"

    SHA = "a" * 40
    ZERO = "0" * 40

    def _push(self, remote_ref: str, local_sha: str | None = None):
        line = f"refs/heads/x {local_sha or self.SHA} {remote_ref} {self.ZERO}\n"
        return _run_hook(self.hook, stdin=line)

    def test_blocks_push_to_main(self):
        result = self._push("refs/heads/main")
        assert result.returncode == 1
        assert "not allowed" in result.stdout

    def test_blocks_push_to_master(self):
        assert self._push("refs/heads/master").returncode == 1

    def test_allows_issue_branch(self):
        assert self._push("refs/heads/feat/PI-42-add-oauth-login").returncode == 0

    def test_allows_nojira_branch(self):
        assert self._push("refs/heads/chore/nojira-bump-dev-dependency").returncode == 0

    def test_blocks_unconventional_branch_name(self):
        result = self._push("refs/heads/wip-stuff")
        assert result.returncode == 1
        assert "naming convention" in result.stdout

    def test_allows_deleting_misnamed_branch(self):
        result = self._push("refs/heads/wip-stuff", local_sha=self.ZERO)
        assert result.returncode == 0

    def test_allows_tags(self):
        line = f"refs/tags/v1.0.0 {self.SHA} refs/tags/v1.0.0 {self.ZERO}\n"
        assert _run_hook(self.hook, stdin=line).returncode == 0


class TestInstallHooks:
    """install_hooks.sh wires all git-level enforcement into .git/hooks."""

    def test_installs_all_enforcement_hooks(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        subprocess.run(
            ["git", "init", "-q"], cwd=tmp_target, check=True, capture_output=True
        )
        result = subprocess.run(
            ["bash", str(tmp_target / ".claude" / "scripts" / "install_hooks.sh")],
            cwd=tmp_target,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        for name in ("pre-commit", "commit-msg", "pre-push"):
            installed = tmp_target / ".git" / "hooks" / name
            assert installed.is_file(), f"{name} not installed"
            assert installed.stat().st_mode & 0o111, f"{name} not executable"

    def test_symlinked_destination_is_replaced_not_clobbered(self, tmp_target: Path):
        """PI-204: when .git/hooks/<hook> is a symlink (e.g. a hooks manager),
        install must replace the link, not write through to its referent."""
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        subprocess.run(
            ["git", "init", "-q"], cwd=tmp_target, check=True, capture_output=True
        )
        referent = tmp_target / "shared-pre-commit"
        referent.write_text("USER SHARED HOOK - DO NOT CLOBBER\n")
        dst = tmp_target / ".git" / "hooks" / "pre-commit"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.symlink_to(referent)

        result = subprocess.run(
            ["bash", str(tmp_target / ".claude" / "scripts" / "install_hooks.sh")],
            cwd=tmp_target,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        # The user's shared file must be untouched ...
        assert referent.read_text() == "USER SHARED HOOK - DO NOT CLOBBER\n"
        # ... and the destination is now a real file (the project's hook).
        assert dst.is_file() and not dst.is_symlink()


class TestCiSecretScanMirror:
    """ADR-007: the gitleaks scan is mirrored as a hard gate in scaffolded CI."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        self.ci = (self.target / ".github" / "workflows" / "ci.yml").read_text()

    def test_secret_scan_job_present(self):
        assert "secret-scan:" in self.ci
        assert "gitleaks/gitleaks-action@v3" in self.ci

    def test_scans_full_history(self):
        assert "fetch-depth: 0" in self.ci

    def test_job_rendered_outside_language_conditionals(self, tmp_path: Path):
        """secret-scan must survive a non-python scaffold too."""
        target = tmp_path / "node-proj"
        target.mkdir()
        scaffold(
            target,
            fallback_preset(),
            fallback_variables(language="node", python="", node="true"),
        )
        ci = (target / ".github" / "workflows" / "ci.yml").read_text()
        assert "secret-scan:" in ci


class TestShellLineEndings:
    """Regression: shell hook scripts must be LF-only.

    Codex evaluation 2026-04-25 caught templates/base/dot_claude/hooks/
    shell scripts shipping with CRLF endings, which made
    `/usr/bin/env: 'bash\\r': No such file or directory` on Unix.
    """

    def test_no_crlf_in_shell_templates(self):
        repo_root = Path(__file__).resolve().parents[2]
        offenders: list[str] = []
        for sh in repo_root.glob("**/*.sh"):
            # Skip generated venv / build dirs.
            if any(part in {".venv", "build", "dist", "node_modules"} for part in sh.parts):
                continue
            data = sh.read_bytes()
            if b"\r\n" in data:
                offenders.append(str(sh.relative_to(repo_root)))
        assert not offenders, (
            "Shell scripts with CRLF line endings:\n  "
            + "\n  ".join(offenders)
        )
