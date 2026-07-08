"""PI-651 (epic #641): failure-path hook output is capped before injection.

`post_edit_lint.sh` (PostToolUse additionalContext) and `pre_commit_gate.sh`
(PreToolUse deny reason) persist their text in the transcript, re-sent every
turn — so the injected error report is capped at 40 lines with a trailer
pointing at the full report. The deny/allow decisions themselves are
unchanged: a failing gate still denies, whatever the output size.

The hooks are exercised from a bare (non-uv) temp repo with the repo venv's
ruff on PATH, so the system-ruff branch runs deterministically offline.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_SRC = _REPO_ROOT / "templates" / "fallback" / "dot_agents" / "hooks"
_VENV_BIN = Path(sys.executable).parent

pytestmark = pytest.mark.skipif(
    not (_VENV_BIN / "ruff").exists() and shutil.which("ruff") is None,
    reason="ruff not available",
)


def _hook_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{_VENV_BIN}:{env['PATH']}"
    return env


def _make_workdir(tmp_path: Path, *hooks: str) -> Path:
    """A bare working dir (no pyproject/uv.lock → system-ruff branch)."""
    work = tmp_path / "work"
    hooks_dir = work / ".agents" / "hooks"
    hooks_dir.mkdir(parents=True)
    for name in (*hooks, "_usage_log.sh"):
        shutil.copy(_HOOKS_SRC / name, hooks_dir / name)
    # _py.sh lives in the base layer (always copied by the scaffolder).
    shutil.copy(
        _REPO_ROOT / "templates" / "base" / "dot_agents" / "hooks" / "_py.sh",
        hooks_dir / "_py.sh",
    )
    return work


def _noisy_py(path: Path, errors: int) -> None:
    # F821 (undefined name) is default-on and NOT auto-fixable → each line
    # survives the --fix pass and lands in the reported errors.
    path.write_text("".join(f"print(undefined_name_{i})\n" for i in range(errors)))


class TestPostEditLintCap:
    def _run(self, work: Path, file_path: Path) -> str:
        payload = json.dumps({"tool_input": {"file_path": str(file_path)}})
        result = subprocess.run(
            ["bash", str(work / ".agents" / "hooks" / "post_edit_lint.sh")],
            input=payload,
            capture_output=True,
            text=True,
            cwd=work,
            env=_hook_env(),
            check=False,
        )
        assert result.returncode == 0, result.stderr
        if not result.stdout.strip():
            return ""
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_oversized_lint_output_is_capped_with_trailer(self, tmp_path: Path):
        work = _make_workdir(tmp_path, "post_edit_lint.sh")
        bad = work / "bad.py"
        _noisy_py(bad, 60)
        ctx = self._run(work, bad)
        assert "Lint errors in" in ctx
        assert "output truncated" in ctx
        assert "just lint" in ctx  # the trailer's pointer to the full report
        # 40 capped lines + header + trailer, with generous slack — never the
        # full 60-error dump (ruff emits several lines per finding).
        assert len(ctx.splitlines()) < 50
        assert "undefined_name_0" in ctx  # the first findings survive

    def test_small_lint_output_is_not_truncated(self, tmp_path: Path):
        work = _make_workdir(tmp_path, "post_edit_lint.sh")
        bad = work / "bad.py"
        _noisy_py(bad, 2)
        ctx = self._run(work, bad)
        assert "Lint errors in" in ctx
        assert "output truncated" not in ctx


class TestPreCommitGateCap:
    def _run_gate(self, work: Path) -> dict:
        payload = json.dumps({"tool_input": {"command": "git commit -m x"}})
        result = subprocess.run(
            ["bash", str(work / ".agents" / "hooks" / "pre_commit_gate.sh")],
            input=payload,
            capture_output=True,
            text=True,
            cwd=work,
            env=_hook_env(),
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)["hookSpecificOutput"]

    def test_oversized_deny_reason_is_capped_but_still_denies(self, tmp_path: Path):
        work = _make_workdir(tmp_path, "pre_commit_gate.sh")
        subprocess.run(["git", "init", "-q"], cwd=work, check=True, capture_output=True)
        bad = work / "bad.py"
        _noisy_py(bad, 60)
        subprocess.run(["git", "add", "bad.py"], cwd=work, check=True, capture_output=True)
        out = self._run_gate(work)
        # Quality guardrail: the decision is untouched — only the text is capped.
        assert out["permissionDecision"] == "deny"
        reason = out["permissionDecisionReason"]
        assert "output truncated" in reason
        assert "just lint" in reason
        assert len(reason.splitlines()) < 50
