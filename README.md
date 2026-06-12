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
    └── vault/               # Obsidian vault (humans)
        ├── decisions/ design/ sessions/ knowledge/
```

Principles:
- **One folder, `.claude/`**, for everything agentic. Project root stays clean.
- **Obsidian vault for humans, Graphify (optional) for agents** — separated on disk.
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
| **Portable regardless** | Lifecycle scripts (plain bash), memory and vault (plain markdown), git hooks (`commit-msg`, `pre-push`) — agent-independent by construction; git hooks bind once `.claude/scripts/install_hooks.sh` has run in the clone (server-side actions need branch protection) | Everything, including Ollama-based agents |

Two honest caveats:

- Hook enforcement and skill invocation **do not exist outside Claude Code**. An
  agent reading `AGENTS.md` is asked to follow the rules; nothing makes it.
  The git hooks and CI checks are the only enforcement that binds all agents.
- **Automated testing covers the Claude Code artifacts only.** The test suite
  validates settings schema, skills, hooks, and rendered files; no other agent
  is exercised in CI.

## Install (one-time)

Two install paths — pick by how you'll invoke it:

**CLI-only, from PyPI** (after the first published release; ADR-011). Gives
you the `project-init` command — no `/project-init` slash command:

```bash
uv tool install project-init   # or one-off: uvx project-init .
```

**Full setup, from git** — adds the Claude Code slash command:

```bash
curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh | bash
```

This installs [`uv`](https://docs.astral.sh/uv/) if missing, clones the repo to `~/.local/share/project-init` (override with `PROJECT_INIT_HOME=...`) **pinned to the latest tagged release**, and writes a user-level slash command at `~/.claude/commands/project-init.md`.

Pin a specific version, or opt into the unreleased development head:

```bash
PROJECT_INIT_REF=v0.3.0 bash -c "$(curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh)"
PROJECT_INIT_REF=main   bash -c "$(curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh)"
```

Direct tool install without the slash command (any pinned tag):

```bash
uv tool install git+https://github.com/VytCepas/project-init@v0.3.0
```

Distribution rationale: [ADR-008](https://github.com/VytCepas/project-init/blob/main/docs/adr/adr-008-distribution-channel.md) (git channel), [ADR-011](https://github.com/VytCepas/project-init/blob/main/docs/adr/adr-011-pypi-trusted-publishing.md) (PyPI via trusted publishing).

## Use

### Option 1: Inside a Claude Code session (interactive)

After the **git install** (`install.sh`), a `/project-init` slash command is available in any Claude Code session:

```
/project-init
```

This runs the interactive wizard in the current project directory. It asks for project name, language, memory stack, and MCPs — then scaffolds `.claude/` for you.

### Option 2: From a shell (non-interactive, for CI / scripts)

With the PyPI install, plain `project-init . --non-interactive …` (or
`uvx project-init . …`) works anywhere. With the git install:

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
- Memory stack — Obsidian-only or Obsidian + Graphify (recommended for code-heavy projects)
- Core MCPs (Context7)
- Database MCP — none / Postgres / SQLite
- Browser automation — Playwright (yes/no)
- Owner/team (`--owner`) — default CODEOWNERS owner, SECURITY contact, and LICENSE copyright holder (e.g. `@org/team`)
- License (`--license mit|apache-2.0|proprietary|none`) — renders a LICENSE with the current year and the owner (or project name); `none` skips the file
- No-plugin fallback (`--no-plugin`) — copies the shared hooks/skills into `.claude/` and wires them in `settings.json` instead of relying on the `project-init-workflow` plugin (offline / no-trust environments)
- Devcontainer (`--devcontainer`) — renders `.devcontainer/` for Codespaces, fresh clones, and remote agent containers (see below)
- Agents (`--agents claude,codex,gemini,ollama`) — which agents the project supports; default `claude`. Codex gets the shared skills at `.agents/skills/` plus the command guard via `.codex/hooks.json`; Gemini CLI gets a project extension (workflow `/commands` + guard; link once with `.claude/scripts/setup_gemini.sh`); Ollama-based agents are instructions-level only. Only the Claude path is functionally CI-tested — overlays are contract-tested on the rendered files
- Toolchain pinning (`--mise`) — renders `mise.toml` pinning runtime/tool versions. Ownership rule: mise owns versions only; uv/bun own dependencies, just owns commands, `.env` owns environment
- Editor config (`--vscode`) — renders `.vscode/extensions.json` + a minimal `settings.json` (format-on-save wired to the preset formatter); nothing personal, and the `.gitignore` shares only these two files

Every preset also scaffolds the env/secret pattern: `.env.example`
documents the variables and their loading order, `.env` is gitignored, and
`.claude/docs/guides/secrets.md` covers when and how to escalate to an org
secret manager (sops / 1Password CLI / Doppler) — none is installed, that
choice is org-specific.

Every preset also ships governance starters: `.github/CODEOWNERS`,
`CONTRIBUTING.md` (setup, `just --list` command surface, branch/PR
conventions, review flow), and `SECURITY.md`. After pushing to GitHub, run
`.claude/scripts/setup_github.sh --protect` inside the project to apply
baseline branch protection (require CI green, require PR review, block
force-push) — unprotected default branches undermine the workflow
enforcement everything else sets up.

Your answers are recorded in `.claude/config.yaml`. Re-run any time — it reconciles, preserves existing project files, and never overwrites memory or vault notes. With `--strict`, templates are rendered and validated in a temporary directory first, then the validated scaffold files are merged into the target; strict mode is not a whole-directory replacement.

### Remote and web agent sessions

Scaffolded projects bootstrap themselves in ephemeral environments
(Claude Code on the web, CI agents, fresh clones):

- A **SessionStart hook** (`.claude/hooks/session_setup.sh`) syncs
  dependencies when a session opens in a cold environment — `just setup`
  when available, falling back to `uv sync` / `bun install` /
  `go mod download`. Warm sessions are a no-op: a content stamp of the
  dependency manifests short-circuits before any tool runs, and a failed
  bootstrap warns without blocking the session.
- The opt-in **`--devcontainer`** flag renders a minimal
  `.devcontainer/` (Ubuntu base image; post-create installs `just` plus
  the language toolchain and reuses the same bootstrap) — one consistent
  environment for new colleagues, Codespaces, and agent containers.

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

Re-run the installer — it moves the clone to the latest tagged release:

```bash
curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh | bash
```

(`PROJECT_INIT_REF=main` for the development head; releases are cut by
tagging `vX.Y.Z`, which triggers the release workflow.)

### Upgrading a scaffolded project

Scaffolded projects are snapshots — as project-init improves, they drift.
After updating the tool itself, re-render any project from its recorded
config and see what changed:

```bash
project-init upgrade /path/to/my-project           # drift report only, touches nothing
project-init upgrade /path/to/my-project --apply   # apply the changes
```

The report classifies every template-owned file:

| State | Meaning | `--apply` does |
|---|---|---|
| new | not in your project | creates it |
| changed | drifted, but you never edited it | updates it |
| conflict | drifted **and** locally edited | writes the new render as a `<file>.new` sibling — your edit is never overwritten |
| removed | no longer rendered by current templates | nothing (reported only; upgrade never deletes) |

`.claude/memory/` and `.claude/vault/` are never compared or touched, and
`.claude/config.yaml` keeps your hand-edited fields (`project_key`, board
number) — only its `project_init_version` and the scaffold record are
refreshed.

How it works: scaffolding records the preset, template variables, and a
content-hash manifest in a `scaffold:` block at the end of
`.claude/config.yaml`. Upgrade re-renders the same preset at the current
template version into a staging directory and compares hashes, so user
edits are distinguishable from upstream template changes. **Migration:**
projects scaffolded before this record existed are reconstructed from the
semantic config fields; without recorded hashes, every modified file is
conservatively treated as a conflict (`.new` sibling). Run `upgrade --apply`
once and the record is written for next time.

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
Run `project-init --help` and pick from `obsidian-only` or `obsidian-graphify` (ADR-009). Custom presets go in `templates/presets/<name>.toml`.

## Positioning in the ecosystem

Where project-init sits relative to the (fast-moving) community landscape, so
adopters know what this tool owns and where it defers:

- **What this scaffolder owns**: project infrastructure files (CI workflows,
  `.gitignore`, GitHub issue/PR templates and board automation),
  preset composition with deterministic, tested rendering, and the integrated
  GitHub lifecycle (DAG-enforced issue → branch → PR → review → merge). No
  community plugin or scaffolder covers these.
- **Knowledge-graph memory**: the community has consolidated around
  [Graphify](https://github.com/safishamsi/graphify) for codebase knowledge
  graphs. The `obsidian-graphify` preset wires it in (ADR-009); the
  hand-rolled LightRAG overlay was removed once Graphify landed (PI-172).
- **Distributing `.claude/` components**: the official
  [Claude Code plugin marketplace](https://code.claude.com/docs/en/discover-plugins)
  is the standard channel for hooks/skills/agents. This repo doubles as a
  marketplace (`.claude-plugin/marketplace.json`) shipping the
  `project-init-workflow` plugin — the project-agnostic skills and guard
  hooks, auto-update included. Scaffolds are **plugin-first** (ADR-010
  cutover): `settings.json` enables the plugin, and a hook or skill fix
  shipped in the plugin reaches every project without re-scaffolding. The
  `--no-plugin` flag restores file copies + local wiring for offline or
  no-marketplace-trust environments; the scaffolder keeps owning project
  files either way.
- **`AGENTS.md` vs `CLAUDE.md`**: Claude Code still reads only `CLAUDE.md`
  ([anthropics/claude-code#34235](https://github.com/anthropics/claude-code/issues/34235)),
  while most other tools read the `AGENTS.md` standard — which is why this
  repo and scaffolded projects keep both: today `AGENTS.md` (and `GEMINI.md`)
  redirect readers to the canonical `CLAUDE.md`; inverting that so `AGENTS.md`
  becomes canonical is planned in #136.

## Further reading

- [Using project-init in Your Project](https://github.com/VytCepas/project-init/blob/main/docs/guides/using-project-init.md) — full workflow, day-to-day usage, customization, and troubleshooting
- [Template System](https://github.com/VytCepas/project-init/blob/main/docs/development/template-system.md) — how layers and variables work
- [Contributing](https://github.com/VytCepas/project-init/blob/main/docs/development/contributing.md) — how to contribute to project-init itself

## Layout of this repo

```
project-init/
├── pyproject.toml            # uv-managed, rich-only runtime dep, ruff-only dev
├── install.sh                # bootstrap one-liner
├── src/project_init/         # wizard CLI + scaffold engine
├── templates/
│   ├── base/                 # always copied
│   ├── obsidian/             # Obsidian vault overlay (both presets)
│   ├── graphify/             # Graphify memory overlay
│   └── presets/              # toml preset definitions
├── examples/                 # sample scaffolded outputs
└── tests/                    # focused pytest modules by behavior area
```

## Status

All milestones (PI-1 through PI-18) are shipped. v0.1.0 released. Track future work in [GitHub Issues](https://github.com/VytCepas/project-init/issues).

## License

Apache-2.0 — see [LICENSE](https://github.com/VytCepas/project-init/blob/main/LICENSE).
