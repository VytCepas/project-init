# ADR-014: Environment promotion-chain branch model (opt-in, reworkable default)

- Status: Accepted
- Date: 2026-06-19
- Implements: epic #298
- Relates to: ADR-005 (PR & board lifecycle — generalizes its single-trunk base-branch assumption), ADR-006 (conventional commit titles — the squashed commit reuses the PR title), ADR-007 (enforcement layers — the hard gate is server-side), ADR-013 (distribution & governance — profile-tiered enforcement)

## Context

Projects scaffolded by `project-init` assume a **single trunk**: every feature
branch targets `main`, and there are no environment branches. This is the right
default for solo and small projects (`project-init` itself included) — it keeps
history linear, revert/bisect trivial, and the lifecycle simple (ADR-005).

Some projects, however, want **environment branches** — a staged path like
`dev → test → main`, or `dev → uat → preprod → main` — so changes are promoted
through environments rather than landing straight on the production branch. We
want to support that without:

1. **Forcing it on anyone** — most projects neither need nor want three branches.
2. **Breaking squash / linear history** — naively squashing *promotions* would
   collapse many already-distinct feature commits into one blob and diverge the
   target branch; rebasing shared long-lived branches rewrites public history.
3. **Violating the scaffolder's invariants** — it is deterministic, pure
   file-ops, and makes no git/network calls (CLAUDE.md; ADR-001). It cannot
   create branches or apply rulesets during scaffold.

A prior decision established **squash-only** as the correct merge default. The
open question was whether environment branches conflict with it. They do not —
*if promotions are fast-forward*.

## Decision

### 1. The branch model is an ordered promotion chain in config

`.claude/config.yaml` carries a `branch_model:` block whose core is an ordered
`promotion_chain` list of branch names. The first element is the **base branch**
(where feature PRs target); the last is **production**. **Single-trunk is just a
length-1 chain (`[main]`)** — the same code path, no special-casing.

Examples: `[main]` (default), `[dev, main]`, `[dev, test, main]`,
`[dev, uat, preprod, main]`, or any custom ordered list.

### 2. Fast-forward promotion reconciles squash with environment branches

Two merge classes, two rules:

- **Feature → base branch**: **squash-merge** (today's behavior).
- **Promotion (base → … → production)**: advance the downstream branch by
  **fast-forward** (`git merge --ff-only`). Because the base only ever receives
  squash commits, fast-forwarding copies those exact commits downstream —
  **linear and squash-consistent across every branch, no merge bubbles.**

This is why squash *and* environment branches both hold. Squashing a promotion
(destroys granularity) and rebasing a shared branch (rewrites history) are
rejected. Merge-commit promotion — needed only for divergent hotfix flows — is
out of scope for v1 (see Open questions).

### 3. Opt-in, default off

The model is selected at init via the wizard (`--branch-model`), with the
**non-interactive default = single-trunk**. Projects that do not opt in render no
chain and see **zero behavior change**. The post-clone tooling ships inert until
a chain is configured.

### 4. Squash is enforced (net-new), tiered by profile

Today squash is enforced only at merge time (`gh pr merge --squash`). The chain
adds real enforcement: a repo-settings change (`allow_squash_merge` only +
`delete_branch_on_merge`) and a `required_linear_history` ruleset, plus
per-branch rules — `pull_request` + squash + linear on the base; promotion-only
(no direct commits) on downstream/production branches.

Per ADR-013, enforcement is **tiered by profile**: advisory branch protection for
`individual` / `standalone`, hard org rulesets (empty bypass allowlist) for `org`.
These apply **only when a chain is configured**.

### 5. Determinism preserved — branch/ruleset creation is post-clone

The Python scaffolder still only writes files and config. All git/network side
effects (creating the chain's branches, applying per-branch protection and
rulesets) live in a new post-clone script,
`templates/base/dot_claude/scripts/setup_env_branches.sh`, which **mirrors
`setup_github.sh`**: it reads the chain from `config.yaml` (same `sed` pattern as
`gh_profile`), is idempotent, and is run by the operator after clone. This keeps
branch creation out of the deterministic core — it is *not* a Python subcommand.

### 6. Reworkable default, addable later

The chain is an **opinionated but reworkable** default — documented as such in the
operator-facing workflow doc. A project that started single-trunk adopts the
model later by: `upgrade --apply --accept-new claude-core` (ships
`setup_env_branches.sh` via the #249 addition-consent system) + a backfilled
default `branch_model:` block (via the `_ensure_observability_fields` mechanism),
then editing the chain and running the script. The `branch_model:` block survives
`upgrade` (config.yaml is excluded from drift); re-scaffold robustness depends on
**#296** (re-scaffold clobbers config.yaml hand-edits).

### 7. A distinct promotion verb

Fast-forward promotion uses a **new lifecycle verb, `promote-env`** (shim
`promote_env.sh`), kept separate from the existing `promote` / `promote_review.sh`
(which means "mark a draft PR ready for review").

## Consequences

- **Backward-compatible**: single-trunk is the default and a length-1 chain;
  non-adopters — `project-init` included — are unaffected.
- Squash and linear history hold across environment branches via ff promotion.
- The shared lifecycle (`dag_workflow.py`, `start_issue.sh`) becomes
  **config-driven on the base branch**, falling back to the repo default branch
  when no chain is set.
- Generalizes ADR-005: the base branch is no longer assumed to be `main`. ADR-005
  is **superseded in part** (its single-trunk base assumption) by this ADR.
- Child tickets implement the pieces under epic #298 (wizard option, config-driven
  base + upgrade backfill, `promote-env`, `setup_env_branches.sh`, CI/pre-push
  retarget, operator docs).

## Out of scope

- **Merge-commit promotions** and divergent hotfix flows — v1 is fast-forward
  only.
- **Adopting environment branches in this repo** — scope is scaffolded output;
  `project-init` stays single-trunk.
- **Auto-creating branches during scaffold** — determinism forbids it; creation
  is post-clone only.

## Open questions

- **Hotfix-to-production under ff-only**: a fix committed straight to production
  diverges it from the base; the operator guide should document the back-merge
  step (or a hotfix branch that squashes into production, then ff downstream).
- Whether to later offer **merge-commit promotion** as a config option for teams
  that need divergent hotfixes without a back-merge dance.
