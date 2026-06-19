# Environments & deployment — how this project is set up

This project uses the **single-trunk + deploy-environments** model. Environments
are a **deploy-time concern** (config + deploy target), **not** a branching concern.
There are no `dev`/`test`/`prod` branches — feature PRs target `main` and squash-merge.

## The one rule that matters for AI agents

**An agent works on feature/PR branches and never pushes to the production ref.**
On any auto-deploy platform, write access to the production branch *is* production
deploy access. The real production gate lives **server-side** (GitHub Environment
protection rules or branch protection), which an agent cannot edit — in-repo hooks
are only fast-feedback defense-in-depth.

## Decision guide — which path is this project?

| You are building… | Model | What ships |
|---|---|---|
| A **library / package** (PyPI, npm, crate) | Release/versioning | A tag-triggered publish workflow (disabled until you wire the registry + metadata) |
| A **deployed service / app** | Single-trunk + build-once-promote | The container parity bundle + opt-in deploy/IaC overlays |
| A **prototype / not sure yet** | Single trunk | Nothing env-related until you grow into one of the above |

## Local ↔ cloud

The unifier is the **container image + the `justfile`**, not Terraform:

- **Local:** `just up` (Compose), `just test`, `just lint`, `just build`. One `.env`
  for *your* dev config.
- **Cloud:** the *same image* is deployed; per-environment config/secrets live in
  **GitHub Environment secrets/variables**, injected at deploy — **never** in a
  local `.env` and never baked into the image.
- "Same image everywhere" is true; "same behavior everywhere" is not — IAM, managed
  services (DBs/queues), and networking differ. Test those against a real cloud dev
  project, not a local emulator.

## Deploying (only if the deploy overlay is enabled)

- Build the artifact **once**; promote the **same digest** dev → staging → prod.
- Production is gated by a **GitHub Environment** rule. In an `org` setup that's a
  required reviewer (who cannot be you); solo, it's a delayed/advisory gate — add a
  second approver or move to the org tier for a true human gate.
- Rollback = redeploy the previous digest. No git surgery.
- If a managed platform (Vercel/Netlify/Render/…) owns your deploy, let it — this
  project points at its native flow rather than fighting it.

See [ADR-015](../../../docs/adr/adr-015-env-deploy-model.md) in the project-init
source for the full rationale.
