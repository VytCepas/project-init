# AI Code Provenance

> **Status:** template — adopt and customise, then commit.
> Policy on code that AI tools authored or materially assisted: attribution,
> licence contamination, and the review bar it must clear.

**Owner:** `<team or person responsible>` · **Last reviewed:** `<YYYY-MM-DD>`

## Why this matters

AI-generated code can (a) reproduce material from incompatible licences, and
(b) be plausible-looking but subtly wrong. Both are *our* liability once merged.
This policy keeps AI assistance auditable and safe to ship.

## Attribution

- AI assistance is an ordinary part of the workflow and does **not** need
  per-line attribution.
- For a **substantial** AI-generated contribution (e.g. a whole module, a
  non-trivial algorithm), note it in the PR description — enough that a future
  reader knows to scrutinise provenance. Follow any org-specific commit-trailer
  convention if one exists.

## Licence contamination

- Do **not** accept AI output that appears to reproduce a recognisable body of
  third-party code (verbatim functions, distinctive comments, license headers).
  When output looks copied, find the upstream source and check its licence
  before using it.
- AI output incorporated here is treated as contributed under this repository's
  licence. If provenance is unclear and cannot be cleared, **do not merge it.**
- Be especially careful introducing code under copyleft (GPL/AGPL) terms into a
  permissively-licensed or proprietary codebase.

## Review bar

- Every AI-generated change gets the **same or higher** review scrutiny as
  human-written code — never lower because "the model wrote it."
- The author must **understand** the code they submit and be able to explain it.
  "The agent produced it" is not an acceptable answer in review.
- AI-generated tests must be checked for the usual failure modes: asserting on
  the wrong thing, tautological assertions, or tests that never actually run.

## Related

- [`AI_USAGE_POLICY.md`](AI_USAGE_POLICY.md) — the umbrella policy.
- [`approved-tools.md`](approved-tools.md) — which tools may produce code here.
- [`NIST_RMF_CROSSWALK.md`](NIST_RMF_CROSSWALK.md) — framework mapping.
