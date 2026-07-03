"""Shift-left commit/push gates: catch static issues before they reach CI.

Three layers, each closing a gap the others leave:

- **git `pre-commit`** now runs `just lint` (not only gitleaks), so a *human*
  committing from a terminal/IDE is held to the same static gate as CI — the
  Claude `pre_commit_gate.sh` only fires for agent-driven commits.
- **git `pre-push`** now runs `just ci`, so the push→CI-fail→fix→re-push loop is
  caught locally.
- **`pre_commit_gate.sh`** (the agent commit gate) gained a per-file shell block
  so staged `.sh` files are `shfmt`/`shellcheck`'d even when `just` is absent.

All three fail-open when their tooling is missing (CI is the hard backstop) and
are bypassable with `--no-verify`, mirroring the existing gitleaks posture.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import fallback_preset, fallback_variables, make_variables


def _git_hooks(target: Path) -> tuple[str, str]:
    """Render a scaffold and return (pre-commit, pre-push) hook text."""
    scaffold(target, load_preset("obsidian-only"), make_variables(language="python", python="true"))
    pre_commit = (target / ".github" / "hooks" / "pre-commit").read_text()
    pre_push = (target / ".github" / "hooks" / "pre-push").read_text()
    return pre_commit, pre_push


def test_git_pre_commit_runs_lint_and_keeps_secret_scan(tmp_target: Path):
    pre_commit, _ = _git_hooks(tmp_target)
    # Same lint surface as CI + the agent gate, so human commits are covered too.
    assert "just lint" in pre_commit
    # Fail-closed when tooling is present, bypassable, and secrets still scanned.
    assert "--no-verify" in pre_commit
    assert "gitleaks" in pre_commit


def test_git_pre_push_runs_ci(tmp_target: Path):
    _, pre_push = _git_hooks(tmp_target)
    assert "just ci" in pre_push
    # Only for a real branch push, and still bypassable in an emergency.
    assert "PUSHING_BRANCH" in pre_push
    assert "--no-verify" in pre_push


def test_pre_commit_gate_has_per_file_shell_block(tmp_target: Path):
    """The agent commit gate must shellcheck/shfmt staged .sh without needing `just`."""
    scaffold(tmp_target, fallback_preset(), fallback_variables(language="python", python="true"))
    gate = (tmp_target / ".claude" / "hooks" / "pre_commit_gate.sh").read_text()
    assert "shfmt -w -i 2" in gate
    assert "shellcheck -S error -x" in gate


@pytest.mark.skipif(shutil.which("shfmt") is None, reason="shfmt not available")
def test_pre_commit_gate_autofixes_staged_shell(tmp_path: Path):
    """End-to-end: a badly-formatted staged .sh is shfmt-fixed and re-staged."""
    target = tmp_path / "proj"
    scaffold(target, fallback_preset(), fallback_variables(language="python", python="true"))
    hook = target / ".claude" / "hooks" / "pre_commit_gate.sh"

    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=target, check=True)

    bad = target / "messy.sh"
    # 4-space indent + one-line case arm — shfmt -i 2 rewrites both.
    bad.write_text('#!/usr/bin/env bash\ncase "$1" in\n    a) echo hi ;; esac\n')
    original = bad.read_text()
    subprocess.run(["git", "add", "messy.sh"], cwd=target, check=True)

    payload = json.dumps({"tool_input": {"command": "git commit -m x"}})
    subprocess.run(
        ["bash", str(hook)], input=payload, cwd=target, capture_output=True, text=True
    )

    # The working-tree file was reformatted in place …
    assert bad.read_text() != original, "pre_commit_gate did not shfmt the staged shell file"
    assert subprocess.run(["shfmt", "-d", "-i", "2", str(bad)], capture_output=True).stdout == b""
    # … and the fix was re-staged, so the commit would include it, not the mess.
    staged = subprocess.run(
        ["git", "show", ":messy.sh"], cwd=target, capture_output=True, text=True
    ).stdout
    assert staged == bad.read_text()
