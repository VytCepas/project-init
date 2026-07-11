"""Shift-left commit/push gates: catch static issues before they reach CI.

Three layers, each closing a gap the others leave:

- **git `pre-commit`** now runs `just lint` (not only gitleaks), so a *human*
  committing from a terminal/IDE is held to the same static gate as CI — the
  Claude `pre_commit_gate.sh` only fires for agent-driven commits.
- **git `pre-push`** runs the fast `just fast-ci` (lint + parallel tests), so
  the common break is caught locally without re-running the full `just ci` (CI's
  job) before every push (PI-759).
- **`pre_commit_gate.sh`** (the agent commit gate) gained a per-file shell block
  so staged `.sh` files are `shfmt`/`shellcheck`'d even when `just` is absent.

All three fail-open when their tooling is missing (CI is the hard backstop) and
are bypassable with `--no-verify`, mirroring the existing gitleaks posture.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import fallback_preset, fallback_variables, make_variables


def _require_tool(name: str) -> None:
    """Fail in CI, skip locally, when `name` is not on PATH.

    `skipif` here meant these tests skipped in CI for as long as `just` was
    absent from the runner (#737) — the hook's two most interesting behaviours
    were never exercised by a gate. A skipped test is not a gate; the same shape
    as #733 (bun) and #719 (actionlint). `ci.yml` installs both tools, so a
    missing one is a broken workflow, not a reason to pass quietly.
    """
    if shutil.which(name):
        return
    if os.environ.get("CI"):
        pytest.fail(f"{name} is not on PATH — CI must install it (ci.yml) or this gate tests nothing (#737).")
    pytest.skip(f"{name} not available — install it to run this gate locally")


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
    # Lints the staged snapshot (strips unstaged changes via a patch), not the
    # working tree, so an unstaged fix can't mask a staged error.
    assert "git apply -R" in pre_commit
    # Untracked files are linted too — the failure path says so, so a false
    # failure from an unrelated untracked file is diagnosable, not baffling.
    assert "git ls-files --others --exclude-standard" in pre_commit
    # Fail-closed when tooling is present, bypassable, and secrets still scanned.
    assert "--no-verify" in pre_commit
    assert "gitleaks" in pre_commit


def test_git_pre_push_runs_fast_ci(tmp_target: Path):
    _, pre_push = _git_hooks(tmp_target)
    # The gate command is the lighter `just fast-ci` (lint + parallel tests),
    # not the full `just ci` — CI is the full backstop (PI-759). Assert the actual
    # invocation, not a substring that also appears in the explanatory comment.
    assert "just fast-ci" in pre_push
    assert "just --show fast-ci" in pre_push
    # Only for a real branch push, and still bypassable in an emergency.
    assert "PUSHING_BRANCH" in pre_push
    assert "--no-verify" in pre_push
    # Skips (not tests) a dirty worktree — the pushed tree is the committed one.
    assert "git status --porcelain" in pre_push


def test_pre_commit_gate_has_per_file_shell_block(tmp_target: Path):
    """The agent commit gate must shellcheck/shfmt staged .sh without needing `just`."""
    scaffold(tmp_target, fallback_preset(), fallback_variables(language="python", python="true"))
    gate = (tmp_target / ".agents" / "hooks" / "pre_commit_gate.sh").read_text()
    assert "shfmt -w -i 2" in gate
    assert "shellcheck -S error -x" in gate
    # A shfmt parse error (nonzero exit) is recorded as blocking, not swallowed,
    # so a broken script can't pass when shellcheck is unavailable.
    assert "Shell format errors (shfmt)" in gate


def test_pre_commit_gate_autofixes_staged_shell(tmp_path: Path):
    """End-to-end: a badly-formatted staged .sh is shfmt-fixed and re-staged."""
    _require_tool("shfmt")
    target = tmp_path / "proj"
    scaffold(target, fallback_preset(), fallback_variables(language="python", python="true"))
    hook = target / ".agents" / "hooks" / "pre_commit_gate.sh"

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


def test_pre_commit_gate_blocks_a_broken_staged_shell(tmp_path: Path):
    """A staged .sh shfmt can't parse must block the commit (deny), not slip through."""
    _require_tool("shfmt")
    target = tmp_path / "proj"
    scaffold(target, fallback_preset(), fallback_variables(language="python", python="true"))
    hook = target / ".agents" / "hooks" / "pre_commit_gate.sh"
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=target, check=True)

    broken = target / "broken.sh"
    broken.write_text("#!/usr/bin/env bash\nif [ ; then\n")  # unparseable
    subprocess.run(["git", "add", "broken.sh"], cwd=target, check=True)

    payload = json.dumps({"tool_input": {"command": "git commit -m x"}})
    result = subprocess.run(
        ["bash", str(hook)], input=payload, cwd=target, capture_output=True, text=True
    )
    # The gate signals a block via a PreToolUse deny decision on stdout.
    assert '"permissionDecision": "deny"' in result.stdout, result.stdout


