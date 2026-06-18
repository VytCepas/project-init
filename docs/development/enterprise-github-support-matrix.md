# Enterprise GitHub Compatibility — Support Matrix

- Status: **Spike (#254)** — input to ADR-013 (#246). 🔬 _Research synthesis in progress._
- Date: 2026-06-18
- Blocks: ADR-013 (#246). Feeds: #248 (marketplace source schema), #251 (enforcement), #255 (host implementation).

## Why this spike

The governance epic (#253) assumes an **org forks the scaffolder** and distributes it
through a Claude Code plugin marketplace, with **server-side hard enforcement**
(ADR-007). Both assumptions were written against public `github.com`. Locked-down orgs
run on other hosts (Enterprise Cloud with EMU, GHE.com data residency, GHES), where
forks, plugin-marketplace resolution, and enforcement primitives may behave
differently. This spike resolves those unknowns before ADR-013 locks the model.

Questions (from #254):

1. Does Claude Code's plugin marketplace resolve enterprise/GHES hosts at all?
2. Does **EMU** permit internal forks of an imported repo, or only mirror/import?
3. Which **enforcement primitives** exist per tier (feeds #251), and is the bootstrap admin-gated?
4. **Is the forked-marketplace model the right _primary_ org path**, or should "org preset
   + copied hooks + upgrade recommendations" (the `--no-plugin` / copied-in path) be primary
   under no-egress/EMU? _(This finding may reshape #248 and the ADR.)_

## Host topology

| Host | What it is |
|---|---|
| **github.com** (Free/Pro/Team/Enterprise Cloud) | Public SaaS; the current assumed target. |
| **Enterprise Cloud + EMU** | Enterprise Managed Users — provisioned identities, restricted external interaction. |
| **GHE.com** | Enterprise Cloud with data residency; tenant on a `*.ghe.com` subdomain. |
| **GHES** | GitHub Enterprise Server — self-hosted, often network-restricted/air-gapped. |

## Support matrix

> 🔬 Cells pending research synthesis from the spike (in progress).

| Capability | github.com | EMU (Enterprise Cloud) | GHE.com | GHES |
|---|---|---|---|---|
| Claude Code plugin marketplace resolves on host | 🔬 | 🔬 | 🔬 | 🔬 |
| Personal/internal **fork** supported | 🔬 | 🔬 | 🔬 | 🔬 |
| **Import/mirror** alternative to fork | 🔬 | 🔬 | 🔬 | 🔬 |
| Classic **branch protection** | 🔬 | 🔬 | 🔬 | 🔬 |
| **Branch/tag rulesets** | 🔬 | 🔬 | 🔬 | 🔬 |
| **Push rulesets** | 🔬 | 🔬 | 🔬 | 🔬 |
| **Required workflows** | 🔬 | 🔬 | 🔬 | 🔬 |
| **Org rulesets** applied directly to target repo | 🔬 | 🔬 | 🔬 | 🔬 |
| Disable admin bypass / **merge queue** | 🔬 | 🔬 | 🔬 | 🔬 |
| **REST API base** | 🔬 | 🔬 | 🔬 | 🔬 |
| **Recommended primary distribution mode** | 🔬 | 🔬 | 🔬 | 🔬 |

## Findings

### Q1 — Plugin marketplace on enterprise hosts
🔬 _Pending._

### Q2 — EMU: fork vs import/mirror
🔬 _Pending._

### Q3 — Enforcement primitives per tier + admin gating
🔬 _Pending._

### Q4 — Fork-via-marketplace vs copied-in as the primary org mode
🔬 _Pending._

## Recommendation (decision input for ADR-013)

🔬 _Pending synthesis._

## Fallback modes per host

🔬 _Pending._

## Impact on downstream tickets

- **#248** (re-pointable marketplace/fork + pin): 🔬 _Pending — confirm or revise the host-aware source schema._
- **#251** (hybrid enforcement): 🔬 _Pending — confirm the per-primitive taxonomy and org-applied rulesets._
- **#255** (enterprise host implementation): 🔬 _Pending — confirm API-base resolution strategy._

## Open questions / verify in implementation

🔬 _Pending._
