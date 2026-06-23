"""ADR-019 / #406: guarded hook self-log (_usage_log.sh + prod_guard.py).

Shipped-always-dormant: the helper and the five always-on shell hooks carry the
self-log, but it no-ops unless the overlay marker (.claude/observability/)
exists. Asserts: marker gating in both directions, JSON validity, the
never-reads-stdin invariant, every hook wiring (fallback + plugin copies), and
that prod_guard logs while STILL blocking a destructive command (regression).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FALLBACK_HOOKS = _REPO_ROOT / "templates" / "fallback" / "dot_claude" / "hooks"
_PLUGIN_HOOKS = _REPO_ROOT / "plugins" / "project-init-workflow" / "hooks"
_HELPER = _FALLBACK_HOOKS / "_usage_log.sh"
_PROD_GUARD = _REPO_ROOT / "templates" / "base" / "dot_claude" / "hooks" / "prod_guard.py"

# The five always-on shell hooks that must self-log, with the (hook, event) each
# should record.
_WIRED_HOOKS = {
    "session_setup.sh": ("session_setup", "SessionStart"),
    "pre_commit_gate.sh": ("pre_commit_gate", "PreToolUse"),
    "github_command_guard.sh": ("github_command_guard", "PreToolUse"),
    "post_edit_lint.sh": ("post_edit_lint", "PostToolUse"),
    "workflow_state_reminder.sh": ("workflow_state_reminder", "UserPromptSubmit"),
}


def _call_helper(root: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    """Source the helper and invoke usage_log with CLAUDE_PROJECT_DIR=root."""
    script = f'. "{_HELPER}"\nusage_log {" ".join(args)}\n'
    return subprocess.run(
        ["bash", "-c", script],
        input=stdin,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root)},
        cwd=str(root),
        timeout=30,
    )


class TestHelperGating:
    def test_dormant_without_marker(self, tmp_path: Path):
        _call_helper(tmp_path, "session_setup", "SessionStart")
        assert not (tmp_path / ".claude" / "observability" / "usage.jsonl").exists()

    def test_writes_valid_json_with_marker(self, tmp_path: Path):
        (tmp_path / ".claude" / "observability").mkdir(parents=True)
        _call_helper(tmp_path, "github_command_guard", "PreToolUse")
        log = tmp_path / ".claude" / "observability" / "usage.jsonl"
        assert log.is_file()
        rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        assert len(rows) == 1
        row = rows[0]
        assert row["hook"] == "github_command_guard"
        assert row["event"] == "PreToolUse"
        assert row["project"] == str(tmp_path)
        assert "ts" in row
        # No session env set → the optional field is omitted.
        assert "session" not in row

    def test_session_emitted_when_env_present(self, tmp_path: Path):
        (tmp_path / ".claude" / "observability").mkdir(parents=True)
        script = f'. "{_HELPER}"\nusage_log pre_commit_gate PreToolUse\n'
        subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env={
                "PATH": "/usr/bin:/bin",
                "CLAUDE_PROJECT_DIR": str(tmp_path),
                "CLAUDE_SESSION_ID": "sess-42",
            },
            cwd=str(tmp_path),
            timeout=30,
        )
        log = tmp_path / ".claude" / "observability" / "usage.jsonl"
        row = json.loads(log.read_text().splitlines()[0])
        assert row["session"] == "sess-42"

    def test_never_consumes_stdin(self, tmp_path: Path):
        """usage_log must not read stdin — the payload belongs to the real hook
        body. Source it, call it, then `cat`: stdin must still be intact."""
        (tmp_path / ".claude" / "observability").mkdir(parents=True)
        script = (
            f'. "{_HELPER}"\n'
            "usage_log github_command_guard PreToolUse </dev/null\n"
            "cat\n"  # whatever usage_log left on stdin
        )
        result = subprocess.run(
            ["bash", "-c", script],
            input="PAYLOAD_STILL_HERE",
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=str(tmp_path),
            timeout=30,
        )
        assert result.stdout == "PAYLOAD_STILL_HERE"


class TestHookWiring:
    @pytest.mark.parametrize("hook,expected", _WIRED_HOOKS.items())
    def test_fallback_hook_sources_and_calls(self, hook: str, expected: tuple[str, str]):
        text = (_FALLBACK_HOOKS / hook).read_text(encoding="utf-8")
        assert "_usage_log.sh" in text, f"{hook} does not source the helper"
        name, event = expected
        assert f"usage_log {name} {event}" in text, f"{hook} missing usage_log call"

    @pytest.mark.parametrize("hook", _WIRED_HOOKS)
    def test_plugin_copy_in_sync(self, hook: str):
        """Plugin-mode hooks self-log too — the synced copy must carry the call."""
        plugin = _PLUGIN_HOOKS / hook
        assert plugin.is_file(), f"{hook} missing from plugin (run just sync-plugin)"
        assert "_usage_log.sh" in plugin.read_text(encoding="utf-8")

    def test_helper_synced_to_plugin(self):
        assert (_PLUGIN_HOOKS / "_usage_log.sh").is_file()
        assert (_PLUGIN_HOOKS / "_usage_log.sh").read_bytes() == _HELPER.read_bytes()

    def test_helper_never_reads_stdin_source(self):
        """No stdin-consuming construct in the helper (cat/read/$(<)/</dev/stdin)."""
        src = _HELPER.read_text(encoding="utf-8")
        for bad in ("$(cat", "read ", "</dev/stdin", "$(<"):
            assert bad not in src, f"helper appears to read stdin: {bad!r}"


def _run_prod_guard(payload: dict, root: Path) -> tuple[dict | None, Path]:
    result = subprocess.run(
        ["python3", str(_PROD_GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root)},
        cwd=str(root),
        timeout=30,
    )
    assert result.returncode == 0, "guard must always exit 0 (fail-open)"
    verdict = json.loads(result.stdout) if result.stdout.strip() else None
    return verdict, root / ".claude" / "observability" / "usage.jsonl"


class TestProdGuardSelfLog:
    def test_blocks_destructive_and_logs_with_observability_on(self, tmp_path: Path):
        """Regression: enabling observability must not weaken the guard."""
        (tmp_path / ".claude" / "observability").mkdir(parents=True)
        payload = {
            "tool_input": {"command": "terraform destroy"},
            "permission_mode": "bypassPermissions",
            "cwd": str(tmp_path),
            "session_id": "sess-xyz",
        }
        verdict, log = _run_prod_guard(payload, tmp_path)
        # Still blocks.
        assert verdict["hookSpecificOutput"]["permissionDecision"] == "deny"
        # And logged exactly one prod_guard line carrying the session.
        rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        assert len(rows) == 1
        assert rows[0]["hook"] == "prod_guard"
        assert rows[0]["session"] == "sess-xyz"

    def test_dormant_without_marker(self, tmp_path: Path):
        payload = {"tool_input": {"command": "ls"}, "cwd": str(tmp_path)}
        _, log = _run_prod_guard(payload, tmp_path)
        assert not log.exists()

    def test_logs_even_when_command_is_safe(self, tmp_path: Path):
        (tmp_path / ".claude" / "observability").mkdir(parents=True)
        payload = {"tool_input": {"command": "ls -la"}, "cwd": str(tmp_path)}
        verdict, log = _run_prod_guard(payload, tmp_path)
        assert verdict is None  # safe command → no verdict
        assert log.is_file()  # but the firing is still recorded
