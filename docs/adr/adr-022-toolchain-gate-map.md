# ADR-022: Toolchain decomposition — keep the existing `{{#if}}` conditionals, don't add overlays

- Status: Accepted (spike — file→gate map + recommendation; no production code)
- Date: 2026-06-25
- Implements: epic #470 (decompose project-init into à-la-carte overlays), WS-C spike — #471
- Relates to: ADR-002 (dot_ + .tmpl convention — the whole-file skip mechanism),
  ADR-015 (env/deploy model — `--delivery`/`--deploy`/`--iac` gating), ADR-020 (memory
  decomposition — the overlay pattern this spike *declines* to extend to the toolchain)

## Context

`base` ships ~13 toolchain files (linters, container, devcontainer, docs, IaC,
Renovate). The WS-C mandate was explicit: **evaluate extending the existing whole-file
`{{#if}}` conditional mechanism BEFORE proposing new overlay layers**, and justify new
overlays only if the conditionals are insufficient.

The whole-file skip mechanism (ADR-002): a `.tmpl` whose rendered output is empty or
whitespace-only is **not created**. Wrapping a file's entire body in `{{#if x}}…{{/if x}}`
makes the file conditional on `x`.

## Finding: the toolchain is already à-la-carte

Every language/container/docs toolchain file is **already** whole-file-gated:

| File | Current gate | Axis | Verdict |
|---|---|---|---|
| `ruff.toml.tmpl` | `{{#if python}}` | language (py) | ✅ keep |
| `eslint.config.mjs.tmpl` | `{{#if node}}` | language (node) | ✅ keep |
| `dot_golangci.yml.tmpl` | `{{#if go}}` | language (go) | ✅ keep |
| `typedoc.json.tmpl` | `{{#if node}}` | language (node) — API docs | ⚠️ keep, but also honor the docs axis |
| `mkdocs.yml.tmpl` | `{{#if python}}` | **mis-gated** — local docs config on raw language (no published site; PI-343) | ⚠️ refine → docs axis |
| `Dockerfile.tmpl` | `{{#if delivery_service}}` | delivery (ADR-015) | ✅ keep |
| `compose.yaml.tmpl` | `{{#if delivery_service}}` | delivery | ✅ keep |
| `dot_dockerignore.tmpl` | `{{#if delivery_service}}` | delivery | ✅ keep |
| `dot_devcontainer/*.tmpl` | `{{#if want_devcontainer}}` | flag/delivery | ✅ keep |
| `deploy/**`, `infra/**` | `--deploy` / `--iac` (ADR-015) | delivery | ✅ keep (separate) |
| `mise.toml.tmpl` | `{{#if mise}}` | flag (`--mise`) | ✅ keep |
| `justfile.tmpl` | always (conditional *sections*) | core command surface | ✅ keep always-on |
| `renovate.json` | **always** (static `.json`, never gated) | — | ⚠️ refine → opt-out |
| `.gitignore`, `.gitattributes`, `ruff`/lang configs core bits | always | core | ✅ keep |

**Conclusion: extend the existing conditional mechanism. Do NOT introduce new overlay
layers.** Overlays (the memory/governance pattern) earn their keep when a concern is a
*cohesive bundle of many files toggled together* (a vault, a governance kit). The
toolchain is the opposite: a set of **independent single files**, each already cleanly
gated on the axis that determines it (language detection, `--delivery`, `--mise`,
`--devcontainer`). Wrapping them in an overlay layer would **duplicate a working
mechanism** and add a registry/derivation indirection for zero benefit.

## Recommended refinements (the C-impl scope — small, additive)

These are gate *adjustments*, not new machinery:

1. **Introduce a docs axis** (`--docs` / `want_docs`), resolving the `mkdocs`↔`python`
   and `typedoc`↔`node` conflation (the per-file conflict #471 called out). Note these
   are **local doc-tooling configs only** — there is no published-site workflow
   (PI-343/ADR-004 retired the GitHub Pages `docs.yml`; `test_quality_toolchain.py`
   asserts its absence). `mkdocs.yml` exists for `mkdocs serve` preview; `typedoc.json`
   for a local `typedoc` build:
   - `mkdocs.yml` should gate on `want_docs`, not raw `python` — a python project that
     doesn't want MkDocs config shouldn't get one, and a node/go project should be able
     to opt in.
   - `typedoc.json` is node **toolchain** (stays `{{#if node}}`) but should additionally
     respect `want_docs` so it isn't forced on every node project.
   - **Backward-compat:** `want_docs` must default to preserve today's output (on for
     python/node) so existing scaffolds re-render byte-identically (PI-189); the new
     behavior is the *opt-out* and the cross-language opt-in.
   - **Cleanup:** `mkdocs.yml.tmpl:3` still claims it is "Published to GitHub Pages by
     `.github/workflows/docs.yml`" — a stale reference to the retired workflow (Codex
     review). C-impl should fix this comment to describe local preview only.
2. **Gate `renovate.json`** behind a flag (e.g. `--renovate`, default on to preserve
   today) or convert it to `.tmpl` wrapped in `{{#if renovate}}` — a project not using
   Renovate currently gets a stray always-on config.
3. **No change** to the language/delivery/mise/devcontainer gates — they are correct.

## Consequences

- WS-C needs **no new overlay layer, no `overlay_layers()` change, no registry**. It is
  a handful of `{{#if}}` gate edits + two new resolved vars (`want_docs`, `renovate`),
  threaded through the same 11-touchpoint wizard/CLI/variable pattern as any flag, and
  guarded by the PI-189 round-trip contract (defaults preserve current output).
- This is the smallest WS-C that satisfies the epic goal ("adopt only what you need"):
  the toolchain was *already* mostly decomposed; the spike's value is confirming the
  existing mechanism is right and pinning down the two real gaps (docs axis, Renovate).

## Out of scope

- Implementation (a follow-up **C-impl** issue: the docs axis + Renovate gate).
- Per-tool opt-outs *within* a language (e.g. python-without-ruff) — niche; ruff is the
  scaffolder's chosen python linter (ADR-001), not an à-la-carte slot.
- A non-GitHub docs publish target (the `docs.yml` workflow is GitHub Pages; a GitLab
  Pages analogue is the forge-overlay concern from ADR-021, not this spike).

## Implementation outcome (C-impl, #477)

Implemented as gate edits + two opt-out vars, no new overlay (as recommended):

- **`want_docs` axis** (`--no-docs`, default ON): `mkdocs.yml` now gates on
  `{{#if python}}{{#if want_docs}}` and `typedoc.json` on `{{#if node}}{{#if want_docs}}`
  — so a python/node project can decline its docs-preview config. Both stay
  byte-identical with the default on (PI-189).
- **`renovate` gate** (`--no-renovate`, default ON): `renovate.json` → `renovate.json.tmpl`
  wrapped in `{{#if renovate}}`.
- **Stale-comment fix**: `mkdocs.yml` and `typedoc.json` no longer claim a
  GitHub-Pages publish workflow (the `docs.yml` retired by PI-343/ADR-004); they
  now state they are local-preview only. This is the one intentional byte change
  (the committed byte-identity fixtures' `mkdocs.yml` hash was updated to match).
- **Deferred — cross-language mkdocs opt-in.** The spike floated letting a
  node/go project opt INTO mkdocs. That needs a separate per-tool selector (a
  single `want_docs` binary with a python default can't also serve node's
  typedoc-but-not-mkdocs without breaking byte-identity), so it is left out as a
  niche follow-up; `want_docs` here only *narrows* (declines), it never forces
  docs on a new language. The primary gap the spike identified — "you can't
  decline mkdocs" — is fixed.
