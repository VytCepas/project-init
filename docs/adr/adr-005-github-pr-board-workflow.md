# ADR-005: GitHub PR and board lifecycle workflow

**Date:** 2026-04-27
**Status:** Accepted

## Context

Projects scaffolded by project-init previously had partial GitHub workflow guidance: issues were created via `start-task`, but there was no standard for branch naming, PR creation timing, board column transitions, or when/how to request code review. This caused inconsistency across projects — some created PRs at the end, some committed directly to main, and code review was ad-hoc.

The goals of this ADR are to:
1. Define a single canonical lifecycle every project follows.
2. Make the happy path fast (automated by `/start-task` and `/request-review`).
3. Keep code review optional to control token cost.

## Decision

### Lifecycle

```
Issue created → branch created → draft PR created → work → PR ready → CI passes → merged
```

Each step maps to a GitHub Projects board column:

| Board column | Trigger |
|---|---|
| Backlog | Issues not yet scheduled |
| To Do | Issue exists, work not started |
| In Progress | `/start-task` run — branch + draft PR created |
| In Review | `/request-review` run — PR marked ready-for-review |
| Done | PR merged with `Closes #<n>` in body |

### Ticket, branch, and PR naming

Use the Project Init key `PI-<issue-number>` in issue titles and PR titles. Branch names must include the issue type prefix and project key: `<issue_type>/PI-<issue-number>-<branch-short-description>`. Keep branch names short and descriptive after the key.

### PR rules

- Created as **draft** immediately when work starts (not when it's done).
- Title format: `[PI-<issue>][<type>] Short description` or `[nojira][<type>] Short description`
- Valid types: `feat` (feature), `fix` (bugfix), `chore` (maintenance/refactor), `docs` (doc-only), `test` (test-only)
- Body must include `Closes #<issue>` to auto-close the issue and trigger the board move on merge (skip for `[nojira]` PRs)
- One issue → one branch → one PR. Stacked PRs allowed only for dependency chains, never for convenience.
- **No direct commits to `main` or `master`** — all changes must go through a PR. Use the pre-push hook to enforce locally.

### PR Types

| Type | Use case | Example |
|---|---|---|
| `feat` | New feature or enhancement | `[PI-42][feat] Add OAuth login` |
| `fix` | Bug fix | `[PI-99][fix] Handle null pointer` |
| `chore` | Maintenance, refactor, deps, CI | `[PI-16][chore] Remove Linear remnants` |
| `docs` | Documentation-only change | `[PI-20][docs] Update API guide` |
| `test` | Test-only change | `[PI-55][test] Add auth unit tests` |

### No-issue PRs (nojira)

For small, trivial changes (typos, quick fixes) that don't warrant a full issue:
```
[nojira][fix] Typo in README
[nojira][chore] Bump dev dependency
```
These PRs **skip the Closes keyword check** since there's no linked issue.

### CI enforcement

PRs must pass all CI checks before merge. The base scaffold ships a CI workflow (`.github/workflows/ci.yml`) that runs tests and lint. Branch protection rules should be enabled on the default branch to enforce this.

### Code review

GitHub PR review is part of the normal merge lifecycle: `finish-pr.sh` and
`monitor-pr.sh --merge` wait for the aggregate `reviewDecision`, print review
feedback when changes are requested, and require the next `--review-cycle`
after fixes are pushed.

The local `reviewer` agent remains optional and is triggered via
`/request-review` when an extra pre-merge pass is worth the token cost. Use it
for security-sensitive changes, architectural changes, or any PR the author is
uncertain about.

### GitHub Projects board

A project board named after the repository should be created once per repo. Column automations:
- Issue opened → **To Do**
- PR opened → linked issue moves to **In Progress**
- PR merged → linked issue moves to **Done** (via `Closes #n`)

## Consequences

- All projects scaffolded after this ADR follow the same lifecycle.
- `start-task` skill updated to create branch + draft PR automatically.
- `/request-review` command added to base scaffold.
- `.github/pull_request_template.md` added to base scaffold.
- `project-init.md.tmpl` updated with lifecycle table and rules.
- Agents working on scaffolded projects have unambiguous instructions — no guessing when to create PRs or how to name branches.
