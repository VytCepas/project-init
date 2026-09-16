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
import pathlib
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
        pytest.fail(
            f"{name} is not on PATH — CI must install it (ci.yml) or this gate tests nothing (#737)."
        )
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


def _fake_just(bin_dir: Path, record: Path) -> None:
    """A `just` that reports which repository a nested git command resolves to.

    The hook only runs the recipe when `just --show fast-ci` succeeds, so the
    stub answers that too. `fast-ci` then does what a real suite does — `git
    init` a scratch repo and use it — and writes the absolute git dir that git
    actually chose. That is the observation: with the environment inherited, git
    ignores the scratch repo and answers with the repo being pushed from.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "just"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "--show" ]; then exit 0; fi\n'
        'scratch="$(mktemp -d)"\n'
        'cd "$scratch" || exit 1\n'
        "git init -q . >/dev/null 2>&1\n"
        f'git rev-parse --absolute-git-dir > "{record}" 2>&1\n'
        "exit 0\n"
    )
    stub.chmod(0o755)


def _push_stdin(sha: str) -> str:
    """What git feeds a pre-push hook for one branch push."""
    return f"refs/heads/chore/nojira-gate {sha} refs/heads/chore/nojira-gate {sha}\n"


def test_pre_push_does_not_point_the_recipe_at_the_pushing_repo(tmp_target: Path):
    """The gate must not hand its own GIT_DIR to the suite it runs.

    git exports GIT_DIR (and GIT_WORK_TREE/GIT_INDEX_FILE in a worktree) to every
    hook, so an unguarded `just fast-ci` gives every git subprocess in the suite a
    pointer back at the repository being pushed from. Measured before the fix:
    413 passed -> 5 failed here, 1508 passed -> 185 failed in
    projects-orchestrator, and — worse than the red — the tests wrote to the
    developer's index, which is where a pile of phantom staged deletions came
    from.

    Asserting the rendered TEXT would not catch this: a misspelled `env -u` entry
    reads fine and restores the regression. So the hook is actually executed, with
    the environment git would really hand it, and the observation is which
    repository a nested `git init` ends up talking to.
    """
    _require_tool("git")
    scaffold(
        tmp_target, load_preset("obsidian-only"), make_variables(language="python", python="true")
    )
    (tmp_target / "justfile").write_text("fast-ci:\n\t@true\n")
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_target, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_target, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e.st", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_target,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_target, check=True, capture_output=True, text=True
    ).stdout.strip()

    # OUTSIDE the repo, both of them. The gate skips on a dirty worktree, so a
    # stub or a scratch file left inside the tree makes this test pass by never
    # running the thing it is testing — which is how the first draft of it
    # "passed" against an unfixed hook.
    record = tmp_target.parent / "resolved-git-dir.txt"
    bin_dir = tmp_target.parent / "fakebin"
    _fake_just(bin_dir, record)

    pushing_git_dir = (tmp_target / ".git").resolve()
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    # Exactly what git exports to a hook. This is the poison, and it is not
    # synthetic: reproduce it by hand with `git push` and the same variables are
    # in the hook's environment.
    env["GIT_DIR"] = str(pushing_git_dir)
    env["GIT_WORK_TREE"] = str(tmp_target)
    env["GIT_INDEX_FILE"] = str(pushing_git_dir / "index")

    hook = tmp_target / ".github" / "hooks" / "pre-push"
    proc = subprocess.run(
        ["bash", str(hook), "origin", "https://example.invalid/r.git"],
        cwd=tmp_target,
        input=_push_stdin(head),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"hook failed: {proc.stdout}\n{proc.stderr}"
    assert "skipping" not in proc.stderr, (
        f"the gate skipped instead of running, so nothing here was exercised: {proc.stderr}"
    )
    assert record.exists(), (
        "the recipe never ran, so this test proves nothing about the environment "
        f"it would have seen: {proc.stdout}\n{proc.stderr}"
    )
    resolved = pathlib.Path(record.read_text().strip())
    assert resolved != pushing_git_dir, (
        "the recipe inherited the pushing repository's GIT_DIR — every git "
        "subprocess in the suite, including a test's own `git init`, is pointed "
        f"at {pushing_git_dir} instead of its own tmpdir"
    )


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
    subprocess.run(["bash", str(hook)], input=payload, cwd=target, capture_output=True, text=True)

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
        "lint:\n    #!/usr/bin/env bash\n    if grep -q BAD x.txt; then exit 1; fi\n"
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
    assert result.returncode != 0, (
        "pre-commit passed on a staged lint error hidden by an unstaged fix"
    )
    # … and the developer's unstaged fix must be restored intact afterward.
    assert (target / "x.txt").read_text() == "GOOD\n", "unstaged changes were not restored"


def test_git_pre_commit_ignores_unstaged_mess_on_a_clean_index(tmp_path: Path):
    """The inverse of the above: unrelated dirty WIP must not fail a clean commit."""
    _require_tool("just")
    target = tmp_path / "proj"
    scaffold(target, load_preset("obsidian-only"), make_variables(language="python", python="true"))
    hook = target / ".github" / "hooks" / "pre-commit"
    (target / "justfile").write_text(
        "lint:\n    #!/usr/bin/env bash\n    if grep -q BAD x.txt; then exit 1; fi\n"
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


@pytest.mark.parametrize("victim_kind", ["symlink", "regular_file"])
def test_git_pre_commit_never_destroys_unstaged_work_it_cannot_isolate(
    tmp_path: Path, victim_kind: str
):
    """A diff `git apply` mishandles must not cost the user their unstaged work (PI-811).

    `git apply` is not atomic: on a fatal error it can delete files and *then* exit
    non-zero. The hook used to read that non-zero exit as "nothing was touched",
    discard the only copy of the patch, and install no restore trap — so a single
    `git commit` silently destroyed uncommitted work and still exited 0.

    Both replacement shapes are covered, because they fail identically but only one
    is visible in the file mode:

    - `symlink`: a tracked symlink replaced by a directory (what `project-init
      upgrade` does to `.claude`) — raw mode 120000.
    - `regular_file`: a tracked regular file replaced by a directory — mode stays
      100644, so a symlink-mode check alone sails right past it.

    Hence the hook's guard is "is this path now a directory", not "is this a
    symlink". Two guards that do NOT work, both tried: `git apply -R --check`
    returns 0 on these diffs, and git reports the replacement as a plain delete so
    `--diff-filter=T` is empty.
    """
    _require_tool("just")
    target = tmp_path / "proj"
    scaffold(target, load_preset("obsidian-only"), make_variables(language="python", python="true"))
    hook = target / ".github" / "hooks" / "pre-commit"
    (target / "justfile").write_text("lint:\n    @echo LINT_OK\n")

    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=target, check=True)
    (target / "a.txt").write_text("ORIG\n")
    if victim_kind == "symlink":
        (target / "victim").symlink_to("a.txt")
    else:
        (target / "victim").write_text("F\n")
    subprocess.run(["git", "add", "a.txt", "victim", "justfile"], cwd=target, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=target, check=True)

    # Unstaged: precious WIP, plus the -> directory replacement that makes
    # `git apply -R` blow up partway through.
    (target / "a.txt").write_text("PRECIOUS_WIP\n")
    (target / "victim").unlink()
    (target / "victim").mkdir()
    (target / "victim" / "inside.txt").write_text("x\n")
    # …and something actually staged, so a commit is genuinely in flight.
    (target / "staged.txt").write_text("s\n")
    subprocess.run(["git", "add", "staged.txt"], cwd=target, check=True)

    result = subprocess.run(["bash", str(hook)], cwd=target, capture_output=True, text=True)

    # The whole point: the unstaged edit survives.
    assert (target / "a.txt").read_text() == "PRECIOUS_WIP\n", (
        "pre-commit destroyed unstaged work while trying to isolate the index"
    )
    # …and it survives by *falling back*, not by aborting: the staged content is
    # clean, so the commit must still be allowed. Without this the test would pass
    # on a hook that simply refused every commit.
    assert result.returncode == 0, f"pre-commit blocked a clean staged commit:\n{result.stderr}"
    # …and the fallback is announced, because it silently drops the index-isolation
    # guarantee (unstaged changes are now in lint scope).
    assert "WORKING TREE" in result.stderr, (
        f"fallback to worktree linting was not announced:\n{result.stderr}"
    )
