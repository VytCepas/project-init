# NIST AI RMF Crosswalk

> **Status:** template — adopt and customise, then commit.
> Maps this project's governance artifacts to the four functions of the
> **NIST AI Risk Management Framework (AI RMF 1.0)** — *Govern, Map, Measure,
> Manage* — plus pointers to ISO/IEC 42001 and the EU AI Act. This is an
> **adopted reference**, dated and versioned; it is documentation, not gate
> logic.

**Owner:** `<team or person responsible>` · **Last reviewed:** `<YYYY-MM-DD>`
**Framework version:** NIST AI RMF 1.0

## Crosswalk

| NIST function | What it asks | This repo's artifact(s) |
|---|---|---|
| **Govern** | Policies, accountability, culture, and oversight for AI risk. | [`AI_USAGE_POLICY.md`](AI_USAGE_POLICY.md) (roles, accountability, review cadence); CODEOWNERS; the CI governance gate (#412). |
| **Map** | Establish context: purpose, role (provider/deployer), affected users, data, dependencies. | The **system card** + **AIBOM** (#412): role, use case, affected users, data classes, declared & detected model/MCP inventory. |
| **Measure** | Assess, analyse, and track AI risks with appropriate methods. | [`data-handling.md`](data-handling.md) (data-class risk); [`ai-code-provenance.md`](ai-code-provenance.md) (provenance/licence risk); evaluation/logging fields on the system card. |
| **Manage** | Act on risks: prioritise, respond, and monitor over time. | [`approved-tools.md`](approved-tools.md) (allow/deny + change process); `prod_guard.py` + gitleaks backstops; `last_reviewed` staleness enforced by the gate. |

## Other adopted frameworks

- **ISO/IEC 42001** (AI management system): this set of policies + review cadence
  is the lightweight, code-resident form of an AIMS. Map clauses as your
  organisation requires.
- **EU AI Act**: classification and obligations depend on **role**
  (provider vs deployer) and **use case**, not on documentation alone. The
  system card (#412) carries `role`, `classification`, and an Act/RMF mapping
  checklist as prose. Treat the mapping as dated reference — the Act's
  obligations evolve.
- **OWASP Top 10 for LLM & Agentic Applications**: informs
  [`data-handling.md`](data-handling.md) (prompt-injection / sensitive-data
  exposure) and the agent oversight rules in
  [`AI_USAGE_POLICY.md`](AI_USAGE_POLICY.md).

## Caveat

Standards drift. This crosswalk is accurate as of **Last reviewed** above;
re-check the named frameworks on each review and update the mapping and date.
