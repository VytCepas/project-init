# Org fork lifecycle runbook

> **Status: skeleton (#256).** This is the adoption path the `org` profile is designed
> around. The mechanics in each stage are filled by #247 (profiles), #248 (fork/pin),
> #251 (enforcement), #255 (host implementation), and #257 (end-to-end + release
> plumbing). It exists early so those tickets validate against a real path instead of
> baking unvalidated assumptions.

For *why* the model is shaped this way, see **ADR-013** (distribution & governance) and
the [Enterprise GitHub support matrix](../development/enterprise-github-support-matrix.md).
This runbook covers the **`org`** profile only; `individual` and `standalone` users do
not need a fork.

## At a glance

```
1. Create the org copy   →  2. Customize  →  3. Publish a fork version  →  4. Onboard a teammate
        (fork | import)         (preset)          (tag + pin)                  (install + enforce)
                         ⟲  Update flow: pull upstream, recommend (never forced)
```

## Stage 1 — Create the org copy (fork or import)

The mechanism is **host-adaptive** (per the spike):

- **github.com / GHES** → **fork** project-init into the org.
- **EMU / GHE.com** → **import or mirror** (EMU blocks external forks; import/mirror is
  the supported path).

_To be filled (#255):_ host-aware commands, `gh` host selection, org forking-policy
prerequisites (forking of private/internal repos defaults to *disallow*).

## Stage 2 — Customize

- Select `--profile org` (recorded in `.claude/config.yaml`).
- Choose delivery: marketplace with a **full git URL** on github.com/GHES; **copied-in
  (`--no-plugin`)** on EMU/GHE.com.
- Apply a company preset; for locked-down orgs, enable no-egress via
  `managed-settings.json`.

_To be filled:_ profile bundle + notify-of-options (#247), company-preset authoring
(#252), no-egress mode (#258).

## Stage 3 — Publish a fork version

- Cut a release/tag on the fork so teammates install a pinned, reproducible version.
- Record the plugin-version pin in config.

_To be filled:_ version-record fields + re-pointable reference (#248), fork release
plumbing (#257).

## Stage 4 — Onboard a teammate

- Install from the fork (the re-pointed reference); the recorded `org` profile drives
  delivery and enforcement.
- Server-side enforcement binds via **org rulesets applied directly to the repo**
  (forks don't inherit branch/tag rulesets); admin-merge is refused.

_To be filled:_ onboarding command + observability record (#259), hybrid enforcement
(#251).

## Update flow — pull-and-recommend

The fork **pulls upstream** and surfaces **recommendations** to adopt new additions —
never forced. New additions require **consent** before they land; nothing is silent.

_To be filled:_ version-span detection + recommendations (#250), opt-in consent for new
additions (#249).

## Validation reference

Each stage above is intentionally a placeholder anchored to the ticket that fills it.
#247/#248/#251/#255 should check their design against this path; #257 turns it into a
validated end-to-end walkthrough and owns the epic's "usable end-to-end" criterion.
