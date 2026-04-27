# .claude/docs — Internal Knowledge Base

This folder is the **system of record** for architectural decisions and development standards. It is version-controlled alongside code and is the primary source of context for AI agents.

## Structure

```
docs/
├── adr/           # Architecture Decision Records — why decisions were made
├── development/   # Standards, conventions, testing strategy
└── guides/        # How-to guides for common workflows
```

## How to use

**Agents:** Read `adr/` before starting tasks. If you establish a new pattern or make a non-obvious decision, write a brief ADR.

**Humans:** When an exploratory note in `.claude/vault/` solidifies into a real decision, move it here as an ADR and commit it.

## One-way flow

```
vault/knowledge/ (exploratory)  →  docs/adr/ (permanent)
```

Never duplicate content. If it's in `docs/adr/`, don't repeat it in `vault/decisions/`.
