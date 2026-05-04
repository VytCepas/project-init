# LightRAG Review — Optional Feature Assessment

**Date**: 2026-05-04 | **Status**: APPROVED (no blockers)

## Summary

LightRAG is **ready as an optional, opt-in feature** for larger projects. Obsidian-only remains the default for smaller projects.

**Design philosophy**: CLI-driven ingestion, not automatic. Users explicitly choose when to run `ingest_sessions.py`. This keeps costs visible and gives users agency.

## Sizing Guidance

| Scale | Preset | Reason |
|-------|--------|--------|
| Small (1–5 devs, <6 months) | Obsidian-only | Vault search sufficient, no API costs |
| Medium (5–15 devs, 6–18 months) | Obsidian-only (LightRAG optional) | Add LightRAG if agents struggle cross-file |
| Large (15+ devs, 18+ months) | Obsidian+LightRAG | Indexed graph helps agents; API costs justified |

## Current State: ✅ Functionally Complete

- Deterministic scripts (`ingest_sessions.py`, `query_memory.py`) — no unexpected LLM calls
- Clean preset/layer integration — no conflicts
- 15 tests passing — scaffolding, syntax, error handling, hash tracking
- Defensive error handling — fast-fail on missing API keys
- Hard-coded config values — intentional, reduces cognitive load for opt-in feature

**Not blockers** (by design):
- ✅ No auto-ingestion hooks — cost control + user agency
- ✅ Rules file is terse — acceptable for optional feature
- ✅ Config marked "reference only" — users don't need to edit it

## Recommendations

### HIGH (User Guidance)

1. **Expand `lightrag.md`** (13 → 40–50 lines)
   - When to use LightRAG vs. vault search
   - Cost expectations (~$0.20–0.50/day for 100k docs)
   - How to run ingest and query
   - Troubleshooting (missing API keys, stale index)

2. **Add quick-reference to `CLAUDE.md.tmpl`** (when LightRAG enabled)
   ```markdown
   ## LightRAG Memory (Optional)
   
   Ingest: `uv run .claude/scripts/ingest_sessions.py`
   Query: `uv run .claude/scripts/query_memory.py "your question"`
   ```

### MEDIUM (Clarity)

3. **Update wizard** — guide users on when LightRAG makes sense (project sizing)

4. **Document hard-coded values in `lightrag.yaml.tmpl`** — explain they're intentional defaults

### LOW (Testing)

5. **Optional integration test** — full workflow (scaffold → ingest → query); skipped by default, requires API keys

## Non-Issues (Working as Intended)

✅ Deterministic scripts | ✅ Layer composition clean | ✅ Test coverage appropriate for optional feature | ✅ Error handling defensive | ✅ Incremental ingestion works

## Verdict

**Ready for next release as optional preset.** Focus on improving user guidance (docs, sizing, quick-start cards) rather than automation. The opt-in philosophy is correct.
