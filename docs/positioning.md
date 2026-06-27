# Positioning in the ecosystem

**project-init builds an agent a workshop, not a note.** It does not sit *inside* any
single competitor category — it sits **underneath** all of them. Each adjacent category
owns one slice of "get an agent productive in a repo"; project-init's bet is that the
slices are weak in isolation and the value is the opinionated, wired-together,
**enforced** whole.

## The four adjacent categories

| Category | Examples | What they own | Overlap with project-init | What we have that they don't |
|---|---|---|---|---|
| **Instruction-file generators** | `/init`, ClaudeForge, DevTk.AI, design.dev | A generated `CLAUDE.md`/`AGENTS.md`, one-shot | We also emit `AGENTS.md` + `CLAUDE.md` (and resolve the redirect split) | Enforcement of what the file *says* (git hooks, lifecycle DAG, CI gates); an `upgrade` path so it doesn't rot; actual infra, not just description |
| **Component catalogs / marketplaces** | davila7/claude-code-templates, awesome-claude-code, rohitg00 toolkit | À-la-carte install of skills/hooks/agents | Same primitives; we *also* ship a marketplace (`.claude-plugin/marketplace.json`, plugin-first) | An opinionated internally-consistent whole, not a parts bin; project infrastructure (CI, `.gitignore`, issue/PR templates, board automation); deterministic tested preset composition |
| **Spec-driven / workflow methods** | GitHub Spec Kit, BMAD, Claude Flow, Superpowers | Methodology / process discipline | We also encode a process (the GitHub lifecycle DAG) | Infrastructure-first, not methodology-first; narrow deterministic enforcement at the git/CI boundary. **Complementary** — runs on top of us |
| **Stack templates** | Vstorm FastAPI+Next, claudefast, claude-code-templates project mode | A working app skeleton for a specific stack | Both produce a ready-to-go project dir | Stack-agnostic, app-agnostic agent infra; never-clobber overlay so we layer *onto* their output |

## The slice nobody else owns (the moat)

1. **Project infrastructure files** — CI workflows, `.gitignore`, issue/PR templates, board
   automation, env/secrets pattern, CODEOWNERS/SECURITY/CONTRIBUTING.
2. **Enforced GitHub lifecycle** — DAG-guarded issue → branch → PR → review → merge, blocked
   at the git/CI boundary (the only enforcement that binds every agent surface; ADR-007).
3. **Deterministic, tested, upgradeable rendering** — preset composition validated by
   scaffolding into temp dirs, plus a real `upgrade` with 3-way merge so scaffolds don't drift.

Everything else (instruction files, component distribution, knowledge-graph memory via
Graphify) we adopt the community standard for rather than reinvent — itself a selling point.

## Compose, don't compete

project-init's never-clobber `.new` overlay means it layers **onto** the output of the tools
above rather than replacing them. Run it *over* a Spec-Kit / BMAD / FastAPI-template project
and it adds the infrastructure + enforcement slice without touching what they generated. The
stance is **interop, not integration**: we do not vendor other tools' methodologies, and we
do not frame ourselves as an alternative to them — they are complementary layers.
