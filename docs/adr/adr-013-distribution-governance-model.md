# ADR-013: Distribution & governance model — three profiles, fork-based orgs, opt-in updates, hybrid enforcement

- Status: Accepted
- Date: 2026-06-18
- Implements: epic #253; informed by spike #254 ([enterprise support matrix](../development/enterprise-github-support-matrix.md))
- Relates to: ADR-010 (plugin marketplace — foresaw a company marketplace), ADR-007 (enforcement layers), ADR-008 (git-based distribution / `PROJECT_INIT_REF`)

## Context

`project-init` is consumed by audiences with different needs: a solo user who just
wants the tool and tracks upstream; a user who customizes their copy heavily and
updates it on their own schedule; and a team/company that wants a standardized,
centrally-updatable setup. The original design assumed a single audience on public
`github.com`, with the shared payload delivered plugin-first (ADR-010) and "hard"
enforcement implicitly trusted to git/Claude hooks.

Two investigations reshaped this:

1. A four-part codebase analysis (plugin/marketplace, presets/overlays, upgrade
   consent, enforcement layers).
2. Spike #254, which resolved how the model behaves on non-`github.com` hosts
   (Enterprise Cloud + EMU, GHE.com data residency, GHES).

This ADR records the resulting model so the child features (#247–#259) build on one
decision rather than re-litigating it.

## Decision

### 1. Three distribution profiles

The model is **three profiles**, keyed on the *relationship to upstream* (who drives
updates and how far you diverge), not on solo-vs-team:

| Profile | Delivery | Updates | Enforcement | Fork |
|---|---|---|---|---|
| **`individual`** (default) | plugin-first (marketplace) — **today's behavior** | track / float from canonical upstream | advisory | optional, re-pointable |
| **`standalone`** | copied-in (`--no-plugin`) | owner-driven, pinned; `upgrade` warns of merge conflicts | advisory | optional, re-pointable |
| **`org`** | host-adaptive (see §3) | fork is the source of truth; pull upstream as *recommendations* | hard (server-side; see §4) | **required** — the team's upstream |

`individual` is defined precisely as **today's plugin-first default** (external
official plugins enabled, float-to-latest, advisory enforcement), so adopting this
ADR is backward-compatible and existing scaffolds/tests are unaffected. `standalone`
is the "own my copy, update when I choose" posture. `org` is the standardized,
fork-distributed team setup.

### 2. Fork is re-pointable everywhere, required only for `org`

The upstream reference is re-pointable by design (#248): a fork can back any profile,
but only `org` *requires* one. This makes graduation `individual → standalone → org`
zero-rework — the config records the upstream and you flip the reference. We do **not**
force a fork on `individual`/`standalone`, to keep the default install frictionless;
the ownership those users want is over their copied-in `.claude/` payload, which they
already have.

### 3. Host-adaptive delivery for `org` (from spike #254)

There is no single marketplace assumption. The `org` primary delivery mode depends on
the host:

- **github.com & GHES** → **fork + plugin marketplace** (emit a **full git URL** for
  non-`github.com` hosts; the `owner/repo` shorthand is github.com-only).
- **EMU & GHE.com** → **copied-in (`--no-plugin`) primary**, with the fork as the
  upgrade source. Rationale: EMU blocks external forks (import/mirror instead), local
  marketplace resolution there is unverified, and cloud Code Review is unsupported on
  GHE.com. Copied-in sidesteps every one of these unknowns.

### 4. Updates are opt-in / consent-based

Nothing lands silently. New additions are gated by **addition-group consent** (#249);
forks **pull-and-recommend** (#250) rather than receiving forced changes. The
`standalone` profile's `upgrade` must **surface potential merge conflicts** on
customized copied-in files.

### 5. Enforcement is hybrid, with an honest server-side constraint

Per ADR-007, **true (hard) enforcement is server-side only** — CI required checks plus
GitHub branch protection / **org rulesets**. Claude/git hooks are soft (consistency +
UX), not a gate. So:

- `individual` / `standalone` → **advisory** enforcement.
- `org` → **hard** enforcement. Because **forks do not inherit branch/tag rulesets**
  (only push rulesets), the org profile applies **org-level rulesets directly to the
  target repo**, with an **empty bypass allowlist** so rules bind owners too. It
  therefore **refuses admin-merge** (`monitor_pr.sh --admin`) and relies on auto-merge
  / required merge queue under required status checks. CI gating uses the org ruleset
  "require workflows to pass" rule (the standalone Actions "Required workflows" feature
  is deprecated).
- **No-egress** orgs disable external marketplaces via Claude Code
  `managed-settings.json` (`strictKnownMarketplaces` / `hostPattern` /
  `blockedMarketplaces`) — not `--no-plugin` alone (#258).

### 6. Options are surfaced to the user (legibility / consent parity)

The three profiles and what each bundles are **printed at selection time**, documented
in README / `--help` / this ADR, and — critically — **non-interactive / agentic
installs print the defaulted profile and its plugin / external-marketplace (egress)
state, never running silently** (#247). Enforcement of consequential choices lives in
the shared CLI arg layer (covers `uvx` / PyPI / direct), with skill/`install.sh` docs
secondary.

### 7. One shared config schema

`.claude/config.yaml` records the governance state — local only, **no external
telemetry**: profile, source repo, host, delivery mode, plugin version, enforcement
mode, and declined-addition IDs. Ownership is split to avoid drift: **#259 owns the
choice/audit fields, #248 owns the version fields**, and this ADR is the single home
for the combined schema.

## Consequences

- Backward-compatible: `individual` = today's default; no migration for existing users.
- A clear graduation path (`individual → standalone → org`) with no rework.
- Enterprise hosts are first-class via host-adaptive delivery; copied-in is a
  co-primary mode, not a footnote.
- Child tickets implement the pieces: #247 (profiles + notify-of-options), #248
  (fork/pin + host-aware schema), #249 (consent), #250 (pull-and-recommend), #251
  (hybrid enforcement), #252 (company presets), #255 (host implementation), #256/#257
  (org fork lifecycle), #258 (no-egress), #259 (observability).

## Out of scope

- Full GHES (self-hosted / air-gapped) **certification** — only host-awareness,
  the support matrix, and documented fallbacks.
- Client-side `settings.json` locking (rejected — enforcement is server-side, ADR-007).
- A hosted/SaaS company registry — the model is fork / copied-in.
- **External** consent/audit telemetry — only the local config record is in scope.

## Open questions

- Local plugin-marketplace resolution on EMU / `*.ghe.com` is inferred, not documented
  — verify on a real tenant before promoting fork+marketplace to primary there (#255).
- "Require workflows to pass" and private merge queue availability on the **Team** tier
  (docs imply Enterprise Cloud only) — decides whether Team-tier orgs enforce CI via
  ruleset or fall back to required status checks (#251).
