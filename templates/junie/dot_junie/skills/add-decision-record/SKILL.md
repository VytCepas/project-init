---
name: add-decision-record
description: Records a decision as a new record in docs/decisions/ using the MADR template and the shared front matter. Use when a non-obvious design choice is made so future agents understand why.
when_to_use: Use when the user says "record this decision", "write an ADR", or when you make an architectural choice (library, pattern, boundary, trade-off) that a future session would otherwise re-litigate. Do not use for trivial or easily reversed choices.
user-invocable: true
effort: low
allowed-tools: Read Write Glob Bash(git *)
---

Record a decision (an ADR).

## When a record is warranted

- The choice is hard to reverse, or expensive to re-derive
- Multiple plausible options existed and one was deliberately picked
- A future agent or developer would ask "why is it like this?"

Not warranted: formatting choices, renames, anything fully explained by code.

## Steps

1. Find the next free number: read the `alias: D-<n>` line of every record in
   `docs/decisions/` and take the highest `n` + 1.
2. Copy `docs/decisions/template.md` to `docs/decisions/<NNNN>-<kebab-slug>.md`,
   where `NNNN` is that number padded to four digits, and set `alias: D-<n>`.
3. Fill every section. Keep it short — context (2-5 sentences), the options
   actually considered, the decision with its justification, and honest
   consequences (including the bad ones). Delete the template's comments.
4. Set `status` to `accepted` if the decision is already in effect, otherwise
   `proposed`, and `date` to today.
5. If the record replaces an older one, write both sides: the new record gets
   `supersedes: D-<old>`, the old one gets `status: superseded` and
   `superseded_by: D-<new>`. Do not delete the old one. A record in another
   repo is written `<system>/D-<n>`. If the new record changes only part of an
   older one, leave that one `accepted` and add `revised_by: D-<new>` to it.
6. Mention the new record in the commit/PR that implements the decision.
