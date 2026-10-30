# ADR-006: Conventional Commits format for commit messages and PR titles

- Status: Accepted
- Date: 2026-06-11
- Supersedes: title-format portions of ADR-003 and ADR-005 (branch naming and lifecycle are unchanged)

## Context

Commit messages and PR titles have used the format `[PI-N][type] Description`
(`[nojira][type]` for no-issue work). PR titles become squash-merge commit
messages, so the same format flows into `git log`.

The bracket format is *almost* [Conventional Commits](https://www.conventionalcommits.org/)
but not parseable by its tooling. That blocks automated changelog generation
(git-cliff, release-please) planned for the release-engineering work (#144),
and diverges from the convention most adopters already know.

## Decision

Switch the canonical format for commit messages and PR titles to Conventional
Commits with the issue key as scope:

| Case | Format | Example |
|---|---|---|
| Issue-linked | `<type>(<KEY>-<n>): <Description>` | `chore(PI-141): Migrate to conventional commit titles` |
| No issue (nojira) | `<type>: <Description>` | `fix: Correct typo in README` |
| Breaking change | `<type>(<KEY>-<n>)!: <Description>` | `feat(PI-9)!: Drop python 3.10` |

Types are unchanged: `feat` `fix` `chore` `docs` `test`.
Branch naming is unchanged: `<type>/<KEY>-<n>-<slug>`.
A title without a scope is the nojira case (replaces the `[nojira]` prefix).

### Transition rule

Validators (PR title workflow, commit-msg git hook) accept **both** the new
format and the legacy `[KEY-N][type]` format so in-flight branches and
existing history are not broken. All generators (lifecycle scripts,
`dag_workflow.py`, docs, templates) emit only the new format. The legacy
acceptance can be dropped in a future major release.

## Consequences

- `git log` becomes machine-parseable; git-cliff/release-please can generate
  changelogs (wired in #144).
- The issue key stays greppable (`PI-141`) and the existing board automation,
  which reads labels and body headings rather than titles, is unaffected.
- The `validate-pr` workflows, `commit-msg` hook, `dag_workflow.py` nojira PR
  creation, `start_issue.sh`, and all docs/skills must be updated in lockstep
  (done in the PR that lands this ADR).
- Existing merged history remains in the legacy format; changelog tooling
  starts from the adoption point.
