"""#606: pre-edit issue guard — verdicts + wiring.

The guard flags edits made while a repo is on its default branch (main/master)
and lets everything else through, fail-open. Modeled on test_prod_guard.py.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK = (
    _REPO_ROOT
    / "templates"
    / "lifecycle_fallback"
    / "dot_claude"
    / "hooks"
    / "pre_edit_issue_guard.py"
)


def _git_repo(path: Path, branch: str) -> Path:
    """Create a git repo at ``path`` with one commit on ``branch``."""
    path.mkdir(parents=True, exist_ok=True)
    env = ["-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / ".keep").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), *env, "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), *env, "commit", "-q", "-m", "init"], check=True)
    subprocess.run(["git", "-C", str(path), "branch", "-m", branch], check=True)
    return path


def _run_hook(payload: dict) -> dict | None:
    result = subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def _payload(file_path: Path, mode: str = "default") -> dict:
    return {"tool_input": {"file_path": str(file_path)}, "permission_mode": mode}


class TestVerdicts:
    def test_edit_on_main_asks_interactive(self, tmp_path: Path):
        repo = _git_repo(tmp_path / "r", "main")
        verdict = _run_hook(_payload(repo / "src" / "x.py"))
        assert verdict["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_edit_on_main_denies_autonomous(self, tmp_path: Path):
        repo = _git_repo(tmp_path / "r", "main")
        verdict = _run_hook(_payload(repo / "x.py", "bypassPermissions"))
        assert verdict["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_deny_reason_names_the_branch(self, tmp_path: Path):
        repo = _git_repo(tmp_path / "r", "master")
        verdict = _run_hook(_payload(repo / "x.py", "bypassPermissions"))
        assert "master" in verdict["hookSpecificOutput"]["permissionDecisionReason"]

    def test_edit_on_issue_branch_passes(self, tmp_path: Path):
        repo = _git_repo(tmp_path / "r", "feat/PI-1-thing")
        assert _run_hook(_payload(repo / "x.py")) is None

    def test_edit_on_issueless_branch_passes(self, tmp_path: Path):
        repo = _git_repo(tmp_path / "r", "chore/cleanup")
        assert _run_hook(_payload(repo / "x.py")) is None

    def test_edit_outside_repo_passes(self, tmp_path: Path):
        assert _run_hook(_payload(tmp_path / "loose.py")) is None

    def test_missing_file_path_passes(self):
        assert _run_hook({"tool_input": {}, "permission_mode": "default"}) is None

    def test_garbage_stdin_fails_open(self):
        result = subprocess.run(
            ["python3", str(_HOOK)], input="not json", capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_non_dict_json_fails_open(self):
        result = subprocess.run(
            ["python3", str(_HOOK)], input="[]", capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_non_dict_tool_input_fails_open(self):
        result = subprocess.run(
            ["python3", str(_HOOK)],
            input='{"tool_input": ["x"]}',
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout == ""


class TestWiring:
    def test_lifecycle_plugin_ships_the_guard(self):
        plugin_hooks = json.loads(
            (_REPO_ROOT / "plugins/project-init-lifecycle/hooks/hooks.json").read_text()
        )
        commands = [
            h["command"] for entry in plugin_hooks["hooks"]["PreToolUse"] for h in entry["hooks"]
        ]
        assert any("pre_edit_issue_guard.py" in c for c in commands)

    def test_fallback_lifecycle_settings_wire_the_guard(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        commands = [
            h["command"] for entry in settings["hooks"]["PreToolUse"] for h in entry["hooks"]
        ]
        assert any("pre_edit_issue_guard.py" in c for c in commands)
        assert (target / ".claude" / "hooks" / "pre_edit_issue_guard.py").is_file()
