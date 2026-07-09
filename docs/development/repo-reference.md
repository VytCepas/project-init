# Repo reference — CI optimizations, extension points, non-goals

Reference material moved out of the always-loaded CLAUDE.md (PI-657, epic
#641). Consult on demand; the per-turn rules stay in CLAUDE.md.

## CI Optimizations

This repo uses three strategies to reduce CI time and token usage:

1. **Test Parallelization** — Scaffolded projects run `pytest -n auto` via pytest-xdist (their `just test` recipe), cutting test time ~30-50% on multi-core runners. This repo's own CI runs pytest serially to avoid cross-test interference; use `uv run --with pytest-xdist pytest -n auto` locally where safe.
2. **Split Heavyweight Tests** — `wheel-smoke` job only runs after `lint-and-test` succeeds, enabling fast feedback.
3. **Job Dependencies** — Integration/smoke tests are separate jobs that only run when main lint passes, avoiding wasted cycles on failures.

Scaffolded projects get a `ci.yml.tmpl` template with these patterns built in. See the comments in that file for how to customize conditional paths (skip docs-only changes, etc.)

## Extending the agent infrastructure

Use this table when adding new capabilities to this repo or its templates:

| You want to… | Add a… | Where |
|---|---|---|
| Automate a repeatable multi-step workflow | **Skill** (`SKILL.md` with frontmatter) | `.agents/skills/<name>/SKILL.md` — register in `INDEX.md` |
| Enforce a rule on every tool call or commit | **Hook** (bash/python script) | `.agents/hooks/` — wire in `settings.json`. Use the `add_hook` skill. |
| Expose a shortcut as `/command` | **Skill** (`SKILL.md` with frontmatter) | `.agents/skills/<name>/SKILL.md` — register in `INDEX.md`. Use the `add_command` skill. |
| Add a reusable sub-agent persona | **Agent spec** | `.agents/agents/<name>.md` |

After creating a skill, add an entry to `.agents/skills/INDEX.md` so it is discoverable without reading every file.

## What this repo does NOT include

- No LLM calls from the scaffolder itself
- No long-running service
- No database (beyond what preset projects may install)
- Graphify setup ships as a user-run script inside the graphify overlay
  (`templates/graphify/dot_agents/scripts/`) — it runs inside scaffolded
  projects, not as part of this repo's runtime.
