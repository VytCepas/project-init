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
    ├── skills/ agents/ hooks/ scripts/ rules/
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
- **Claude-first, portable core** — built and tested for Claude Code; other agents get instructions, not enforcement. See [Agent support tiers](#agent-support-tiers).
- **`bun` and `uv` only** — no `npm`/`npx`/`pip`/`venv` anywhere in scaffolded projects.

## Agent support tiers

This is **firstly a Claude Code scaffolder**. It aims to be agent-agnostic where
that is cheap, but it is not natively so — be explicit about what each agent gets:

| Tier | What you get | Applies to |
|---|---|---|
| **Native (Claude Code)** | Everything: deterministic hooks (lifecycle guard, pre-commit gate), skills invoked as `/commands`, settings wiring | Claude Code only |
| **Instructions-only** | `AGENTS.md` / `GEMINI.md` redirect to the canonical `CLAUDE.md`; agents read conventions but **no hook fires and nothing is enforced** for them | Codex, Gemini CLI, Cursor, and other AGENTS.md-aware tools |
| **Portable regardless** | Lifecycle scripts (plain bash), memory and vault (plain markdown), git hooks (`commit-msg`, `pre-push`) — agent-independent by construction; git hooks bind once `install_hooks.sh` has run in the clone (server-side actions need branch protection) | Everything, including Ollama-based agents |

Two honest caveats:

- Hook enforcement and skill invocation **do not exist outside Claude Code**. An
  agent reading `AGENTS.md` is asked to follow the rules; nothing makes it.
  The git hooks and CI checks are the only enforcement that binds all agents.
- **Automated testing covers the Claude Code artifacts only.** The test suite
  validates settings schema, skills, hooks, and rendered files; no other agent
  is exercised in CI.

## Install (one-time)

```bash
curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh | bash
```

This installs [`uv`](https://docs.astral.sh/uv/) if missing, clones the repo to `~/.local/share/project-init` (override with `PROJECT_INIT_HOME=...`), and writes a user-level slash command at `~/.claude/commands/project-init.md`.

## Use

### Option 1: Inside a Claude Code session (interactive)

After installing, a `/project-init` slash command is available in any Claude Code session:

```
/project-init
```

This runs the interactive wizard in the current project directory. It asks for project name, language, memory stack, and MCPs — then scaffolds `.claude/` for you.

### Option 2: From a shell (non-interactive, for CI / scripts)

```bash
cd your-project
uvx --from ~/.local/share/project-init project-init . \
  --non-interactive \
  --preset obsidian-only \
  --name my-app \
  --description "an app" \
  --language python \
  --mcps context7
```

The wizard asks (interactive mode only):

- Project name / description
- Language (Python/Node/Go/none) — drives `lint_command`, `format_command`, `test_command`
- Memory stack — Obsidian-only or Obsidian + LightRAG
- Core MCPs (Context7)
- Database MCP — none / Postgres / SQLite
- Browser automation — Playwright (yes/no)

Your answers are recorded in `.claude/config.yaml`. Re-run any time — it reconciles, preserves existing project files, and never overwrites memory or vault notes. With `--strict`, templates are rendered and validated in a temporary directory first, then the validated scaffold files are merged into the target; strict mode is not a whole-directory replacement.

## Example command

Scaffold an Obsidian-only Python project with Context7 MCP:

```bash
uvx --from ~/.local/share/project-init project-init /path/to/my-project \
  --non-interactive \
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

## Positioning in the ecosystem

Where project-init sits relative to the (fast-moving) community landscape, so
adopters know what this tool owns and where it defers:

- **What this scaffolder owns**: whole-project setup (pyproject/CI/.gitignore),
  preset composition with deterministic, tested rendering, and the integrated
  GitHub lifecycle (DAG-enforced issue → branch → PR → review → merge). No
  community plugin or scaffolder covers these.
- **Knowledge-graph memory**: the community has consolidated around
  [Graphify](https://github.com/safishamsi/graphify) for codebase knowledge
  graphs. The LightRAG overlay here remains supported; a Graphify-based preset
  is planned (#130).
- **Distributing `.claude/` components**: the official
  [Claude Code plugin marketplace](https://code.claude.com/docs/en/discover-plugins)
  is the standard channel for hooks/skills/agents. Migrating the template
  payloads to a plugin is planned (#129); the scaffolder will keep owning
  project files.
- **`AGENTS.md` vs `CLAUDE.md`**: Claude Code still reads only `CLAUDE.md`
  ([anthropics/claude-code#34235](https://github.com/anthropics/claude-code/issues/34235)),
  while most other tools read the `AGENTS.md` standard — which is why this
  repo and scaffolded projects keep both, with a redirect between them
  (inversion to AGENTS.md-canonical planned in #136).

## Further reading

- [Using project-init in Your Project](docs/guides/using-project-init.md) — full workflow, day-to-day usage, customization, and troubleshooting
- [Template System](docs/development/template-system.md) — how layers and variables work
- [Contributing](docs/development/contributing.md) — how to contribute to project-init itself

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
