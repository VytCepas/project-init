# project-init

Scaffolder for agentic-development infrastructure. One command drops a `.claude/` folder into any project so Claude Code (and other agents) have memory, docs, hooks, and curated MCPs ready to go.

## What it gives you

Inside any target project:

```
<your-project>/
├── CLAUDE.md          # thin redirect into .claude/
├── AGENTS.md          # layout spec for non-Claude agents (Cursor, Aider, …)
└── .claude/
    ├── project-init.md      # workflow + conventions
    ├── config.yaml          # record of options chosen at init
    ├── settings.json        # Claude Code settings + hooks
    ├── commands/ skills/ agents/ hooks/ scripts/
    ├── memory/
    │   ├── MEMORY.md        # grep-able memory index
    │   └── .lightrag/       # optional KG index (if chosen)
    └── vault/               # Obsidian vault (humans)
        ├── decisions/ design/ sessions/ knowledge/
```

Principles:
- **One folder, `.claude/`**, for everything agentic. Project root stays clean.
- **Obsidian vault for humans, LightRAG (optional) for agents** — separated on disk.
- **Deterministic-first** — hooks and scripts are bash/python. LLM calls only where generative.
- **Model-agnostic** — `AGENTS.md` documents the layout for non-Claude agents.

## Install (one-time)

```bash
curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh | bash
```

This installs [`uv`](https://docs.astral.sh/uv/) if missing, clones the repo to `~/.local/share/project-init`, and writes a user-level slash command at `~/.claude/commands/project-init.md`.

## Use

In any project:

```bash
# Inside a Claude Code session:
/project-init

# Or from a shell:
cd your-project
uvx --from ~/.local/share/project-init project-init
```

The wizard asks:

- Project name / description
- Language (Python/Node/Go/none)
- Memory stack — Obsidian-only or Obsidian + LightRAG
- MCPs to install (Linear, GitHub, Context7, Playwright, Postgres/SQLite, …)
- Lint/test tooling (ruff, pytest)

Your answers are recorded in `.claude/config.yaml`. Re-run any time — it reconciles, never overwrites memory or vault notes.

## Update

```bash
git -C ~/.local/share/project-init pull
```

## Uninstall

```bash
rm -rf ~/.local/share/project-init ~/.claude/commands/project-init.md
```

## Layout of this repo

```
project-init/
├── pyproject.toml            # uv-managed, rich-only runtime dep, ruff-only dev
├── install.sh                # bootstrap one-liner
├── src/project_init/         # wizard CLI (PI-3 pending)
├── templates/
│   ├── base/                 # always copied
│   ├── obsidian/             # Obsidian-only + Obsidian+LightRAG overlay
│   ├── lightrag/             # LightRAG overlay
│   └── presets/              # yaml preset definitions
└── tests/
```

## Status

Templates (PI-2) and install script (PI-4) are in. Interactive wizard (PI-3) is a stub — track progress in Linear.

## License

MIT
