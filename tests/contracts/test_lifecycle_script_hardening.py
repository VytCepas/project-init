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
        block = re.search(r"\n(.*\n)?\s*echo \"Warning: could not add", s)
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
        subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(bare)], check=True)
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
            assert "refs/remotes/origin/$BASE_BRANCH" in s, (
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
        m = re.search(r"^_seed_base\(\) \{\n.*?\n\}$", s, re.MULTILINE | re.DOTALL)
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
            # No single-shot non-admin merge may remain outside the helper.
            # Bound the helper's span by line index (its body ends at the
            # first bare closing brace) so a text-identical line elsewhere
            # can't be mistaken for one of the helper's own attempts.
            lines = s.split("_merge_with_retry() {")[1].splitlines()
            helper_end = next(i for i, ln in enumerate(lines) if ln == "}")
            outside = [
                ln
                for ln in lines[helper_end + 1 :]
                if "pr merge" in ln
                and "--admin" not in ln
                and "--auto" not in ln
                and not ln.lstrip().startswith("#")
            ]
            assert not outside, f"{path}: single-shot merge outside _merge_with_retry: {outside}"

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

    def _run_with_stub(
        self, tmp_path: Path, stub: str, script_tail: str
    ) -> subprocess.CompletedProcess:
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


class TestMonitorPrLocalBranchCleanup:
    """#678: `--delete-branch` removes the remote branch, but the local one
    survives deferred/raced merges — every merged PR left a branch behind for
    the operator to hand-delete. After a confirmed merge the script deletes
    the local head branch, but ONLY when its SHA equals the PR's headRefOid
    (no unpushed work); diverged branches stay, absent branches no-op."""

    _GIT_ENV = ["-c", "user.email=t@t", "-c", "user.name=t"]

    def test_every_confirmed_merge_triggers_cleanup(self):
        for path in (
            _LIFECYCLE_SCRIPTS / "monitor_pr.sh",
            _ROOT_SCRIPTS / "monitor_pr.sh",
        ):
            lines = path.read_text().splitlines()
            for i, ln in enumerate(lines):
                if 'echo "Merged PR' in ln:
                    window = "\n".join(lines[i + 1 : i + 3])
                    assert "_cleanup_local_branch" in window, (
                        f"{path}:{i + 1}: confirmed merge without local cleanup"
                    )
                if "Auto-merge enabled" in ln:
                    window = "\n".join(lines[i + 1 : i + 3])
                    assert "_cleanup_local_branch" not in window, (
                        f"{path}:{i + 1}: deferred auto-merge must NOT delete "
                        "the still-unmerged local branch"
                    )

    def _setup_repo(self, tmp_path: Path) -> Path:
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
        self._git(clone, "commit", "-q", "--allow-empty", "-m", "c1")
        self._git(clone, "push", "-q", "-u", "origin", "HEAD:main")
        self._git(clone, "checkout", "-q", "-B", "main", "origin/main")
        return clone

    def _git(self, cwd: Path, *args: str) -> str:
        r = subprocess.run(
            ["git", *self._GIT_ENV, *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
        return r.stdout.strip()

    def _run_cleanup(
        self,
        tmp_path: Path,
        clone: Path,
        head_oid: str,
        pr_state: str = "MERGED",
    ) -> subprocess.CompletedProcess:
        s = (_LIFECYCLE_SCRIPTS / "monitor_pr.sh").read_text()
        parts = []
        for name in ("_pr_is_merged", "_cleanup_local_branch"):
            m = re.search(rf"^{name}\(\) \{{\n.*?\n\}}$", s, re.MULTILINE | re.DOTALL)
            assert m, f"{name} not found"
            parts.append(m.group(0))
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        gh = bin_dir / "gh"
        # `pr view --json state` probes get the PR state; the head-ref query
        # gets "name oid" — matching the two real gh calls cleanup makes.
        gh.write_text(
            "#!/usr/bin/env bash\n"
            'case "$*" in\n'
            f'*"--json state"*) echo "{pr_state}" ;;\n'
            f'*) echo "feat/T-9-x {head_oid}" ;;\n'
            "esac\n"
        )
        gh.chmod(0o755)
        body = "\n".join(parts)
        script = f"export PATH={bin_dir}:$PATH\nset -euo pipefail\nPR_NUMBER=9\n{body}\n_cleanup_local_branch"
        return subprocess.run(
            ["bash", "-c", script],
            cwd=clone,
            capture_output=True,
            text=True,
            check=False,
        )

    def _branch_exists(self, clone: Path, name: str) -> bool:
        return (
            subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{name}"],
                cwd=clone,
            ).returncode
            == 0
        )

    def test_deletes_matching_branch_and_returns_to_base(self, tmp_path):
        clone = self._setup_repo(tmp_path)
        self._git(clone, "checkout", "-q", "-b", "feat/T-9-x")
        self._git(clone, "commit", "-q", "--allow-empty", "-m", "seed")
        sha = self._git(clone, "rev-parse", "HEAD")

        r = self._run_cleanup(tmp_path, clone, sha)
        assert r.returncode == 0, r.stderr
        assert "cleaned up local branch feat/T-9-x" in r.stdout
        assert not self._branch_exists(clone, "feat/T-9-x")
        assert self._git(clone, "branch", "--show-current") == "main"

    def test_keeps_diverged_branch(self, tmp_path):
        clone = self._setup_repo(tmp_path)
        self._git(clone, "checkout", "-q", "-b", "feat/T-9-x")
        self._git(clone, "commit", "-q", "--allow-empty", "-m", "seed")
        merged_sha = self._git(clone, "rev-parse", "HEAD")
        self._git(clone, "commit", "-q", "--allow-empty", "-m", "unpushed")

        r = self._run_cleanup(tmp_path, clone, merged_sha)
        assert r.returncode == 0, r.stderr
        assert "differs from the merged head" in r.stdout
        assert self._branch_exists(clone, "feat/T-9-x"), (
            "a branch with unpushed work must never be deleted"
        )

    def test_noop_when_branch_absent(self, tmp_path):
        clone = self._setup_repo(tmp_path)
        r = self._run_cleanup(tmp_path, clone, "0" * 40)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "", "absent local branch must no-op silently"

    def test_dirty_worktree_left_alone_silently(self, tmp_path):
        clone = self._setup_repo(tmp_path)
        self._git(clone, "checkout", "-q", "-b", "feat/T-9-x")
        self._git(clone, "commit", "-q", "--allow-empty", "-m", "seed")
        sha = self._git(clone, "rev-parse", "HEAD")
        (clone / "wip.txt").write_text("uncommitted\n")

        r = self._run_cleanup(tmp_path, clone, sha)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "", "dirty-worktree skip must be silent (#678)"
        assert self._branch_exists(clone, "feat/T-9-x")
        assert self._git(clone, "branch", "--show-current") == "feat/T-9-x"

    def test_enqueued_but_unmerged_pr_keeps_branch(self, tmp_path):
        """PR #707 review: with a merge queue, a successful merge command may
        have only ENQUEUED the still-open PR — cleanup must not delete the
        branch until the server says MERGED."""
        clone = self._setup_repo(tmp_path)
        self._git(clone, "checkout", "-q", "-b", "feat/T-9-x")
        self._git(clone, "commit", "-q", "--allow-empty", "-m", "seed")
        sha = self._git(clone, "rev-parse", "HEAD")

        r = self._run_cleanup(tmp_path, clone, sha, pr_state="OPEN")
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == ""
        assert self._branch_exists(clone, "feat/T-9-x"), (
            "an enqueued-but-unmerged PR's local branch must survive"
        )


class TestPrCreationDoesNotRelyOnGhInference:
    """A narrow fetch refspec makes `gh pr create` abort after a successful push.

    `gh` resolves the head branch through the local remote-tracking ref. A
    `--single-branch` or `--depth` clone configures only
    ``remote.origin.fetch = +refs/heads/main:refs/remotes/origin/main``, so no
    tracking ref is ever created for the branch just pushed — and gh aborts with
    "you must first push the current branch to a remote, or use the --head flag"
    even though the push succeeded and the branch exists on the remote.

    Reproduced against a real clone: with the narrow refspec, `git rev-parse
    @{upstream}` fails with "not stored as a remote-tracking branch" and PR
    creation dies; widening the refspec and re-fetching fixes it. Both lifecycle
    entry points therefore name the branch instead of letting gh infer it.
    """

    def test_start_issue_passes_head_explicitly(self, tmp_path: Path):
        """Behavioural: run the real _create_pr with a fake gh recording argv."""
        source = (_LIFECYCLE_SCRIPTS / "start_issue.sh").read_text()
        m = re.search(r"^_create_pr\(\) \{\n.*?\n\}$", source, re.MULTILINE | re.DOTALL)
        assert m, "_create_pr not found in start_issue.sh"

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        argv_log = tmp_path / "argv"
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/usr/bin/env bash\n"
            f'printf "%s\\n" "$@" > {argv_log}\n'
            'echo "https://github.com/o/r/pull/1"\n'
        )
        gh.chmod(0o755)

        script = (
            f"export PATH={bin_dir}:$PATH\n"
            "set -euo pipefail\n"
            'BASE_BRANCH=main\nBRANCH=feat/PI-1-x\nPR_TITLE="feat(PI-1): x"\nPR_BODY="Closes #1"\n'
            f"{m.group(0)}\n_create_pr\n"
        )
        proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr

        argv = argv_log.read_text().splitlines()
        assert "--head" in argv, f"gh pr create invoked without --head: {argv}"
        assert argv[argv.index("--head") + 1] == "feat/PI-1-x", argv
        # The base must still be passed — a --head fix that dropped it would
        # silently retarget PRs at the repo default.
        assert "--base" in argv and argv[argv.index("--base") + 1] == "main", argv

    def test_create_pr_nojira_passes_head_explicitly(self, tmp_path: Path):
        """The other entry point: dag_workflow's create-pr-nojira."""
        import importlib.util

        hook = _REPO_ROOT / "templates/lifecycle/dot_agents/hooks/dag_workflow.py"
        spec = importlib.util.spec_from_file_location("dagw_head", hook)
        assert spec and spec.loader
        dag = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dag)

        calls: list[list[str]] = []

        def fake_gh(args: list[str], **kwargs: object) -> tuple[int, str]:
            calls.append(args)
            if args[:2] == ["pr", "view"]:
                # No open PR yet, so creation proceeds.
                return 1, ""
            return 0, "https://github.com/o/r/pull/2"

        dag._gh = fake_gh  # type: ignore[assignment]
        dag._git = lambda args, **kw: (0, "")  # type: ignore[assignment]
        dag._current_branch = lambda: "feat/nojira-x"  # type: ignore[assignment]
        dag.cmd_push = lambda *a, **k: 0  # type: ignore[assignment]

        rc = dag.cmd_create_pr_nojira("feat", "Some title", None, None)
        assert rc == 0, calls

        create = [c for c in calls if c[:2] == ["pr", "create"]]
        assert create, f"no gh pr create call recorded: {calls}"
        args = create[0]
        assert "--head" in args, f"create-pr-nojira invoked gh without --head: {args}"
        assert args[args.index("--head") + 1] == "feat/nojira-x", args

        # The existing-PR probe must also name the branch, for the same reason.
        view = [c for c in calls if c[:2] == ["pr", "view"]]
        assert view, f"no gh pr view probe recorded: {calls}"
        assert "feat/nojira-x" in view[0], f"pr view relies on inference: {view[0]}"
