# AI Usage Policy (AUP)

> **Status:** template — adopt and customise for your organisation, then commit.
> This is *governance-as-code*: a versioned, reviewed policy that travels with
> the repo, not a PDF in a drive nobody reads. Keep it to one page.

**Owner:** `<team or person responsible>`
**Last reviewed:** `<YYYY-MM-DD>`
**Applies to:** everyone contributing to this repository, human or agent.

## Purpose

Define how AI tools (LLM APIs, coding agents, MCP servers) may be used in this
project so we get their leverage without creating security, legal, or quality
risk. This policy *adopts* established frameworks rather than inventing new ones:
**NIST AI RMF**, **ISO/IEC 42001**, the **EU AI Act**, and the **OWASP Top 10
for LLM & Agentic Applications**. See [`NIST_RMF_CROSSWALK.md`](NIST_RMF_CROSSWALK.md)
for how each control here maps back to those frameworks.

## Principles

1. **Human accountability.** A person — not a model — owns every change. AI
   output is a draft until a human reviews, understands, and approves it.
2. **Least exposure.** Send the minimum data needed to the minimum set of
   approved tools. See [`data-handling.md`](data-handling.md).
3. **Approved tools only.** Use only the models, endpoints, and MCP servers
   sanctioned in [`approved-tools.md`](approved-tools.md). New tools require a
   review before first use.
4. **Provenance is tracked.** AI-authored or AI-assisted code follows
   [`ai-code-provenance.md`](ai-code-provenance.md) for attribution, licensing,
   and review.
5. **Governance is enforced, not assumed.** Controls bind through CI gates and
   git hooks, not goodwill. A policy that can't fail a build is documentation.

## Rules

- **Do** use approved AI tools for drafting, refactoring, review, test
  generation, and research.
- **Do** review every AI-generated diff before committing — you are responsible
  for it as if you wrote it by hand.
- **Do not** paste secrets, credentials, customer data, or NDA-covered source
  into any AI tool. The repo's secret scan (gitleaks) and `--no-egress` mode are
  backstops, not permission to be careless.
- **Do not** ship AI-generated code of unclear licence provenance into a
  permissively- or proprietary-licensed codebase without the checks in
  [`ai-code-provenance.md`](ai-code-provenance.md).
- **Do not** grant an agent autonomous, unreviewed access to production systems,
  payments, or destructive commands. The repo's command guard
  (`prod_guard.py`) is a safety net, not a substitute for oversight.

## Roles & responsibilities

| Role | Responsibility |
|---|---|
| Contributors | Follow this policy; review AI output before committing. |
| Maintainers / CODEOWNERS | Enforce the policy in review; keep approved-tools current. |
| Policy owner (above) | Keep this policy and the crosswalk reviewed and dated. |

## Review

This policy is reviewed at least every **180 days** (or sooner on a material
change to the tools used or the data handled). Update **Last reviewed** above on
each review — staleness is itself a finding.

## Related controls in this repo

- [`approved-tools.md`](approved-tools.md) — allow/deny list of models, endpoints, data classes.
- [`data-handling.md`](data-handling.md) — what data may and may not be sent to AI tools.
- [`ai-code-provenance.md`](ai-code-provenance.md) — AI-authored code attribution & licensing.
- [`NIST_RMF_CROSSWALK.md`](NIST_RMF_CROSSWALK.md) — mapping to NIST AI RMF functions.
- [`../CAPABILITIES.md`](../CAPABILITIES.md) — *inventory* of what was installed (supporting evidence, not policy).
