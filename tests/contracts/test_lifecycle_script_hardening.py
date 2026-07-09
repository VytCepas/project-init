"""2026-07 code-review pass: content contracts on lifecycle scripts + hook wiring.

Each assertion pins a specific defect fixed in the review:

- ``start_issue.sh`` died silently on a nonexistent issue — under ``set -e``
  the command-substitution assignment killed the script (gh stderr discarded)
  before the "issue not found" branch could run.
- ``create_issue.sh`` leaked its mktemp file on the could-not-add early return.
- ``pre_commit_gate.sh`` fail-closed in uv projects that don't ship ruff: uv's
  "Failed to spawn" error was captured as bogus "Python lint errors".
- ``monitor_pr.sh`` printed "no reviewer has acted" (and hid the comments)
  after breaking early on review activity; the ROOT copy also predated the
  template's ``--admin`` opt-in for BLOCKED merges and the order-independent
  flag parser.
- The ``github_command_guard`` hook budget (10s) was smaller than one internal
  subprocess timeout (15s); a PreToolUse hook that exceeds its budget is
  killed and FAILS OPEN, so the guarded command executed unchecked.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIFECYCLE_SCRIPTS = _REPO_ROOT / "templates/lifecycle/dot_agents/scripts"
_ROOT_SCRIPTS = _REPO_ROOT / ".agents/scripts"


class TestStartIssueErrorPath:
    def test_issue_title_fetch_survives_set_e(self):
        s = (_LIFECYCLE_SCRIPTS / "start_issue.sh").read_text()
        m = re.search(r"^ISSUE_TITLE=\$\(gh issue view .*\)$", s, re.MULTILINE)
        assert m, "issue-title fetch line not found"
        assert "|| true" in m.group(0), (
            "under set -e a failing gh exit kills the script at the assignment, "
            "making the 'issue not found' branch unreachable"
        )


class TestCreateIssueTempFile:
    def test_could_not_add_early_return_removes_temp_file(self):
        s = (_LIFECYCLE_SCRIPTS / "create_issue.sh").read_text()
        block = re.search(
            r"\n(.*\n)?\s*echo \"Warning: could not add", s
        )
        assert block, "could-not-add warning not found"
        assert 'rm -f "$pdata_file"' in block.group(0), (
            "the could-not-add early return must clean up the mktemp file "
            "like the project-not-found path does"
        )


class TestPreCommitGateFailOpen:
    def test_uv_branch_probes_ruff_before_linting(self):
        for rel in (
            "templates/fallback/dot_agents/hooks/pre_commit_gate.sh",
            "plugins/project-init-workflow/hooks/pre_commit_gate.sh",
        ):
            s = (_REPO_ROOT / rel).read_text()
            assert "uv run ruff --version" in s, (
                f"{rel}: without the probe, a uv project that doesn't ship ruff "
                "captures uv's spawn error as bogus lint errors and blocks the commit"
            )


class TestMonitorPrReviewActivity:
    def test_early_break_surfaces_comments_not_false_timeout(self):
        for path in (
            _LIFECYCLE_SCRIPTS / "monitor_pr.sh",
            _ROOT_SCRIPTS / "monitor_pr.sh",
        ):
            s = path.read_text()
            assert "REVIEW_ACTIVITY=1" in s, f"{path}: early-break flag missing"
            assert "review comments posted" in s, (
                f"{path}: the early review-activity break must surface the "
                "comments instead of claiming no reviewer acted"
            )


class TestRootMonitorPrBackport:
    """The root copy is this repo's own tool (invoked by `dag_workflow.py
    finish`); the template fixes must not silently diverge from it again."""

    def test_admin_gate_backported(self):
        s = (_ROOT_SCRIPTS / "monitor_pr.sh").read_text()
        assert "ALLOW_ADMIN" in s
        assert '[ "$ALLOW_ADMIN" -eq 1 ]' in s, (
            "a BLOCKED merge state must require the explicit --admin opt-in, "
            "not auto-admin-merge past branch protection on cycle 0"
        )

    def test_flag_parser_is_order_independent(self):
        s = (_ROOT_SCRIPTS / "monitor_pr.sh").read_text()
        assert 'MODE="${2:-}"' not in s, (
            "the positional parser rejected documented usage like "
            "`monitor_pr.sh 12 --no-review` with 'Unknown option'"
        )
        assert "--admin)" in s
        assert "--merge)" in s


class TestGuardHookBudget:
    """A PreToolUse hook killed at its timeout fails OPEN, so the guard's hook
    budget must comfortably exceed its internal per-subprocess timeout."""

    _SUBPROCESS_TIMEOUT_RE = re.compile(r"subprocess\.run\(.*timeout=(\d+)")

    def _guard_timeout(self, hooks_cfg: dict) -> int:
        for group in hooks_cfg["hooks"]["PreToolUse"]:
            for hook in group["hooks"]:
                if "github_command_guard" in hook["command"]:
                    return hook["timeout"]
        raise AssertionError("github_command_guard hook not wired")

    def test_repo_settings_budget_exceeds_subprocess_timeout(self):
        cfg = json.loads((_REPO_ROOT / ".agents/settings.json").read_text())
        dag = (_REPO_ROOT / ".agents/hooks/dag_workflow.py").read_text()
        m = self._SUBPROCESS_TIMEOUT_RE.search(dag)
        assert m, "dag_workflow.py subprocess timeout not found"
        assert self._guard_timeout(cfg) >= 4 * int(m.group(1)), (
            "one hung gh call must never eat the whole hook budget — the "
            "guard makes several sequential gh/git calls before denying"
        )

    def test_plugin_hooks_budget_matches(self):
        cfg = json.loads(
            (_REPO_ROOT / "plugins/project-init-lifecycle/hooks/hooks.json").read_text()
        )
        assert self._guard_timeout(cfg) == 60

    def test_scaffolded_settings_template_budget_matches(self):
        s = (_REPO_ROOT / "templates/base/dot_agents/settings.json.tmpl").read_text()
        m = re.search(r'github_command_guard\.sh",\s*\n\s*"timeout": (\d+)', s)
        assert m, "guard hook entry not found in settings.json.tmpl"
        assert int(m.group(1)) == 60


class TestNojiraPrStateCheck:
    def test_existing_pr_short_circuit_checks_open_state(self):
        # `gh pr view` with no selector also resolves the most recent
        # CLOSED/MERGED PR for a reused branch name — the "already exists"
        # short-circuit must check the state like check_pr_opened does.
        for rel in (
            ".agents/hooks/dag_workflow.py",
            "templates/lifecycle/dot_agents/hooks/dag_workflow.py",
            "plugins/project-init-lifecycle/hooks/dag_workflow.py",
        ):
            s = (_REPO_ROOT / rel).read_text()
            assert '"url,state"' in s, f"{rel}: nojira PR reuse ignores PR state"


class TestStartIssueWorktreeKey:
    """#631: the derived project key must be pinned to the repository, not the
    working directory. Inside a linked worktree (``git worktree add
    ../zari-15-synthetic``) a ``--show-toplevel``-based derivation yields Z1S
    while the main checkout yields ZARI, so one repo accumulates mixed
    branch/PR keys — validate-pr only checks title<->branch consistency, so
    both pass."""

    def test_derivation_anchors_on_main_worktree(self):
        for path in (
            _LIFECYCLE_SCRIPTS / "start_issue.sh",
            _ROOT_SCRIPTS / "start_issue.sh",
        ):
            s = path.read_text()
            assert "_repo_root_name" in s, f"{path}: main-worktree helper missing"
            assert "--git-common-dir" in s, (
                f"{path}: repo-name derivation must anchor on the common git "
                "dir (main worktree), not the current worktree's toplevel"
            )
            # Both derivation sites (initials fallback + short-key widening)
            # must go through the helper; --show-toplevel may appear only
            # inside the helper's own last-resort fallback.
            body = s.split("_repo_root_name() {")[1]
            derive = body.split("derive_project_key() {")[1]
            assert "_repo_root_name" in derive, (
                f"{path}: derive_project_key bypasses the main-worktree helper"
            )
            assert "--show-toplevel" not in derive, (
                f"{path}: a --show-toplevel call after the helper reintroduces "
                "the per-worktree key drift"
            )

    def _extract_helper(self, script: Path) -> str:
        m = re.search(
            r"^_repo_root_name\(\) \{\n.*?\n\}$",
            script.read_text(),
            re.MULTILINE | re.DOTALL,
        )
        assert m, f"{script}: _repo_root_name not found"
        return m.group(0)

    def test_helper_returns_main_repo_name_from_linked_worktree(self, tmp_path):
        helper = self._extract_helper(_LIFECYCLE_SCRIPTS / "start_issue.sh")
        git_env = ["-c", "user.email=t@t", "-c", "user.name=t"]
        repo = tmp_path / "zarija"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", *git_env, "commit", "-q", "--allow-empty", "-m", "init"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "worktree", "add", "-q", "-b", "wt", "../zari-15-synthetic"],
            cwd=repo,
            check=True,
        )
        sub = tmp_path / "zari-15-synthetic" / "sub"
        sub.mkdir()
        for cwd in (repo, tmp_path / "zari-15-synthetic", sub):
            out = subprocess.run(
                ["bash", "-c", f"{helper}\n_repo_root_name"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            )
            assert out.stdout.strip() == "zarija", (
                f"from {cwd}: derived repo name {out.stdout.strip()!r} — the "
                "key must match the main checkout's"
            )

    def test_helper_handles_bare_repo_worktrees(self, tmp_path):
        """PR #702 review: with worktrees hanging off a bare repo
        (/srv/widget.git), the common dir IS the bare dir — dirname would
        derive the unrelated parent ('srv'), not the repo name ('widget')."""
        helper = self._extract_helper(_LIFECYCLE_SCRIPTS / "start_issue.sh")
        git_env = ["-c", "user.email=t@t", "-c", "user.name=t"]
        seed = tmp_path / "seed"
        seed.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=seed, check=True)
        subprocess.run(
            ["git", *git_env, "commit", "-q", "--allow-empty", "-m", "init"],
            cwd=seed,
            check=True,
        )
        srv = tmp_path / "srv"
        srv.mkdir()
        bare = srv / "widget.git"
        subprocess.run(
            ["git", "clone", "-q", "--bare", str(seed), str(bare)], check=True
        )
        wt = tmp_path / "widget-15-fix"
        subprocess.run(
            ["git", "--git-dir", str(bare), "worktree", "add", "-q", str(wt)],
            check=True,
        )
        out = subprocess.run(
            ["bash", "-c", f"{helper}\n_repo_root_name"],
            cwd=wt,
            capture_output=True,
            text=True,
            check=True,
        )
        assert out.stdout.strip() == "widget", (
            f"derived {out.stdout.strip()!r} from a bare-repo worktree — the "
            "bare dir's own name (minus .git), never its parent directory"
        )


class TestStartIssueSeedCommit:
    """#633: 'No commits between main and <branch>' despite the #433 seed.

    The seed heuristic compared HEAD against the LOCAL base ref, but GitHub
    judges emptiness against ITS base. A branch cut from origin/main while the
    local main lags behind (the normal worktree state on zarija) has
    rev-list main..HEAD non-empty, so the seed was skipped — and PR creation
    failed anyway. The seed must compare against the remote base, and PR
    creation must self-repair by seeding + retrying once if GitHub still
    rejects."""

    def test_seed_compares_against_remote_base(self):
        for path in (
            _LIFECYCLE_SCRIPTS / "start_issue.sh",
            _ROOT_SCRIPTS / "start_issue.sh",
        ):
            s = path.read_text()
            assert "_seed_base" in s, f"{path}: remote-base resolver missing"
            assert 'refs/remotes/origin/$BASE_BRANCH' in s, (
                f"{path}: the seed decision must prefer the remote-tracking "
                "base ref — the local base can lag behind what GitHub compares"
            )

    def test_pr_create_retries_once_after_seeding(self):
        for path in (
            _LIFECYCLE_SCRIPTS / "start_issue.sh",
            _ROOT_SCRIPTS / "start_issue.sh",
        ):
            s = path.read_text()
            retry_idx = s.find('grep -qi "No commits between"')
            assert retry_idx != -1, (
                f"{path}: a 'No commits between' rejection must trigger "
                "seed-and-retry, not strand a branch without a PR"
            )
            # The retry must re-push the seeded branch before re-creating.
            tail = s[retry_idx:]
            assert "push_branch.sh" in tail.split("Draft PR:")[0], (
                f"{path}: the seeded commit must be pushed before the retry"
            )

    def test_seed_decision_flips_when_local_base_lags(self, tmp_path):
        """Behavioral: replicate the zarija state — local main one commit
        behind origin/main, feature branch cut from origin/main. The old
        local-base comparison says 'has commits' (skip seed); the remote-base
        comparison correctly says 'level' (seed)."""
        s = (_LIFECYCLE_SCRIPTS / "start_issue.sh").read_text()
        m = re.search(
            r"^_seed_base\(\) \{\n.*?\n\}$", s, re.MULTILINE | re.DOTALL
        )
        assert m, "_seed_base not found"
        helper = m.group(0)

        git_env = ["-c", "user.email=t@t", "-c", "user.name=t"]
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)

        def git(*args: str) -> str:
            r = subprocess.run(
                ["git", *git_env, *args],
                cwd=clone,
                check=True,
                capture_output=True,
                text=True,
            )
            return r.stdout.strip()

        git("commit", "-q", "--allow-empty", "-m", "c1")
        git("push", "-q", "-u", "origin", "HEAD:main")
        git("checkout", "-q", "-B", "main", "origin/main")
        git("commit", "-q", "--allow-empty", "-m", "c2")
        git("push", "-q", "origin", "main")
        git("reset", "-q", "--hard", "HEAD~1")  # local main lags origin/main
        git("checkout", "-q", "-b", "feat/T-1-x", "origin/main")

        script = f'BASE_BRANCH=main\n{helper}\ngit rev-list "$(_seed_base)..HEAD" | wc -l'
        out = subprocess.run(
            ["bash", "-c", script],
            cwd=clone,
            capture_output=True,
            text=True,
            check=True,
        )
        assert out.stdout.strip() == "0", (
            "branch cut from origin/main must count as level with the base "
            "(seed fires) even though the stale local main is behind"
        )
        # The pre-#633 comparison really would have skipped the seed here.
        old = subprocess.run(
            ["bash", "-c", 'git rev-list "main..HEAD" | wc -l'],
            cwd=clone,
            capture_output=True,
            text=True,
            check=True,
        )
        assert old.stdout.strip() != "0", (
            "fixture no longer reproduces the stale-local-base state the "
            "regression test is meant to pin"
        )


class TestMonitorPrMergeRetry:
    """#632: the merge fires the instant the last check settles, but GitHub's
    mergeability lags a few seconds — the single-shot merge failed ('Merge
    already in progress', 'not mergeable') while the PR was CLEAN, and a
    manual re-run seconds later succeeded every time."""

    def test_merge_paths_use_retry(self):
        for path in (
            _LIFECYCLE_SCRIPTS / "monitor_pr.sh",
            _ROOT_SCRIPTS / "monitor_pr.sh",
        ):
            s = path.read_text()
            assert "_merge_with_retry" in s, f"{path}: merge retry missing"
            assert "_pr_is_merged" in s, (
                f"{path}: a failed attempt whose merge actually landed "
                "server-side must count as success"
            )
            # No single-shot non-admin merge may remain outside the helpers.
            body = s.split("_merge_with_retry() {")[1]
            plain = [
                ln
                for ln in body.splitlines()
                if "pr merge" in ln
                and "--admin" not in ln
                and "--auto" not in ln
                and not ln.lstrip().startswith("#")
                and "_merge_with_retry() " not in ln
            ]
            # the helper's own two attempts are inside its function body,
            # which ends at the first unindented closing brace
            helper_body = body.split("\n}\n")[0]
            outside = [ln for ln in plain if ln not in helper_body.splitlines()]
            assert not outside, (
                f"{path}: single-shot merge outside _merge_with_retry: {outside}"
            )

    def _extract(self, script: Path, *names: str) -> str:
        s = script.read_text()
        parts = []
        for name in names:
            m = re.search(
                rf"^{re.escape(name)}\(\) \{{\n.*?\n\}}$",
                s,
                re.MULTILINE | re.DOTALL,
            )
            assert m, f"{script}: {name} not found"
            parts.append(m.group(0))
        return "\n".join(parts)

    def _run_with_stub(self, tmp_path: Path, stub: str, script_tail: str) -> subprocess.CompletedProcess:
        helpers = self._extract(
            _LIFECYCLE_SCRIPTS / "monitor_pr.sh",
            "_run_gh",
            "_pr_is_merged",
            "_merge_with_retry",
        )
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(stub)
        gh.chmod(0o755)
        script = (
            f"export PATH={bin_dir}:$PATH\n"
            f"export PI_MERGE_RETRY_DELAYS='0 0 0'\n"
            f"PR_NUMBER=12\n{helpers}\n{script_tail}"
        )
        return subprocess.run(
            ["bash", "-c", script],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_retry_succeeds_after_transient_failure(self, tmp_path):
        stub = (
            "#!/usr/bin/env bash\n"
            'if [ "$1 $2" = "pr merge" ]; then\n'
            "  n=$(cat n 2>/dev/null || echo 0); n=$((n+1)); echo $n > n\n"
            '  [ "$n" -ge 2 ] && exit 0\n'
            '  echo "GraphQL: Merge already in progress (mergePullRequest)" >&2; exit 1\n'
            "fi\n"
            'echo "OPEN"\n'
        )
        r = self._run_with_stub(tmp_path, stub, "_merge_with_retry")
        assert r.returncode == 0, f"retry should recover: {r.stdout} {r.stderr}"
        assert (tmp_path / "n").read_text().strip() == "2", "expected exactly 2 attempts"

    def test_already_merged_counts_as_success(self, tmp_path):
        stub = (
            "#!/usr/bin/env bash\n"
            'if [ "$1 $2" = "pr merge" ]; then\n'
            '  echo "GraphQL: Merge already in progress (mergePullRequest)" >&2; exit 1\n'
            "fi\n"
            # any `gh pr view --json state -q .state` probe reports MERGED
            'echo "MERGED"\n'
        )
        r = self._run_with_stub(tmp_path, stub, "_merge_with_retry")
        assert r.returncode == 0, (
            f"a merge that landed server-side must not be an error: {r.stdout} {r.stderr}"
        )

    def test_persistent_failure_still_fails(self, tmp_path):
        stub = (
            "#!/usr/bin/env bash\n"
            'if [ "$1 $2" = "pr merge" ]; then\n'
            "  n=$(cat n 2>/dev/null || echo 0); echo $((n+1)) > n\n"
            '  echo "merge blocked" >&2; exit 1\n'
            "fi\n"
            'echo "OPEN"\n'
        )
        r = self._run_with_stub(tmp_path, stub, "_merge_with_retry")
        assert r.returncode != 0, "an unmergeable PR must still fail"
        assert int((tmp_path / "n").read_text().strip()) == 4, (
            "expected 3 backoff attempts + 1 final attempt"
        )
