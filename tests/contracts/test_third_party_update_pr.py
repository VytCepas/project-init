"""PI-939: the weekly bump PR must be able to go green on its own.

A PR opened with `GITHUB_TOKEN` is authored by `github-actions[bot]`, and under
this repository's Actions approval policy a bot-actor run is queued at
`action_required` rather than run. The PR's head SHA then carries ZERO check
runs — not red, not green, never reported — so branch protection is
unsatisfiable by construction. Two bump PRs accumulated that way before anyone
noticed, because nothing about the state looks like failure.

These are text assertions on a workflow file, which is the weakest kind of
test: they cannot prove the PR goes green, only that the mechanism that would
make it go green is still wired. The acceptance test in #939 needs a real
scheduled run and is named there.
"""

from __future__ import annotations

from pathlib import Path

_WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "third-party-updates.yml"
)


def _body() -> str:
    return _WORKFLOW.read_text()


def test_the_pr_is_opened_under_a_non_actions_identity_when_one_exists():
    assert "secrets.BUMP_PR_TOKEN || github.token" in _body(), (
        "the bump PR must prefer a non-GITHUB_TOKEN identity; a PR authored by "
        "github-actions[bot] gets no check runs at all"
    )


def test_a_missing_secret_warns_instead_of_failing():
    """The secret is optional on purpose: a missing one must not turn the
    weekly check into a hard failure, and the fallback still opens a usable PR
    — but it must say so, or the resulting stuck PR has no explanation."""
    body = _body()
    assert "BUMP_PR_TOKEN_PRESENT" in body
    assert "::warning::" in body
    assert "action_required" in body, "the warning must name the state it produces"


def test_the_recovery_step_exists_and_cannot_fail_the_run():
    body = _body()
    assert "tools/approve_pending_bump_runs.sh" in body
    assert "continue-on-error: true" in body, (
        "a recovery step must never fail the weekly check whose real job succeeded"
    )
    assert "actions: write" in body, "approving a run needs the actions scope"


def test_the_recovery_script_is_honest_about_what_it_cannot_approve():
    """Measured against a live run on 2026-08-21: the approve endpoint returns
    403 "This run is not from a fork pull request or queued by the Actions bot"
    for the `pull_request_review` run, which is exactly the one gating
    review/decision. A remedy that silently covers half the problem is worse
    than one that names its half."""
    script = (
        Path(__file__).resolve().parents[2] / "tools" / "approve_pending_bump_runs.sh"
    ).read_text()
    assert "queued by the Actions bot" in script
    assert "review/decision" in script
    assert "exit 0" in script


def test_the_recovery_script_only_touches_bot_authored_prs():
    """It approves runs, and approving a run is running code — it must never
    reach a PR a human or a third party opened."""
    script = (
        Path(__file__).resolve().parents[2] / "tools" / "approve_pending_bump_runs.sh"
    ).read_text()
    assert 'select(.author.login == "app/github-actions")' in script
