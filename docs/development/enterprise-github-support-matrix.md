# Enterprise GitHub Compatibility — Support Matrix

- Status: **Spike (#254) — complete.** Input to ADR-013 (#246); synthesis of 3 research strands + internal code grounding.
- Date: 2026-06-18 (facts current as of this date; external host behavior changes — re-verify before relying on a ⚠️/inference cell)
- Blocks: ADR-013 (#246). Feeds: #248 (marketplace source schema), #251 (enforcement), #255 (host implementation), #258 (no-egress mode).

## Why this spike

The governance epic (#253) assumes an **org forks the scaffolder** and distributes it
through a Claude Code plugin marketplace, with **server-side hard enforcement**
(ADR-007). Both assumptions were written against public `github.com`. Locked-down orgs
run on other hosts (Enterprise Cloud with EMU, GHE.com data residency, GHES), where
forks, plugin-marketplace resolution, and enforcement primitives behave differently.
This spike resolves those unknowns before ADR-013 locks the model.

Questions (from #254):

1. Does Claude Code's plugin marketplace resolve enterprise/GHES hosts at all?
2. Does **EMU** permit internal forks of an imported repo, or only mirror/import?
3. Which **enforcement primitives** exist per tier (feeds #251), and is the bootstrap admin-gated?
4. **Is the forked-marketplace model the right _primary_ org path**, or should "org preset
   + copied hooks + upgrade recommendations" (the `--no-plugin` / copied-in path) be primary
   under no-egress/EMU?

## Host topology

| Host | What it is |
|---|---|
| **github.com** (Free/Pro/Team/Enterprise Cloud) | Public SaaS; the current assumed target. REST base `api.github.com`. |
| **Enterprise Cloud + EMU** | Enterprise Managed Users — provisioned identities, restricted external interaction. Still on github.com (REST `api.github.com`) unless paired with data residency. |
| **GHE.com** | Enterprise Cloud with **data residency**; tenant on a `*.ghe.com` subdomain. REST base `api.SUBDOMAIN.ghe.com`. |
| **GHES** | GitHub Enterprise Server — self-hosted, often network-restricted/air-gapped. REST base `HOST/api/v3`. |

> These columns are **not fully orthogonal**: EMU is a property of an Enterprise Cloud
> tenant, and GHE.com is Enterprise Cloud *with* data residency. An EMU tenant with data
> residency inherits the GHE.com REST base. Treat the columns as the distinct
> *constraint sets* a scaffold must adapt to, not as four mutually exclusive products.

## Support matrix

Legend: ✅ supported · ⚠️ conditional / caveats · 🔻 restricted/blocked · _(Team+)_ = needs Team tier or above

| Capability | github.com | EMU (Enterprise Cloud) | GHE.com | GHES |
|---|---|---|---|---|
| Claude Code plugin marketplace resolves | ✅ `owner/repo` or full URL | ⚠️ full git URL only; cloud features need enterprise-authorized OAuth app | ⚠️ full git URL; local `git clone` only (inference, low) | ✅ official; **full git URL required** |
| Personal/internal **fork** | ✅ (org policy; default *disallow* for private/internal) | 🔻 external forks blocked; **within-enterprise only** | ⚠️ within-enterprise per Cloud forking policy | ✅ per org/enterprise forking policy |
| **Import/mirror** alternative | ✅ Importer / mirror-clone | ✅ **de-facto path** for external upstream | ✅ Importer / mirror | ✅ Importer / mirror |
| Classic **branch protection** | ✅ (private: Team+) | ✅ | ✅ | ✅ |
| **Branch / tag rulesets** | ✅ _(Team+)_ | ✅ | ✅ | ✅ |
| **Push rulesets** (private/internal) | ✅ _(Team+)_ | ✅ | ✅ | ✅ |
| **Required workflows** (org ruleset rule) | ⚠️ Enterprise Cloud only | ✅ | ✅ | ✅ |
| **Org rulesets** applied directly to target repo | ✅ _(Team+)_ | ✅ | ✅ | ✅ |
| Disable admin bypass / **merge queue** | ✅ bypass-off; private/internal merge queue needs Enterprise Cloud | ✅ | ✅ | ✅ |
| **REST API base** | `api.github.com` | `api.github.com` (or `api.SUB.ghe.com` w/ data residency) | `api.SUBDOMAIN.ghe.com` | `HOST/api/v3` |
| **No-egress lockdown** (`managed-settings.json`) | ✅ `strictKnownMarketplaces` / `blockedMarketplaces` / `hostPattern` | ✅ same | ✅ same | ✅ `hostPattern` allowlists the GHES host |
| **Recommended primary distribution mode** | Fork + marketplace | **Copied-in (`--no-plugin`)**; fork = upgrade source | **Copied-in (`--no-plugin`)** | Fork + marketplace (full git URL) |

## Findings

### Q1 — Plugin marketplace on enterprise hosts

- Claude Code resolves git-based marketplace sources by **shelling out to `git clone`** and
  **reusing local git credential helpers** (HTTPS via `gh auth login`/credential store, SSH via
  `ssh-agent`). Enterprise auth therefore works *through git* and is host-aware — but
  **`GH_HOST` is never consulted** by the resolver. _(high — [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces))_
- The **`owner/repo` shorthand always resolves to github.com**. Any non-github.com host needs a
  **full git URL** (`https://HOST/owner/repo.git` or `git@…`). `github` sources default to SSH;
  HTTPS via `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1`. _(high — [github-enterprise-server](https://code.claude.com/docs/en/github-enterprise-server))_
- **GHES is officially supported** for local `/plugin marketplace add` via full git URL. **GHE.com**
  local marketplace is plain `git clone` (works if clone works — _inference, low_); cloud **Code
  Review is not supported** on GHE.com (only GHES + github.com). **EMU** cloud features need a
  Claude OAuth app authorized at enterprise level _(medium)_; local marketplace via full URL is
  _inference, low_. _([code-review setup](https://support.claude.com/en/articles/14233555))_
- **No-egress controls** live in `managed-settings.json` (highest precedence, non-overridable):
  `strictKnownMarketplaces` (allowlist; `[]` blocks all additions), `blockedMarketplaces`,
  `hostPattern` source type (allowlist a whole GHES host), `allowManagedHooksOnly` + `enabledPlugins`
  to lock the supply chain — enforced **before download**. _(high — [settings](https://code.claude.com/docs/en/settings) · [manage plugins for your org](https://support.claude.com/en/articles/13837433))_

### Q2 — EMU: fork vs import/mirror

- Managed users **cannot fork repos from outside the enterprise**; they *can* fork private/internal
  repos **owned by enterprise orgs** into an enterprise namespace, *as policy allows*. Forks are thus
  **restricted to within the enterprise, not fully disabled**. _(high — [EMU abilities & restrictions](https://docs.github.com/en/enterprise-cloud@latest/admin/managing-iam/understanding-iam-for-enterprises/abilities-and-restrictions-of-managed-user-accounts))_
- To bring an **external upstream** in, GitHub points to **Enterprise Importer** and **mirror-clone +
  mirror-push**. Import/mirror is the de-facto pattern for an EMU org to hold a copy of `project-init`
  _(inference, medium — no doc explicitly labels it "recommended for EMU")_.
- Org forking policy can allow/forbid forking of private/internal repos (**default = disallow**); an
  **enterprise policy can cap orgs** so they cannot choose a more permissive setting. _(high — [forking policy](https://docs.github.com/en/organizations/managing-organization-settings/managing-the-forking-policy-for-your-organization))_

### Q3 — Enforcement primitives per tier + admin gating

**Availability by plan tier** (orgs need Team minimum; some rules are Enterprise Cloud-only). Free/Pro
are public-repo-only or unavailable for most rules and are not relevant to org governance.

| Primitive | Team | Enterprise Cloud | GHES |
|---|---|---|---|
| Classic branch protection | ✅ | ✅ | ✅ |
| Branch / tag rulesets | ✅ | ✅ | ✅ |
| Push rulesets (private/internal) | ✅ | ✅ | ✅ |
| Org-level rulesets (target by name/property) | ✅ | ✅ | ✅ |
| "Require workflows to pass" (ruleset rule) | ⚠️ likely Enterprise-only _(inference)_ | ✅ | ✅ |
| Merge queue (private/internal) | ⚠️ → Enterprise Cloud | ✅ | ✅ |

- **Fork inheritance (confirms #251's core assumption):** forks do **NOT** inherit branch/tag
  rulesets; they **DO** inherit **push rulesets** (which apply to the whole fork network, bypass
  inherited from the root). So an org-owned fork must be governed by **org-level rulesets targeting the
  repo directly** (All / selected / name pattern / repository-property), not by upstream inheritance.
  _(high — [about-rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) · [org rulesets](https://docs.github.com/en/organizations/managing-organization-settings/creating-rulesets-for-repositories-in-your-organization))_
- **Admin bypass — the "hard rules" lever:** classic branch protection lets admins bypass **by
  default** unless "Do not allow bypassing the above settings" is set; **rulesets** use an **explicit
  bypass allowlist** — admins/owners are *not* auto-bypass, and an **empty list binds everyone**.
  Configuration is admin-gated (repo rules = repo admin / "edit repository rules" role; org rules = org
  owners). With bypass off, enforced merging via **auto-merge / required merge queue** under required
  status checks is the correct pattern (merge queue is repo-level, not an org ruleset rule). _(high —
  [about-protected-branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches))_
- The standalone Actions **"Required workflows"** feature is **deprecated/replaced** by the org ruleset
  "require workflows to pass before merging" rule. _(high — [available-rules](https://docs.github.com/en/enterprise-cloud@latest/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets))_

### Q4 — Fork-via-marketplace vs copied-in as the primary org mode

The fork **model** holds, but the **delivery mechanism must be host-adaptive** rather than assuming a
github.com marketplace:

- **github.com & GHES → fork + live plugin marketplace is primary.** Requirement: emit a **full git
  URL** in `extraKnownMarketplaces.source` whenever host ≠ github.com (GHES is officially supported);
  github.com may keep `owner/repo`. For no-egress, layer `managed-settings.json`
  (`strictKnownMarketplaces` / `hostPattern` / `blockedMarketplaces`).
- **EMU & GHE.com (data residency / no-egress) → copied-in (`--no-plugin`) is primary.** The fork
  still exists but serves as the **upstream source for `project-init upgrade` recommendations**, not a
  live marketplace. Rationale: external forks are blocked under EMU (import/mirror instead); local
  marketplace resolution on EMU/`*.ghe.com` is unverified (low-confidence); cloud Code Review is
  unsupported on GHE.com. Copied-in sidesteps every one of these unknowns and is the safe default for
  locked-down tenants.

**Net:** this **confirms #248's direction** (host-aware source schema; force `--no-plugin` on
unsupported hosts) and **elevates copied-in from a fallback to a co-primary mode** for EMU/no-egress —
exactly the spike-decision the plan anticipated.

## Recommendation (decision input for ADR-013)

1. **Keep the fork model**, but record a **host-adaptive delivery mode** per profile
   (`individual` / `standalone` / `org` — see #247), not a single marketplace assumption.
2. **Primary distribution mode by host:** github.com/GHES → fork + marketplace (full git URL off
   github.com); EMU/GHE.com → copied-in (`--no-plugin`) with the fork as the upgrade source.
3. **No-egress is achievable via `managed-settings.json`** (`strictKnownMarketplaces` / `hostPattern`
   / `blockedMarketplaces` / `allowManagedHooksOnly`) — #258 should emit these rather than relying on
   `--no-plugin` alone.
4. **Never derive host/API base from the repo URL string** — resolve via `gh`/explicit config (#255).
5. **Enforcement = org-level rulesets applied directly to the fork** (not via inheritance), with an
   **empty bypass allowlist** so rules bind owners too; the org profile **refuses admin-merge**
   (`monitor_pr.sh --admin`) and relies on auto-merge / required merge queue under required status
   checks. "Required workflows" uses the org ruleset rule (Enterprise Cloud/GHES). Team-tier orgs get
   rulesets but may lack the required-workflows rule and private merge queue → degrade to required
   status checks (feature probe per #251).

## Fallback modes per host

| Host | If fork + marketplace is unavailable |
|---|---|
| github.com | n/a (primary path works) |
| EMU | copied-in (`--no-plugin`); import/mirror the upstream; managed-settings allowlist |
| GHE.com | copied-in (`--no-plugin`); full-URL marketplace only if `git clone` verified |
| GHES | copied-in (`--no-plugin`) if instance not connected; otherwise full-URL marketplace |

## Impact on downstream tickets

- **#248** (re-pointable marketplace/fork + pin): **confirmed + sharpened.** The current schema
  `"source": { "source": "github", "repo": "{{project_init_repo}}" }`
  (`templates/base/dot_claude/settings.json.tmpl`) is github.com-only, and
  `{{project_init_repo}} = __repo_url__.removeprefix("https://github.com/")`
  (`src/project_init/__main__.py:514`, `upgrade.py:324`) silently no-ops on non-github.com URLs. Fix:
  emit a **full git URL** (a `git`/`url`-type source) for non-github.com hosts, or force `--no-plugin`.
- **#255** (enterprise host implementation): **confirmed.** Resolve REST base via `gh api --hostname`
  / `GH_HOST` / explicit `PROJECT_INIT_API_BASE` — never string-derive from the repo URL. Replace
  hardcoded `api.github.com` (`install.sh:56`) and `https://github.com/...` manual links
  (`setup_github.sh`, `push_wiki.sh`).
- **#258** (no-egress mode): **de-risked.** Claude Code exposes managed-settings controls
  (`strictKnownMarketplaces` / `blockedMarketplaces` / `hostPattern`) to disable external marketplaces
  entirely — emit these for the org profile.
- **#251** (hybrid enforcement): **confirmed in full.** (1) the primitive split is real (branch
  protection / branch+tag rulesets / push rulesets / required-workflows-ruleset / merge queue have
  distinct availability); (2) **forks don't inherit branch/tag rulesets** (only push rulesets) → apply
  **org rulesets directly to the target repo**; (3) rulesets' empty bypass allowlist binds owners, so
  the org profile should **refuse `monitor_pr.sh --admin`** and use auto-merge/merge queue. The
  standalone Actions "Required workflows" is **deprecated** — use the org ruleset rule. Feature probes
  still needed for Team-vs-Enterprise gaps (required-workflows rule, private merge queue).

## Open questions / verify in implementation

- Local `/plugin marketplace add` against `*.ghe.com` and EMU hosts is **inferred, not documented** —
  verify on a real tenant before promoting fork+marketplace to primary there.
- Whether `hostPattern` is honored identically for `*.ghe.com` and GHES.
- Exact GHE.com **GraphQL** hostname (only the `*.SUBDOMAIN.ghe.com` wildcard is documented) — matters
  for the #255 Project owner-lookup fallback.
- "Require workflows to pass" and private **merge queue** availability on **Team** tier (docs imply
  Enterprise Cloud only) — decides whether Team-tier orgs enforce CI via ruleset or fall back to
  required status checks.

## Sources

Claude Code: [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces) ·
[github-enterprise-server](https://code.claude.com/docs/en/github-enterprise-server) ·
[settings](https://code.claude.com/docs/en/settings) ·
[code-review setup](https://support.claude.com/en/articles/14233555) ·
[manage plugins for your org](https://support.claude.com/en/articles/13837433).
GitHub: [EMU abilities & restrictions](https://docs.github.com/en/enterprise-cloud@latest/admin/managing-iam/understanding-iam-for-enterprises/abilities-and-restrictions-of-managed-user-accounts) ·
[REST getting started](https://docs.github.com/en/enterprise-cloud@latest/rest/using-the-rest-api/getting-started-with-the-rest-api) ·
[GHES REST quickstart](https://docs.github.com/en/enterprise-server@3.17/rest/quickstart) ·
[org forking policy](https://docs.github.com/en/organizations/managing-organization-settings/managing-the-forking-policy-for-your-organization) ·
[about rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) ·
[about protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) ·
[org rulesets](https://docs.github.com/en/organizations/managing-organization-settings/creating-rulesets-for-repositories-in-your-organization) ·
[merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue).
`gh` CLI: [environment](https://cli.github.com/manual/gh_help_environment) · [gh api](https://cli.github.com/manual/gh_api).
