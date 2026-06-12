# ADR-009: Graphify becomes the recommended KG memory preset; LightRAG demoted to legacy

- Status: Accepted (amended 2026-06-12: LightRAG overlay removed — see Consequences)
- Date: 2026-06-12
- Implements: evaluation required by #130

## Context

The `obsidian-lightrag` preset ships hand-rolled ingestion/query scripts
(`ingest_sessions.py`, `query_memory.py`) against `lightrag-hku`. As a
solo-maintained integration it is the part of this repo most likely to rot:
it pins a fast-moving Python dependency, requires both Anthropic and OpenAI
API keys for entity extraction and embeddings, and every LightRAG API change
lands on us.

Meanwhile the community consolidated around
[Graphify](https://github.com/safishamsi/graphify) (~65k stars, weekly
releases — v0.8.38 shipped 2026-06-11) for knowledge-graph memory across
Claude Code, Codex, Gemini CLI, and other agents.

## Evaluation: Graphify vs LightRAG for scaffolded-project memory

| Dimension | LightRAG overlay (current) | Graphify |
|---|---|---|
| Maintenance | ours — custom scripts against `lightrag-hku` | upstream — weekly releases, 711+ commits on the active branch |
| Install | `lightrag-hku>=1.0` as a project core dependency | `uv tool install graphifyy` + `graphify install` — tool-level, no project dependency |
| API keys | Anthropic + OpenAI required (extraction + embeddings) | none for IDE use (AST mode is 0 LLM tokens; headless extraction optionally uses any provider incl. Ollama) |
| Claude Code integration | custom rules file + manual script invocation | self-registers as a project-scoped skill (`/graphify`) + PreToolUse hook nudging graph queries over grepping |
| Obsidian path | custom ingestion into the vault | native `--obsidian` vault export |
| Freshness | manual re-ingestion | `graphify hook install` rebuilds changed files post-commit (SHA256 cache) |
| Multi-agent | Claude-specific scripts | works across the agents #137 targets |

The community pattern we adopt (see
[claude-code-memory-setup](https://github.com/lucasrosati/claude-code-memory-setup))
layers Graphify's structural code graph alongside the Obsidian vault:
graph for "how does the code fit together", vault for human decisions and
session memory.

## Decision Outcome

Add an `obsidian-graphify` preset and recommend it for new projects;
mark `obsidian-lightrag` legacy (still functional, no new features).

Scaffolder boundaries (unchanged by this ADR):

- The scaffolder never runs Graphify — it renders docs, a setup script the
  *user* runs once (`.claude/scripts/setup_graphify.sh`), and agent rules.
  Deterministic file ops only.
- Graphify's own artifacts (`graphify-out/`) are gitignored except the
  markdown report; the graph is a derived cache, not source.

## Consequences

- New projects get maintained KG memory with zero API-key setup.
- ~~The LightRAG overlay stays for existing projects~~ **Amended
  2026-06-12 (PI-172):** the owner confirmed the project has no users, so
  the compatibility argument was void — the overlay, preset, and its CLI
  flags were removed the same day Graphify landed. `project-init upgrade`
  on a recorded `obsidian-lightrag` preset errors with migration guidance.
- `memory.stack` gains the value `obsidian-graphify`; `project-init
  upgrade` maps memory stacks to preset names 1:1, so upgrades keep working.
