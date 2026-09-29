---
title: ADR-000 Project setup
date: 2026-01-01
status: accepted
tags: [setup, scaffolding]
---

# ADR-000: Project setup with project-init

## Context

This project was scaffolded using [project-init](https://github.com/example/project-init).

## Decision

Preset: `obsidian-only`

## Consequences

- Memory files live in `.agents/memory/` (agent-curated facts)
- Vault notes live in `.agents/vault/` (human-authored, Obsidian-compatible)

