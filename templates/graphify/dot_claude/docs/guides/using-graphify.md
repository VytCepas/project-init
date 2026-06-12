# Using Graphify memory

This project uses the `obsidian-graphify` memory stack (ADR-009 in the
project-init repo): the Obsidian vault holds human decisions and session
notes; [Graphify](https://github.com/safishamsi/graphify) holds a queryable
knowledge graph of the codebase. Graph for "how does the code fit
together", vault for "why did we do it this way".

## One-time setup

```bash
.claude/scripts/setup_graphify.sh
```

This installs the `graphify` CLI (`uv tool install graphifyy`), registers
the project-scoped `/graphify` skill plus a PreToolUse hook that nudges
agents toward querying the graph instead of grepping, and adds a
post-commit hook that incrementally rebuilds the graph (SHA256-cached, only
changed files). No API keys are needed — IDE usage runs through your
existing agent session, and AST extraction costs zero LLM tokens.

## Daily flow

1. Build/refresh: the post-commit hook keeps the graph current; after large
   uncommitted changes run `/graphify .` (or `graphify update .`).
2. Query: agents read `graphify-out/graph.json` first (see
   `.claude/rules/graphify.md`); the HTML visualization at
   `graphify-out/graph.html` is for humans.
3. Vault export (optional): `graphify . --obsidian` writes graph notes into
   the vault so wikilinks can connect code structure to decisions.

## What is committed

`graphify-out/` is a derived artifact: the markdown report
(`GRAPH_REPORT.md`) is worth committing for reviewers; the JSON/HTML/cache
are gitignored. Never hand-edit graph output — fix the code or the vault
note instead.
