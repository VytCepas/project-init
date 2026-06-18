# Hybrid enforcement — enforced vs overridable

- Status: reference (#251); implements ADR-013, grounded in ADR-007.
- Date: 2026-06-18

project-init's guardrails are **hybrid** (ADR-007): only some bind server-side.
The `org` profile makes the *hard* layer bind by default; `individual` and
`standalone` keep everything advisory.

## Classification

| Guardrail | Class | Mechanism | Binds whom |
|---|---|---|---|
| Required CI checks (lint/test, secret scan) | **enforced (hard)** | ruleset / branch protection — required status checks | everyone (org: empty bypass) |
| Pull-request review required | **enforced (hard)** | ruleset `pull_request` rule | everyone |
| No force-push / no branch deletion | **enforced (hard)** | ruleset `non_fast_forward` + `deletion` | everyone |
| Conversation resolution | **enforced (hard)** | ruleset / branch protection | everyone |
| DAG workflow lifecycle gate | advisory | Claude/git hooks | the agent / committer (bypassable) |
| Commit-message format | advisory | commit-msg hook + CI title check | committer (the CI check is the real gate) |
| Lint-on-edit | advisory | PostToolUse hook | the agent only |

Only **server-side** controls (CI required checks + rulesets / branch protection)
are true gates (ADR-007). Agent/git hooks are fast-feedback UX, not a boundary.

## Org profile: make the hard layer bind

- **Rulesets, applied directly to the repo.** A ruleset with an empty
  `bypass_actors` binds owners/admins too — unlike classic branch protection
  (`enforce_admins: false`). Forks do **not** inherit branch/tag rulesets, so the
  org applies them directly (`setup_github.sh --protect` → the
  `project-init-baseline` ruleset).
- **No admin bypass.** `monitor_pr.sh` refuses `--admin` under the org profile —
  merge via auto-merge / the merge queue under the required checks instead.
- **Required workflows** use the org ruleset "require workflows" rule (Enterprise
  Cloud / GHES); Team-tier orgs fall back to required status checks.

## Availability by tier (per the support matrix)

| Primitive | Team | Enterprise Cloud | GHES |
|---|---|---|---|
| Branch protection / branch+tag rulesets / push rulesets | ✅ | ✅ | ✅ |
| Org rulesets targeting repos | ✅ | ✅ | ✅ |
| "Require workflows" ruleset rule | ⚠️ likely Enterprise-only | ✅ | ✅ |
| Merge queue (private/internal) | ⚠️ → Enterprise Cloud | ✅ | ✅ |

`setup_github.sh` feature-probes the rulesets API and degrades gracefully (warns,
falls back to branch protection) where a primitive is unavailable. See the
[enterprise support matrix](enterprise-github-support-matrix.md) for sources.
