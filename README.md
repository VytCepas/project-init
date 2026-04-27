# project-init

[![CI](https://github.com/VytCepas/project-init/actions/workflows/ci.yml/badge.svg)](https://github.com/VytCepas/project-init/actions/workflows/ci.yml)

Scaffolder for agentic-development infrastructure. One command drops a `.claude/` folder into any project so Claude Code (and other agents) have memory, docs, hooks, and curated MCPs ready to go.

## What it gives you

Inside any target project:

```
<your-project>/
├── CLAUDE.md          # canonical agent instructions; points into .claude/
├── AGENTS.md          # thin redirect to CLAUDE.md for non-Claude agents
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
- **Model-agnostic** — `AGENTS.md` and `GEMINI.md` redirect non-Claude agents to the canonical `CLAUDE.md` instructions.
- **`bun` and `uv` only** — no `npm`/`npx`/`pip`/`venv` anywhere in scaffolded projects.

## Install (one-time)

```bash
curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh | bash
```

This installs [`uv`](https://docs.astral.sh/uv/) if missing, clones the repo to `~/.local/share/project-init` (override with `PROJECT_INIT_HOME=...`), and writes a user-level slash command at `~/.claude/commands/project-init.md`.

## Use

In any project:

```bash
# Inside a Claude Code session:
/project-init

# Or from a shell:
cd your-project
uvx --from ~/.local/share/project-init project-init
```

### Non-interactive (CI / scripts)

```bash
project-init ./my-app \
  --non-interactive \
  --preset obsidian-only \
  --name my-app \
  --description "an app" \
  --language python \
  --mcps context7 \
  --db postgres \
  --browser \
  --strict
```

The wizard asks:

- Project name / description
- Language (Python/Node/Go/none) — drives `lint_command`, `format_command`, `test_command`
- Memory stack — Obsidian-only or Obsidian + LightRAG
- Core MCPs (Context7)
- Database MCP — none / Postgres / SQLite
- Browser automation — Playwright (yes/no)

Your answers are recorded in `.claude/config.yaml`. Re-run any time — it reconciles, never overwrites memory or vault notes.

## Example command

Run this to scaffold an Obsidian-only project with Context7 MCP:

```bash
project-init /path/to/my-project --non-interactive \
  --preset obsidian-only --name example --description "example python project" \
  --language python --mcps context7
```

The test suite validates this command works correctly — see `TestREADMEExampleCommand` in `tests/test_readme_examples.py`.

## Update

```bash
git -C ~/.local/share/project-init pull
```

## Uninstall

```bash
rm -rf ~/.local/share/project-init ~/.claude/commands/project-init.md
```

## Troubleshooting

**`/usr/bin/env: 'bash\r': No such file or directory`**
A shell template arrived with CRLF line endings. The repo enforces LF via `.gitattributes`; if you cloned through Windows in a way that converted endings, run `dos2unix install.sh templates/**/*.sh` and re-clone with `git clone --config core.autocrlf=false`.

**`uv: command not found` after install**
The installer adds `~/.local/bin` to PATH for the current process only. Add it to your shell profile: `export PATH="$HOME/.local/bin:$PATH"` in `~/.bashrc` / `~/.zshrc`.

**`claude mcp add` fails with `command not found: bunx`**
The MCP catalog uses [bun](https://bun.sh) instead of npm/npx. Install it once:
```bash
curl -fsSL https://bun.sh/install | bash
```

**Hooks silently do nothing on commit**
The hooks need `python3` on `PATH` (replaces the previous `jq` dependency). They auto-detect `uv run ruff` for uv-managed Python projects and fall back to a system `ruff`.

**WSL: phantom permission/CRLF changes when working from Git Bash on Windows**
Edit and commit from inside WSL (`wsl` then `cd ~/projects/...`). Editing WSL files from Git Bash on Windows mangles executable bits and line endings.

**`Unknown preset 'foo'`**
Run `project-init --help` and pick from `obsidian-only` or `obsidian-lightrag`. Custom presets go in `templates/presets/<name>.toml`.

## Layout of this repo

```
project-init/
├── pyproject.toml            # uv-managed, rich-only runtime dep, ruff-only dev
├── install.sh                # bootstrap one-liner
├── src/project_init/         # wizard CLI + scaffold engine
├── templates/
│   ├── base/                 # always copied
│   ├── obsidian/             # Obsidian-only + Obsidian+LightRAG overlay
│   ├── lightrag/             # LightRAG overlay
│   └── presets/              # toml preset definitions
├── examples/                 # sample scaffolded outputs
└── tests/                    # focused pytest modules by behavior area
```

## Status

All milestones (PI-1 through PI-18) are shipped. v0.1.0 released. Track future work in [GitHub Issues](https://github.com/VytCepas/project-init/issues).

## License

MIT