def test_git_pre_commit_lints_the_index_not_the_worktree(tmp_path: Path):
    """A staged lint error must not be masked by an unstaged fix (Codex #596).

    Uses a sentinel `just lint` recipe (fails when the file contains BAD) so the
    check is independent of the real ruff toolchain — the point under test is the
    stash-the-index mechanism, not what `just lint` runs.
    """
    _require_tool("just")
    target = tmp_path / "proj"
    scaffold(target, load_preset("obsidian-only"), make_variables(language="python", python="true"))
    hook = target / ".github" / "hooks" / "pre-commit"
    # Replace the scaffolded justfile with a sentinel lint recipe.
    (target / "justfile").write_text(
        'lint:\n    #!/usr/bin/env bash\n    if grep -q BAD x.txt; then exit 1; fi\n'
    )

    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=target, check=True)
    (target / "x.txt").write_text("INIT\n")
    subprocess.run(["git", "add", "x.txt", "justfile"], cwd=target, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=target, check=True)

    # Stage the BAD version, then leave a GOOD *unstaged* fix on top.
    (target / "x.txt").write_text("BAD\n")
    subprocess.run(["git", "add", "x.txt"], cwd=target, check=True)
    (target / "x.txt").write_text("GOOD\n")

    result = subprocess.run(["bash", str(hook)], cwd=target, capture_output=True, text=True)

    # The staged (index) content is BAD, so the hook must block the commit …
    assert result.returncode != 0, "pre-commit passed on a staged lint error hidden by an unstaged fix"
    # … and the developer's unstaged fix must be restored intact afterward.
    assert (target / "x.txt").read_text() == "GOOD\n", "unstaged changes were not restored"


def test_git_pre_commit_ignores_unstaged_mess_on_a_clean_index(tmp_path: Path):
    """The inverse of the above: unrelated dirty WIP must not fail a clean commit."""
    _require_tool("just")
    target = tmp_path / "proj"
    scaffold(target, load_preset("obsidian-only"), make_variables(language="python", python="true"))
    hook = target / ".github" / "hooks" / "pre-commit"
    (target / "justfile").write_text(
        'lint:\n    #!/usr/bin/env bash\n    if grep -q BAD x.txt; then exit 1; fi\n'
    )
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=target, check=True)
    (target / "x.txt").write_text("INIT\n")
    subprocess.run(["git", "add", "x.txt", "justfile"], cwd=target, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=target, check=True)

    # Stage a clean (GOOD) version, then leave a BAD *unstaged* mess on top.
    (target / "x.txt").write_text("GOOD\n")
    subprocess.run(["git", "add", "x.txt"], cwd=target, check=True)
    (target / "x.txt").write_text("BAD\n")

    result = subprocess.run(["bash", str(hook)], cwd=target, capture_output=True, text=True)

    # The index is clean, so the commit must be allowed despite the dirty worktree …
    assert result.returncode == 0, f"pre-commit blocked a clean staged commit:\n{result.stderr}"
    # … and the unstaged mess restored untouched (no conflict markers).
    assert (target / "x.txt").read_text() == "BAD\n", "unstaged changes were not restored"
