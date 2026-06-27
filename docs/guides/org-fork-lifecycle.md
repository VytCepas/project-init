# Org fork lifecycle runbook

> **Status: validated end-to-end (#257).** Every stage's mechanics now ship; the
> path is exercised by `tests/integration/test_org_lifecycle.py`. This owns the
> epic's "three-case model usable end-to-end" criterion (#253).

For *why* the model is shaped this way, see [ADR-013](../adr/adr-013-distribution-governance-model.md)
and the [Enterprise GitHub support matrix](../development/enterprise-github-support-matrix.md).
This runbook covers the **`org`** profile; `individual` and `standalone` users do
not need a fork.

## At a glance

```
1. Create the org copy   →  2. Customize  →  3. Publish a fork version  →  4. Onboard a teammate
        (fork | import)         (--profile org)     (tag → release.yml)         (install + enforce)
                         ⟲  Update flow: pull upstream, recommend (never forced)
```

## Stage 1 — Create the org copy (fork or import)

Host-adaptive (per spike #254):

- **github.com / GHES** → **fork** project-init into the org:
  `gh repo fork VytCepas/project-init --org <ORG>` (or fork on your GHES host).
- **EMU / GHE.com** → **import or mirror** (external forks are blocked): GitHub
  Enterprise Importer, or a mirror-clone + mirror-push.

Then point the lifecycle scripts at your host (#255): they infer the host from
the repo remote, or set `PROJECT_INIT_HOST` / `GH_HOST`, and
`PROJECT_INIT_API_BASE` for GHES (`https://HOST/api/v3`). Org forking of
private/internal repos defaults to *disallow* — enable it in org settings, or use
import on EMU.

## Stage 2 — Customize

- Scaffold with the org profile: `project-init <target> --profile org` — bundles
  host-adaptive delivery, pinning, and hard-enforcement defaults, and prints what
  it bundles + the egress posture (notify-of-options, #247).
- **Delivery** is host-adaptive (#248): github.com/GHES → fork + marketplace (a
  full git URL is emitted off github.com); EMU/GHE.com → copied-in (`--no-plugin`).
- **Company preset**: `project-init preset new acme-backend --extends obsidian-only`,
  then edit `templates/presets/acme-backend.toml` (layers/vars/deps inherit; a
  `min_project_init_version` marker guards compatibility) (#252).
- **Locked down?** add `--no-egress` to omit the external official marketplace
  from scaffolded settings (#258).

## Stage 3 — Publish a fork version (release plumbing)

The fork owns its releases:

1. Bump the version in `src/project_init/__init__.py` (`__version__`),
   `pyproject.toml`, and `CITATION.cff` (`version:`), on a branch → PR → merge.
   A contract test (`test_release_engineering.py`) enforces that all three agree.
2. Tag the release — `release.yml` triggers on a tag push:
   `git tag vX.Y.Z && git push origin vX.Y.Z`. If your org's rulesets or the
   workflow guard restrict tag pushes, create the tag via the API instead:
   `gh api repos/<ORG>/<FORK>/git/refs -f ref=refs/tags/vX.Y.Z -f sha=<main-sha>`.
   Either path triggers `release.yml` (git-cliff changelog from Conventional
   Commits + wheel; ADR-006/008).
3. **Channel** (ADR-008/ADR-011): git-based by default — downstream pins with
   `PROJECT_INIT_REF=vX.Y.Z`. A fork publishing to a private index configures its
   *own* PyPI trusted publishing (ADR-011); it owns its release identity/secrets.

The plugin/fork version is recorded in scaffolded configs (#248), so downstream
projects pin to the fork's version, not upstream's.

## Stage 4 — Onboard a teammate

- Install from the fork:
  `PROJECT_INIT_REPO=https://<HOST>/<ORG>/<FORK>.git ./install.sh`
  (or `uv tool install "git+https://<HOST>/<ORG>/<FORK>@vX.Y.Z"`), then
  `project-init <target> --profile org`.
- The recorded profile/host/enforcement in `.claude/config.yaml` (#259) drives
  delivery and enforcement on every `upgrade`.
- **Server-side enforcement** (#251): `.claude/scripts/setup_github.sh --protect`
  applies the `project-init-baseline` ruleset directly (empty `bypass_actors` —
  binds everyone, no admin bypass). `monitor_pr.sh` refuses admin-merge under the
  org profile; merge via auto-merge / the merge queue under the required checks.

## Update flow — pull-and-recommend (#250 / #249)

1. The fork pulls upstream project-init and cuts a new fork version (Stage 3).
2. Downstream projects run `project-init upgrade`: genuinely-new additions are
   surfaced as **version-span recommendations** (#250) — never auto-applied.
3. Adopt per group with `--accept-new <id>`, skip with `--decline-new <id>`;
   `--apply` is refused until each new group is decided (#249). Declined groups
   are recorded and suppressed unless they change materially.

## Validation (end-to-end)

`tests/integration/test_org_lifecycle.py` scaffolds with `--profile org` and
asserts the recorded profile/enforcement/host, the host-adaptive delivery, the
no-egress mode, and the enforcement scripts are all coherent — confirming the
three-case model is usable end-to-end (epic #253).
