# ADR-015: Agnostic local↔cloud environment & deploy model (single-trunk; deploy/IaC opt-in)

- Status: Accepted
- Date: 2026-06-19
- Implements: epic #316
- Supersedes: ADR-014 (branch-per-env promotion chains)
- Relates to: ADR-005 (PR & board lifecycle — single-trunk base), ADR-007 (enforcement layers), ADR-013 (distribution & governance — profile tiers)

## Context

ADR-014 introduced opt-in **branch-per-environment promotion chains** for
scaffolded projects. Research across five tracks (human best practice, AI-agent
best practice, the PaaS landscape, self-managed/GitOps, and local↔cloud parity;
summarized in `PLAN.md` / `PLAN-REVIEW-LOG.md`, hardened over three Codex rounds)
found branch-per-env to be a deprecated pattern for **both** humans and AI agents:
environments differ by **config and deploy target**, not by **branch**. Conflating
them causes merge/config drift and — for an AI agent — forces it to reconstruct an
implicit branch→env model every session and hands it the deploy capability *as* a
destructive git capability.

The scaffolder is also language- and deploy-target-agnostic and must stay
deterministic (pure file-ops, no network/LLM calls; ADR-001). It is consumed by a
genuinely mixed, unknown population (libraries, deployed services, prototypes), so
no single env model can be a fixed default — the model must be chosen by interview.

## Decision

### 1. Single trunk is the only default

Every scaffolded project targets `main`. There are no environment branches. The
generic `base_branch` abstraction (`main`) is retained and consumed by `ci.yml`,
`validate-pr.yml`, and `start_issue.sh`.

### 2. A delivery-type question drives a coherent bundle

The wizard asks **"How is this delivered?"** → `library` / `service-or-app` /
`prototype-or-none`. Delivery is a template **layer/variable**, not a replacement
preset (it composes with preset × language).

- **library** → release/versioning bundle (publish workflow shipped **disabled/TODO**
  until registry + metadata + trusted-publishing are validated).
- **service-or-app** → the **parity bundle** (§3). `service-or-app` + `--language none`
  is **rejected** (no safe generic Dockerfile/test for an unknown runtime).
- **prototype-or-none** → single trunk, nothing env-related.

### 3. The local↔cloud unifier is the container image + a one-command interface

Not Terraform (a cloud-only provisioning layer). The parity bundle is: a multi-stage
`Dockerfile`, a Compose-Spec `compose.yaml` (explicit backing-service selection;
optional `compose watch`), `devcontainer.json`, a deterministic non-interactive
`justfile` (`up`/`test`/`lint`/`build`), `.env.example`, and a CI that reuses the
same image with a **pinned** test-execution location. "Same image everywhere" holds;
"same behavior everywhere" does not (IAM, managed services, networking break — test
those against a real cloud dev project).

### 4. Deploy and IaC are opt-in per-target overlays (default OFF)

Managed PaaS usually owns the deploy last-mile better than scaffolded YAML, so the
default stops at the cloud boundary. When opted in:

- **Deploy** builds once and promotes the **same immutable artifact by digest, not
  tag**, through **GitHub Environments**. Three target classes: container-deploy,
  registry-publish-only (publication, not deploy), and source/PaaS (routed to a
  "platform owns deploy" path). `environments.yaml` declares the model in **fixed
  shapes** (the renderer is pure `.tmpl` substitution with no loops).
- **Prod gate tiered by profile:** `org` = a true human gate (required reviewers +
  prevent-self-review + disallow-admin-bypass); `individual`/`standalone` = honestly
  labeled **"delayed + advisory, not human-gated"** (no second approver exists solo).
  The server-side GitHub Environment rule is the only boundary an agent cannot edit;
  in-repo hooks are advisory defense-in-depth.
- **IaC** emits plain **HCL defaulting to OpenTofu** (license-safe vs BUSL/IBM
  Terraform), structural layer only, with **apply manual/environment-gated by
  default** (no apply-on-merge).

### 5. Cloud governance is a separate product

GCP (or any cloud) governance, monitoring, IAM, and landing-zone are **out of this
repo**. The scaffolder emits only an integration **seam** (OIDC trust + env
contract) that a separate platform/landing-zone product plugs into. Keeping a thin
agnostic "paved road" separate from a heavyweight landing zone is the documented
platform-engineering standard (CNCF, IDP reference model, Team Topologies, Backstage).

### 6. Determinism preserved

The Python scaffolder still only writes files and config. All git/network side
effects (branch protection, GitHub Environments, IaC apply) run **post-clone** via
operator-run scripts (`setup_github.sh --protect`, the deploy/IaC overlay setup),
never from the scaffolder core.

## Consequences

- Branch-per-env is removed (not demoted); ADR-014 is a superseded tombstone.
- The reusable governance bits (squash-only merge policy, base-branch protection,
  org rulesets) are centralized in `setup_github.sh --protect`.
- Child tickets implement the pieces under epic #316 (wizard delivery question,
  parity bundle, CI, guardrails, library path, deploy overlay, IaC overlay,
  integration seam, config schema + upgrade backfill, consistency sweep).

## Out of scope

- Cloud governance/monitoring/landing-zone (separate product; seam only).
- Adopting env branches or containers in **this** repo (project-init stays a
  single-trunk Python scaffolder).
- Kubernetes/GitOps as a default; single-vendor abstraction tools (Score/Encore)
  as defaults.

## Open questions

- Whether to later offer a first-class PaaS-native deploy sub-type per platform
  (Vercel/Render/Fly) beyond the generic "platform owns deploy" pointer.
- Whether `environments.yaml` ever needs dynamic N-environment generation (would
  require a deterministic, pure-file-ops code-gen render step).
