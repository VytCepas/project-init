# Repo reference — CI optimizations, extension points, non-goals

Reference material moved out of the always-loaded CLAUDE.md (PI-657, epic
#641). Consult on demand; the per-turn rules stay in CLAUDE.md.

## CI Optimizations

This repo uses three strategies to reduce CI time and token usage:

1. **Test Parallelization** — Scaffolded projects run `pytest -n auto` via pytest-xdist (their `just test` recipe), cutting test time ~30-50% on multi-core runners. This repo's own CI runs pytest serially to avoid cross-test interference; use `uv run --with pytest-xdist pytest -n auto` locally where safe.
2. **Split Heavyweight Tests** — `wheel-smoke` job only runs after `lint-and-test` succeeds, enabling fast feedback.
3. **Job Dependencies** — Integration/smoke tests are separate jobs that only run when main lint passes, avoiding wasted cycles on failures.

Scaffolded projects get a `ci.yml.tmpl` template with these patterns built in. See the comments in that file for how to customize conditional paths (skip docs-only changes, etc.)

## Extending the agent infrastructure

Use this table when adding new capabilities to this repo or its templates:

| You want to… | Add a… | Where |
|---|---|---|
| Automate a repeatable multi-step workflow | **Skill** (`SKILL.md` with frontmatter) | `.agents/skills/<name>/SKILL.md` — register in `INDEX.md` |
| Enforce a rule on every tool call or commit | **Hook** (bash/python script) | `.agents/hooks/` — wire in `settings.json`. Use the `add_hook` skill. |
| Expose a shortcut as `/command` | **Skill** (`SKILL.md` with frontmatter) | `.agents/skills/<name>/SKILL.md` — register in `INDEX.md`. Use the `add_command` skill. |
| Add a reusable sub-agent persona | **Agent spec** | `.agents/agents/<name>.md` |

After creating a skill, add an entry to `.agents/skills/INDEX.md` so it is discoverable without reading every file.

## The weekly third-party bump, and the one secret it wants

`third-party-updates.yml` opens a PR proposing a version bump for the pinned
third-party tools (ADR-016 §5). It never auto-merges.

**Set a repository secret `BUMP_PR_TOKEN`** — a PAT or a GitHub App
installation token with `contents: write` and `pull-requests: write`. Without
it the workflow still opens the PR, but under the `github-actions[bot]`
identity, and this repository's Actions approval policy queues bot-actor runs
at `action_required` instead of running them. The PR's head SHA then carries
**zero check runs** — not red, not green, never reported — so branch
protection is unsatisfiable and the PR sits at `BLOCKED` until someone clicks
"Approve and run" in the Actions tab. Two PRs accumulated that way before
anyone noticed, because nothing about the state looks like failure (#939).

The fallback is deliberately not a hard failure: a missing secret must not
turn the weekly check into a red build. It emits a `::warning::`, and a
best-effort recovery step (`tools/approve_pending_bump_runs.sh`) approves what
it can. **It cannot approve everything** — the endpoint refuses runs it did not
queue, including the `pull_request_review` run that gates `review/decision`:

```
POST /actions/runs/{id}/approve
403  This run is not from a fork pull request or queued by the Actions bot
```

For that one the remedy is a plain PR comment, which re-triggers
`review-status.yml`; `monitor_pr.sh` now posts it automatically when the
review gate has passed and the status has not caught up.

The approval policy itself **is** readable and writable over REST, and the
one-liner below is the fix that removes the problem rather than working
around it:

```sh
gh api repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval
# {"approval_policy":"first_time_contributors"}

gh api --method PUT repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval \
  -f approval_policy=first_time_contributors_new_to_github
```

Allowed values are `first_time_contributors_new_to_github`,
`first_time_contributors` and `all_external_contributors`; there is no
"never require approval", so the first is the loosest. A bot actor counts as
a first-time contributor under the middle tier, which is what queued the runs.

An earlier revision of this page said the setting was **not** reachable over
REST, on the strength of `/actions/permissions/access` answering 422. That is
a *different* setting — workflow access from other repositories — and it is
genuinely 422 for a public repo. Recording the mistake rather than quietly
deleting it: the wrong endpoint returning a plausible error is exactly how a
one-command fix turns into a documented dead end.

## What this repo does NOT include

- No LLM calls from the scaffolder itself
- No long-running service
- No database (beyond what preset projects may install)
- Graphify setup ships as a user-run script inside the graphify overlay
  (`templates/graphify/dot_agents/scripts/`) — it runs inside scaffolded
  projects, not as part of this repo's runtime.
