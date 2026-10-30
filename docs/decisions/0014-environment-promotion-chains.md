# ADR-014: Environment promotion-chain branch model (SUPERSEDED)

- Status: **Superseded** by epic #316 (agnostic local↔cloud env/deploy model)
- Date: 2026-06-19 (superseded 2026-06-19)
- Superseded-by: ADR-015 (env/deploy model) — see `PLAN.md`

## Why this was superseded

ADR-014 introduced opt-in **branch-per-environment promotion chains**
(`dev → test → main`, etc.) for scaffolded projects. Subsequent research (5
tracks, summarized in `PLAN.md` / `PLAN-REVIEW-LOG.md`) found branch-per-env to
be a deprecated pattern for both humans and AI agents: environments differ by
*config and deploy target*, not by *branch*. The modern model is **single-trunk +
build-once + promote the immutable artifact through deployment environments**,
with deploy/IaC as opt-in overlays.

Epic #316 therefore **removes** the promotion-chain feature entirely (the wizard
`--branch-model` option, the `promotion_chain` config block, `promote_env.sh`,
`setup_env_branches.sh`, and the multi-branch presets). The only pieces retained
are the **generic single-trunk `base_branch` abstraction** (feature PRs target the
default branch) and the **base-branch protection + merge-policy logic**, now folded
into `setup_github.sh --protect`.

This file is kept as a tombstone so historical references resolve. For the current
environment/deployment design, see **ADR-015** and `PLAN.md`.
