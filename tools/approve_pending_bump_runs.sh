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

set -uo pipefail

command -v gh >/dev/null 2>&1 || {
  echo "approve_pending_bump_runs: gh not found — nothing to do." >&2
  exit 0
}

prs=()
[ $# -gt 0 ] && prs=("$@")
if [ ${#prs[@]} -eq 0 ]; then
  # `app/github-actions` is how gh spells the bot author. Restrict to it: this
  # script approves runs, and approving a run is running code, so it must never
  # reach a PR a human or a third party opened.
  # A while-read loop, not `mapfile`: this repo gates on macOS bash 3.2, which
  # has no mapfile, and a script that only ever runs on the Linux runner still
  # gets read by people on the machine that cannot run it.
  while IFS= read -r n; do
    [ -n "$n" ] && prs+=("$n")
  done < <(
    gh pr list --state open --json number,author \
      --jq '.[] | select(.author.login == "app/github-actions") | .number' 2>/dev/null
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
  head_sha=$(gh pr view "$pr" --json headRefOid --jq '.headRefOid' 2>/dev/null) || continue
  [ -n "$head_sha" ] || continue

  # Runs are matched on the head SHA, not the branch: a branch-name match would
  # also pick up runs from an earlier push that are no longer what the PR is
  # blocked on.
  run_ids=$(
    gh api "repos/{owner}/{repo}/actions/runs?head_sha=${head_sha}&per_page=100" \
      --jq '.workflow_runs[] | select(.status == "action_required" or .conclusion == "action_required") | .id' \
      2>/dev/null
  )

  if [ -z "$run_ids" ]; then
    echo "PR #${pr}: no runs waiting for approval."
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
