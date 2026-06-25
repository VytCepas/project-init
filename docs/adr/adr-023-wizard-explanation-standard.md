# ADR-023: Self-explaining wizard — every selectable concern explains its value

- Status: Accepted
- Date: 2026-06-25
- Implements: epic #470 (decompose project-init into à-la-carte, self-explaining
  overlays), WS-D — #472
- Relates to: ADR-013 (distribution profiles), ADR-020 (memory decomposition),
  ADR-021 (lifecycle decomposition), ADR-022 (toolchain gate map) — each of which
  ships its own wizard explanation as Definition-of-Done

## Context

Epic #470's headline goal is not just *making* concerns optional — it is letting
a user **decide each one informed**, understanding what a piece brings and what
it costs, rather than blindly accepting or declining. As the overlays landed
(memory, lifecycle, toolchain), `_choose_*_interactive()` accreted a good shape
ad hoc; this ADR promotes that shape to a **documented, test-enforced standard**
so the next selectable concern can't ship as a bare yes/no prompt.

## Decision — the explanation standard

**Every selectable concern explains its value before asking.** Two equivalent
forms satisfy the standard:

1. **Panel form** (opt-in / opt-out concerns: memory, lifecycle, governance,
   observability, multi-model, devcontainer, mise, vscode, docs, renovate, the
   Playwright/browser add-on). A `rich.Panel` whose body states, in order:
   - **what it ships** — the concrete files/behavior;
   - a **`Helps:` line** — the value, in the user's terms ("why you'd want it");
   - the **honest cost / caveat** — build time, a setting to enable, a tradeoff;
   - the **safe default** — and the flag that overrides it.
2. **Annotated option list** (multi-choice pickers: preset, profile, delivery,
   deploy, iac, and the MCP catalog). Each option printed as
   `name — what it brings`, preceded by a one-line framing of the choice. The
   `name — description` rows carry the per-option value.

Lightweight toolchain toggles share the `_explain_and_confirm(title, body,
question, *, default)` helper so the wizard stays scannable while still
explaining each. Heavyweight concerns keep their bespoke panels.

Non-interactive equivalence: every concern's flag carries the same information in
its `--help` text, and the README documents it — so `--non-interactive` users are
not second-class.

## Enforcement — a non-vacuous coverage test

`tests/contracts/test_wizard_explanations.py`:

- **Enumeration from the real registry.** `WIZARD_CONCERN_FLAGS` (concern →
  CLI-flag `dest`) and `WIZARD_MECHANICAL_FLAGS` (identity / distribution /
  catalog-selection flags that self-describe) together must partition **every**
  flag in `_build_parser()`. A newly added flag fails the test until it is
  classified — so the coverage can't silently go stale or vacuous.
- **Every concern actually explains.** Each concern's chooser is rendered (prompts
  mocked) and asserted to print a non-trivial explanation containing a value cue
  (`Helps:` or an annotated ` — ` option list). A concern registered with an
  empty explanation fails.

## Consequences

- Adding a new optional concern now has three mechanical steps enforced by the
  test: a chooser that explains (panel or annotated list), a `WIZARD_CONCERN_FLAGS`
  entry, and `--help`/README copy. Forgetting any one fails CI.
- The standard is a convention + helper + test, **not** a data-driven framework
  (deliberately, per #472's out-of-scope) — the bespoke panels stay readable and
  copy-editable.
- `core` + all overlays declined now yields a minimal scaffold the user chose
  knowingly: `project-init --preset core --memory none --lifecycle none
  --no-docs --no-renovate`.

## Out of scope

- Rewriting the option-list pickers (profile/delivery/deploy/iac) into panels —
  their annotated lists already carry per-option value.
- A localization / templating layer for the copy.
