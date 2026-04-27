# docs — project-init internal knowledge base

Architecture decisions, development guides, and references for contributors and AI agents.

## Contents

| Path | Purpose |
|---|---|
| [`adr/`](adr/) | Architecture Decision Records — why decisions were made |
| [`development/`](development/) | Standards, testing, template system |
| [`guides/`](guides/) | How-to guides for contributors |

## Agent instruction

Before starting any task, check the relevant ADR. The template system, preset anatomy, and MCP choices all have documented decisions here. Reading them first prevents relitigating settled decisions.

## Adding an ADR

1. Copy the format from an existing ADR
2. Increment the number: `adr-NNN-<topic>.md`
3. Update this README's table
4. Commit alongside the code change it documents
