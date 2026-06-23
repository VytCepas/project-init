# Data Handling for AI Tools

> **Status:** template — adopt and customise, then commit.
> Defines what data may and may not be sent to AI tools, by class. Pairs with
> the allow/deny list in [`approved-tools.md`](approved-tools.md).

**Owner:** `<team or person responsible>` · **Last reviewed:** `<YYYY-MM-DD>`

## Data classes

| Class | Examples | May it go to an AI tool? |
|---|---|---|
| **Public** | open-source code, published docs | Yes — any approved tool. |
| **Internal** | non-sensitive internal code, configs without secrets | Yes — approved hosted tools whose terms forbid training on inputs. |
| **Confidential** | proprietary algorithms, unreleased plans | Only local / no-egress tools, or hosted tools under a DPA. |
| **Restricted** | secrets, credentials, keys, customer PII, NDA-covered source, regulated data (health/financial) | **Never.** No AI tool, hosted or local-with-egress. |

When unsure of the class, treat data as the **more** restricted class until
classified.

## Hard rules

- **Never** paste or feed **Restricted** data into any AI tool, prompt, or MCP
  server.
- **Never** commit secrets — even into a prompt history or scratch file.
- Strip identifiers and minimise context before sending **Confidential** data to
  any tool that is permitted to receive it.

## Enforcement & backstops (already in this repo)

These are *backstops*, not permission to relax the rules above:

- **gitleaks** secret scan runs on commit/CI — blocks committing detected
  secrets, but it cannot see what you paste into a chat window.
- **`--no-egress` mode** scaffolds the project so AI tooling avoids network
  calls — use it for **Confidential** work where local-only is required.
- **`prod_guard.py`** blocks destructive commands across agent surfaces.

The decisive control is human judgement at the point of input. The tooling
catches mistakes; it does not make the decision for you.

## Incident response

If Restricted data is sent to an AI tool in error: rotate any exposed
credentials immediately, notify the policy owner, and record the incident.
Treat it as a data exposure regardless of the provider's retention claims.
