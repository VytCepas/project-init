#!/usr/bin/env bash
# PI-939: approve workflow runs left at `action_required` on this repo's open
# bot-authored bump PRs, and say plainly what could not be approved.
#
# WHY THIS EXISTS. A PR opened with GITHUB_TOKEN is authored by
# github-actions[bot]. Under this repo's Actions approval policy a bot-actor
# run is queued as `action_required` rather than run, so the PR's head SHA
# carries no check runs at all. Branch protection then blocks the PR on
# contexts that will never report — a state that reads as "waiting" and is
# actually "stuck forever". The durable fix is opening the PR under a
# non-Actions identity (BUMP_PR_TOKEN); this is the recovery for when that
# secret is absent.
#
# WHAT IT CANNOT DO, stated so the caller does not over-trust it:
#   - The approve endpoint refuses runs it did not queue: "This run is not from
#     a fork pull request or queued by the Actions bot". The `Review status`
#     run triggered by a bot's review is exactly that case, so `review/decision`
#     is NOT recoverable here. A plain PR comment re-triggers that workflow;
#     monitor_pr.sh does it.
#   - GITHUB_TOKEN may be refused outright depending on repository settings.
#     That is reported, not retried, and never fails the caller.
#
# Exit code is always 0. This is a best-effort remedy attached to a workflow
# whose real job already succeeded; turning "could not un-stick a PR" into a
# failed weekly check would replace a quiet problem with a noisy one.
#
# Usage: approve_pending_bump_runs.sh [pr-number ...]
#        With no arguments, every open PR authored by github-actions[bot].
#        An explicitly named PR is author-checked too — the filter is a
#        boundary, not a discovery convenience.
#
# Env: APPROVE_WAIT_SECONDS (default 90), APPROVE_POLL_SECONDS (default 10).

set -uo pipefail

command -v gh >/dev/null 2>&1 || {
  echo "approve_pending_bump_runs: gh not found — nothing to do." >&2
  exit 0
}

# How long to wait for a PR's workflow runs to appear. PR event delivery and
# workflow-run creation are asynchronous, and this script runs seconds after
# the PR is opened — querying once can legitimately find nothing and then
# report "no runs waiting" about a PR that is about to be stuck (PR #944
# review, P2).
WAIT_SECONDS="${APPROVE_WAIT_SECONDS:-90}"
POLL_SECONDS="${APPROVE_POLL_SECONDS:-10}"

# `app/github-actions` is how gh spells the bot author.
BOT_AUTHOR="app/github-actions"

prs=()
[ $# -gt 0 ] && prs=("$@")
if [ ${#prs[@]} -eq 0 ]; then
  # A while-read loop, not `mapfile`: this repo gates on macOS bash 3.2, which
  # has no mapfile, and a script that only ever runs on the Linux runner still
  # gets read by people on the machine that cannot run it.
  while IFS= read -r n; do
    [ -n "$n" ] && prs+=("$n")
  done < <(
    gh pr list --state open --json number,author \
      --jq ".[] | select(.author.login == \"$BOT_AUTHOR\") | .number" 2>/dev/null
  )
fi

if [ ${#prs[@]} -eq 0 ]; then
  echo "approve_pending_bump_runs: no open bot-authored PRs."
  exit 0
fi

approved=0
refused=0

for pr in "${prs[@]}"; do
  [ -n "$pr" ] || continue

  # THE AUTHOR CHECK BELONGS HERE, not only in the discovery above. An explicit
  # `approve_pending_bump_runs.sh 123` bypassed the filter entirely and could
  # approve — that is, RUN — code on a PR a human or a third party opened,
  # defeating the exact boundary this script's header claims to respect
  # (PR #944 review, P1). Re-validating every PR costs one API call.
  author=$(gh pr view "$pr" --json author --jq '.author.login' 2>/dev/null) || continue
  if [ "$author" != "$BOT_AUTHOR" ]; then
    echo "PR #${pr}: author is '${author:-unknown}', not ${BOT_AUTHOR} — refusing to approve its runs."
    continue
  fi
  head_sha=$(gh pr view "$pr" --json headRefOid --jq '.headRefOid' 2>/dev/null) || continue
  [ -n "$head_sha" ] || continue

  # Runs are matched on the head SHA, not the branch: a branch-name match would
  # also pick up runs from an earlier push that are no longer what the PR is
  # blocked on.
  #
  # Polled, because "no runs yet" and "no runs ever" look identical at second
  # zero and mean opposite things. Two cheap queries per round rather than one
  # plus a JSON parse: `gh --jq` is already the idiom here and this repo keeps
  # `jq` itself off the dependency list.
  waited=0
  run_ids=""
  total_runs=0
  while :; do
    run_ids=$(
      gh api "repos/{owner}/{repo}/actions/runs?head_sha=${head_sha}&per_page=100" \
        --jq '.workflow_runs[] | select(.status == "action_required" or .conclusion == "action_required") | .id' \
        2>/dev/null
    )
    total_runs=$(
      gh api "repos/{owner}/{repo}/actions/runs?head_sha=${head_sha}&per_page=100" \
        --jq '.total_count' 2>/dev/null
    )
    # Something to approve, or runs reporting normally: either way the question
    # is answered and there is nothing left to wait for.
    [ -n "$run_ids" ] && break
    [ "${total_runs:-0}" -gt 0 ] 2>/dev/null && break
    [ "$waited" -ge "$WAIT_SECONDS" ] && break
    sleep "$POLL_SECONDS"
    waited=$((waited + POLL_SECONDS))
  done

  if [ -z "$run_ids" ]; then
    if [ "${total_runs:-0}" -gt 0 ] 2>/dev/null; then
      echo "PR #${pr}: ${total_runs} run(s) reporting normally — nothing to approve."
    else
      echo "PR #${pr}: NO workflow runs appeared within ${waited}s — that is the stuck state," \
        "not a healthy one. Check the Actions tab for 'Approve and run'."
    fi
    continue
  fi

  for run_id in $run_ids; do
    if err=$(gh api --method POST "repos/{owner}/{repo}/actions/runs/${run_id}/approve" 2>&1); then
      echo "PR #${pr}: approved run ${run_id}."
      approved=$((approved + 1))
    else
      echo "PR #${pr}: could NOT approve run ${run_id} — ${err%%$'\n'*}"
      refused=$((refused + 1))
    fi
  done

  if [ "$refused" -gt 0 ]; then
    echo "PR #${pr}: some runs still need a human 'Approve and run' in the Actions tab."
  fi
done

echo "approve_pending_bump_runs: ${approved} approved, ${refused} refused."
exit 0
