# project-init

[![CI](https://github.com/VytCepas/project-init/actions/workflows/ci.yml/badge.svg)](https://github.com/VytCepas/project-init/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/project-init)](https://pypi.org/project/project-init/)
[![Python versions](https://img.shields.io/pypi/pyversions/project-init)](https://pypi.org/project/project-init/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Scaffolder for agentic-development infrastructure. One command drops a `.claude/` folder into any project so Claude Code (and other agents) have memory, docs, hooks, and curated MCPs ready to go.

**Who it's for** — solo devs and small teams running Claude Code seriously across multiple repos who want consistent, *enforced* agent infrastructure (CI, a git-lifecycle DAG guard, memory, curated MCPs) — not a hand-maintained `.claude/` per project.

```bash
uvx project-init .        # scaffold into the current directory
```

→ **How it compares** to other scaffolders and Claude Code plugins: [docs/positioning.md](docs/positioning.md).

## What it gives you

Inside any target project:

```
<your-project>/
├── AGENTS.md          # canonical agent instructions; points into .claude/
├── CLAUDE.md          # thin redirect to AGENTS.md (+ Claude-only compact instructions)
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
- **Memory is à-la-carte** — a superset ladder (ADR-024): flat agent-memory files (`--memory auto`), **plus** an Obsidian vault for humans (`obsidian`), **plus** Graphify for agents (`obsidian-graphify`), **plus** an opt-in tier-3 RAG *seam* for multi-project/monorepo scale (`obsidian-graphify-rag` — docs + a user-run setup stub, engine not bundled; #495), or **none at all** (`--memory none` / the vault-free `core` preset). When present, the vault and the agent index are separated on disk.
- **The GitHub lifecycle is à-la-carte** — the issue → branch → PR → review → merge automation (DAG guard hooks, lifecycle scripts, board/validation workflows, issue/PR templates, lifecycle skills) ships by default but is declinable (`--lifecycle none`) for a forge-agnostic or minimalist scaffold. The forge-portable quality hooks (commit-msg, gitleaks, lint/format gate, prod-safety) stay either way (ADR-021).
- **Low-token code map** — Python projects ship `.claude/scripts/gen_code_map.py`, a deterministic AST generator that writes `.claude/docs/CODE_MAP.md` (one line per module/class/function, from docstrings). Agents read it before grepping; in practice the map is ~3% of source size. Regenerate with `just code-map` (#496).
- **Deterministic-first** — hooks and scripts are bash/python. LLM calls only where generative.
- **Claude-first, portable core** — built and tested for Claude Code; other agents get instructions, not enforcement. See [Agent support tiers](#agent-support-tiers).
- **`bun` and `uv` only** — no `npm`/`npx`/`pip`/`venv` anywhere in scaffolded projects.

## Install (one-time)

Two install paths — pick by how you'll invoke it:

**CLI-only, from [PyPI](https://pypi.org/project/project-init/)** (ADR-011). Gives
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
PROJECT_INIT_REF=v0.5.1 bash -c "$(curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh)"
PROJECT_INIT_REF=main   bash -c "$(curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh)"
```

Direct tool install without the slash command (any pinned tag):

```bash
uv tool install git+https://github.com/VytCepas/project-init@v0.5.1
```

Distribution rationale: [ADR-008](https://github.com/VytCepas/project-init/blob/main/docs/adr/adr-008-distribution-channel.md) (git channel), [ADR-011](https://github.com/VytCepas/project-init/blob/main/docs/adr/adr-011-pypi-trusted-publishing.md) (PyPI via trusted publishing).

### Platform requirements

macOS, Linux, and WSL work out of the box. The scaffolded hooks and lifecycle
scripts are bash (a single bash-3.2 portability floor, epic #359) — so on **native Windows
(non-WSL)** you need **[Git for Windows](https://gitforwindows.org/)** (it ships
`bash`/`sh` + coreutils), and you should run from a **Git Bash** shell. Claude
Code then runs hooks through Git Bash automatically; the wired hooks also pin
`"shell": "bash"` to make that explicit. Without Git for Windows, Claude Code
falls back to PowerShell, which can't run a bash hook — so the enforcement
hooks won't fire. PowerShell-only is not a supported target; there are no
`.ps1` equivalents by design. (WSL remains the smoothest Windows path.)

## Agent support tiers

This is **firstly a Claude Code scaffolder**. It aims to be agent-agnostic where
that is cheap, but it is not natively so — be explicit about what each agent gets:

| Tier | What you get | Applies to |
|---|---|---|
| **Native** | Everything: deterministic hooks (lifecycle guard, pre-commit gate), skills invoked as `/commands`, settings wiring — read directly from `.claude/` | Claude Code (CLI + the Anthropic VS Code extension) |
| **Generated per-surface config** | One canonical hook/MCP spec rendered to each surface's native files (ADR-017): Codex `.codex/`, Cursor `.cursor/`, Antigravity `.agents/` (experimental), VS Code `.vscode/mcp.json`, Amp `.amp/settings.json`, Junie `.junie/mcp/mcp.json`. Skills cross-read natively. Agent hooks (incl. the Codex CLI) are **best-effort/fail-open** | Codex (CLI+IDE), Cursor, Antigravity, VS Code Copilot, Amp, JetBrains Junie |
| **Instructions + portable** | `AGENTS.md` is canonical; `CLAUDE.md` redirects to it; lifecycle scripts (plain bash), memory/vault (markdown), git hooks (`commit-msg`, `pre-push`) — agent-independent; git hooks bind once `.claude/scripts/install_hooks.sh` has run (server-side actions need branch protection) | Everything, including Ollama-based agents |

### Surface support matrix

Which scaffolded config each surface actually reads (full detail + sources:
[`docs/development/non-cli-surface-matrix.md`](docs/development/non-cli-surface-matrix.md)):

| Surface | Instructions | Skills | Hooks | MCP | Local shell |
|---|---|---|---|---|---|
| Claude Code CLI / VS Code ext | `CLAUDE.md` | `.claude/skills` | `.claude/settings.json` (honored) | root `.mcp.json` | yes |
| VS Code Copilot | `CLAUDE.md`/`AGENTS.md` | `.claude/skills` | Claude hooks (matchers ignored) | `.vscode/mcp.json` (`servers`) | yes |
| Cursor | `AGENTS.md` | `.claude/skills` | `.cursor/hooks.json` (best-effort) | `.cursor/mcp.json` | yes |
| Codex (CLI + IDE) | `AGENTS.md` | `.agents/skills` | `.codex/hooks.json` (advisory) | `.codex/config.toml` | yes |
| Antigravity (`agy`) | `AGENTS.md` | `.agents/skills` | `.agents/hooks.json` (experimental) | `.agents/mcp_config.json` | yes |
| Amp | `AGENTS.md` | `.agents/skills` | — | `.amp/settings.json` (`amp.mcpServers`) | yes |
| JetBrains Junie | `AGENTS.md` | `.junie/skills` | — | `.junie/mcp/mcp.json` | yes |
| Ollama-based | `AGENTS.md` | — | — | — | yes |

`AGENTS.md` is the portability backbone (every surface reads it); `CLAUDE.md`
rides alongside for Claude + VS Code. The generated `.claude/CAPABILITIES.md`
lists exactly what a given scaffold exposes, on any surface.

### Local vs. cloud: where enforcement actually runs (ADR-007)

The execution model — not the surface name — decides what binds:

- **Local-execution surfaces** (Claude Desktop-local, VS Code, Codex IDE, Cursor,
  Antigravity, Gemini Code Assist): bash hooks + git hooks + MCP stdio servers all
  run on your machine, so the enforcement layer is live (subject to the
  per-surface fidelity above — some drop hook matchers).
- **Cloud-sandbox surfaces** (Claude web, Codex cloud, Jules): only
  **repo-committed** config runs; user-level `~/.claude` is dropped, hooks run
  inside the VM, and git goes through a push-restricted proxy — the local
  enforcement layer is replaced by the sandbox's.

Two honest caveats hold across all of it:

- **Agent hook enforcement (including the Codex CLI) is best-effort, not a guarantee.** Generated hooks are
  fail-open, some surfaces ignore matchers, and some (e.g. codex 0.138.0) may not
  fire project-scoped hooks without an enable step; an agent reading `AGENTS.md` is
  *asked* to follow the rules. The **git hooks + CI checks are the only
  enforcement that binds every surface** — that is the real boundary (ADR-007).
- **Automated testing covers the Claude Code artifacts + the rendered per-surface
  files.** The suite validates settings/skills/hooks/MCP and the generated
  surface configs; no GUI agent is driven live in CI.

## Use

### Option 1: Inside a Claude Code session (interactive)

After the **git install** (`install.sh`), a `/project-init` slash command is available in any Claude Code session:

```
/project-init
```

This runs the interactive wizard in the current project directory. It asks for project name, language, delivery model, memory stack, and MCPs — then scaffolds `.claude/` for you.

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
- Delivery model (`--delivery library|service|prototype`) — how the project ships, driving its env/CI/release bundle (ADR-015). `service` adds the container **parity bundle** (Dockerfile + `compose.yaml` + devcontainer + `just up`/`build`) and unlocks the deploy overlay; `library` adds a tag-triggered release workflow (publish **disabled** until you wire the registry); `prototype` (default) adds nothing env-specific. `service` requires a language.
- Deploy overlay (`--deploy none|cloud-run|fly|k8s|registry|custom`) — opt-in, **service only**. Container targets scaffold a build-once-**by-digest** `deploy.yml` (GitHub Environments: staging auto-deploys, production is **gated**) + a declarative `deploy/environments.yaml`, plus `setup_env_protection.sh` (server-side prod gate, tiered by profile) and `whats_deployed.sh`. `none` (default) = your platform (Vercel/Render/Fly/…) owns deploy.
- Infrastructure-as-Code (`--iac none|opentofu`) — opt-in OpenTofu/HCL skeleton under `infra/` + a plan-on-PR workflow (apply is **manual / environment-gated**, never apply-on-merge). Emits structure only — no resources or credentials.
- Multi-model switching (`--multi-model`) — opt-in overlay (ADR-016) that scaffolds a [claude-code-router](https://github.com/musistudio/claude-code-router) config + a `setup_models.sh` installer, so you can run DeepSeek/Kimi/Ollama **through the Claude Code harness** with live `/model` switching and background **cost-routing** — your hooks, CI gates, and standards stay identical (they run below the model). OpenAI/Codex is better in its native `--agents` harness. CCR is **pinned**, machine-level, and the scaffolder never runs it (ADR-001). Clean by default.
- AI governance (`--governance`) — opt-in overlay (ADR-018) that ships **governance-as-code** for projects that build or operate an AI system: a **policy layer** (AI usage policy, approved-tools / data-handling / code-provenance docs, NIST RMF crosswalk), a **system card** template carrying a flat-scalar governance manifest, a two-file **AIBOM** (generated MCP + detected-CCR-route inventory, plus a user-owned declarations file), and a **presence-triggered CI gate** that validates every real system card (required fields, allowed values, the `prohibited`+`allowed:true` illegal combo, declarations completeness, `last_reviewed` staleness) — failing the build, not producing a PDF. Adopts NIST AI RMF / ISO 42001 / EU AI Act / OWASP conventions (referenced, not re-authored). A freshly scaffolded project ships only an example/template, so the gate passes until a team deliberately writes a card. Most projects are not AI products — strictly opt-in, off by default. The `governed` preset enables it.
- Observability (`--observability`) — opt-in overlay (ADR-019) that scaffolds a **file-based usage report**: a stdlib analyzer over the Claude Code transcript JSONL plus a guarded, stdin-safe hook self-log, rendered to an HTML report with one command. **No Docker, no OTEL, no egress** — everything stays on disk. Lets you see what your agents actually do (tokens, tool calls, activity) without a telemetry backend. Strictly opt-in, off by default.
- Memory backend (`--memory none|auto|obsidian|obsidian-graphify|obsidian-graphify-rag`) — a **superset ladder** (ADR-024): **none** (vault-free; the `core` preset), **auto** (flat agent-memory files in `.claude/memory/`, no vault — pure files, installs nothing), **Obsidian-only** (auto **plus** a human markdown vault), **Obsidian + Graphify** (obsidian **plus** a derived code knowledge graph; recommended for code-heavy projects), or **+ RAG** (`obsidian-graphify-rag`, tier 3 — a semantic recall *seam*: docs + a user-run `setup_rag.sh` stub + the `rag_endpoint` descriptor, **engine not bundled**; worth it only at multi-project/monorepo scale, parked in #495). Each rung adds a retrieval surface without relocating the anchors. The flag overrides the preset's default; the wizard explains each backend and its install cost before asking (#466, #497, ADR-024).
- GitHub lifecycle (`--lifecycle github|none`) — **github** (default) ships the issue → branch → PR → review → merge automation: DAG guard hooks, lifecycle scripts (`start_issue`/`finish_pr`/…), board/PR-validation workflows, issue/PR templates, the `create_issue`/`start_task`/`github_workflow` skills, and — in plugin mode — the `project-init-lifecycle` plugin. **none** declines it for a forge-agnostic or minimalist scaffold (the `core` preset's audience). The forge-portable quality hooks (commit-msg, gitleaks secret scan, lint/format gate, prod-safety) stay either way. The flag overrides the preset's default; the wizard explains it before asking (#476, ADR-021).
- Core MCPs (Context7)
- Database MCP — none / Postgres / SQLite
- Browser automation — Playwright (yes/no)
- Owner/team (`--owner`) — default CODEOWNERS owner, SECURITY contact, and LICENSE copyright holder (e.g. `@org/team`)
- License (`--license mit|apache-2.0|proprietary|none`) — renders a LICENSE with the current year and the owner (or project name); `none` skips the file
- No-plugin fallback (`--no-plugin`) — copies the shared hooks/skills into `.claude/` and wires them in `settings.json` instead of relying on the `project-init-workflow` plugin (offline / no-trust environments)
- Devcontainer (`--devcontainer`) — renders `.devcontainer/` for Codespaces, fresh clones, and remote agent containers (see below)
- Agents & surfaces (`--agents claude,codex,ollama,cursor,antigravity,vscode,amp,junie`) — which agents/editors the project supports; default `claude`. **Amp** and **JetBrains Junie** get a skills layer plus generated MCP config (`.amp/settings.json` key `amp.mcpServers`; `.junie/mcp/mcp.json`). Selecting the `context7-http` MCP emits an HTTP/streamable entry (`type: http`) — the transport that works on Claude web/mobile/Cowork, where stdio servers are invisible. Codex gets the shared skills at `.agents/skills/` plus the command guard wired via `.codex/hooks.json` (advisory — codex 0.138.0 may not fire project hooks without an enable step); **Antigravity** (`agy`, Google's CLI/IDE) gets the shared skills at `.agents/skills/`, the command guard via `.agents/hooks.json` (experimental), and project MCP at `.agents/mcp_config.json`; Ollama-based agents are instructions-level only. (Gemini CLI was removed in PI-386 — Google sunset its free/Pro/Ultra tiers on 2026-06-18; Antigravity, which reads the same `.agents/` tree, is the Google target.) Other GUI surfaces get generated per-surface config from one canonical source (ADR-017): **Cursor** → `.cursor/hooks.json` + `.cursor/mcp.json`, **VS Code** → `.vscode/mcp.json`; selecting any MCP also emits a root `.mcp.json` (Claude's shareable project scope) and `.codex/config.toml` when Codex is on. Skills are read natively by all of these. Agent hooks (incl. the Codex CLI) are best-effort/fail-open (their exact blocking I/O wasn't live-verified — e.g. codex 0.138.0 may not fire project hooks without an enable step); git hooks + CI remain the only enforcement that binds every surface. Only the Claude path is functionally CI-tested — overlays are contract-tested on the rendered files
- Toolchain pinning (`--mise`) — renders `mise.toml` pinning runtime/tool versions. Ownership rule: mise owns versions only; uv/bun own dependencies, just owns commands, `.env` owns environment
- Docs tooling (`--no-docs`) — by default a python project gets `mkdocs.yml` and a node project gets `typedoc.json` (local-preview configs — there is no publish workflow; ADR-022/PI-343). `--no-docs` declines them; the wizard asks per language (#477)
- Renovate (`--no-renovate`) — `renovate.json` (the Renovate dependency-update bot config) ships by default; `--no-renovate` declines it if you use a different update mechanism (#477, ADR-022)
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

Your answers are recorded in `.claude/config.yaml`. On the **first** scaffold into a project that already has files, your existing files are never clobbered: when a generated file (e.g. a hand-written `CLAUDE.md`) would differ, the new render is written alongside as a `<file>.new` sibling for you to merge, and the run prints which files were preserved. On a **re-run** (config already present) it refreshes the files project-init manages and never overwrites your `memory/` or `vault/` notes. With `--strict`, templates are rendered and validated in a temporary directory first, then the validated scaffold files are merged into the target; strict mode is not a whole-directory replacement.

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
project-init upgrade /path/to/my-project              # drift report only, touches nothing
project-init upgrade /path/to/my-project --apply      # apply the changes
project-init upgrade /path/to/my-project --apply -i   # decide per file: update / skip / diff
```

With `-i`/`--interactive`, `--apply` walks each changed/merged/conflicting file
and prompts to update it, skip it, or show its diff — skipped files stay drifted
and are re-offered next upgrade. New-file additions still use the
`--accept-new`/`--decline-new` group consent.

**Upgrade as a PR.** Every scaffold ships a `.github/workflows/project-init-upgrade.yml`
workflow (manual `workflow_dispatch`, opt into a cadence by uncommenting the
`schedule:` block). It runs the upgrade on a fresh branch and opens a pull request with the
drift — Renovate-style, but for the scaffold — so the change never lands on your
default branch unreviewed and `.new` conflicts show up right in the PR diff. It
installs project-init from your recorded source URL (so forks/GHES hosts work)
and uses the built-in `GITHUB_TOKEN`; set an `UPGRADE_PR_TOKEN` secret if you
want CI to run on the upgrade PR.

The report classifies every template-owned file:

| State | Meaning | `--apply` does |
|---|---|---|
| new | not in your project | creates it |
| changed | drifted, but you never edited it | updates it |
| merged | drifted **and** locally edited, but the edits don't overlap | 3-way auto-merges both in place — no `.new` sibling |
| conflict | drifted **and** locally edited with overlapping changes | keeps your file; writes the conflict-marked merge as a `<file>.new` sibling — your edit is never overwritten |
| removed | no longer rendered by current templates | nothing (reported only; upgrade never deletes) |

**Migration notes.** Alongside the file drift, upgrade prints the curated
changelog/migration notes for the version span it crosses (recorded → target),
with any **action required** step called out prominently — so you know *why* the
files changed, not just *which*. The notes are packaged and read offline (no
changelog fetch).

`.claude/memory/` and `.claude/vault/` are never compared or touched, and
`.claude/config.yaml` keeps your hand-edited fields (`project_key`, board
number) — only its `project_init_version` and the scaffold record are
refreshed.

How it works: scaffolding records the preset, template variables, and a
content-hash manifest in a `scaffold:` block at the end of
`.claude/config.yaml`, plus the rendered text of each managed (UTF-8) file in a
`.claude/.upgrade-base.json` sidecar. Upgrade re-renders the same preset at the
current template version into a staging directory and compares hashes, so user
edits are distinguishable from upstream template changes. When both you and the
templates changed a file, the sidecar is the *base* leg of a 3-way merge (via
`git merge-file`, with a pure-Python fallback): non-overlapping edits auto-merge,
only true overlaps become a `<file>.new` conflict. **Migration:** projects
scaffolded before this record existed are reconstructed from the semantic config
fields; without recorded hashes or a base, every modified file is conservatively
treated as a conflict (`.new` sibling). Run `upgrade --apply` once and the record
is written for next time.

### Adding or removing a concern later

Changed your mind about a tier you declined (or want to drop one)? `add` and
`remove` toggle a single concern on an **already-scaffolded** project — no need to
re-run the wizard. They reuse the upgrade engine, so the shared wiring
(`settings.json`, `config.yaml`, CI) is re-rendered with the concern flipped.

```bash
project-init add governance --target /path/to/proj          # dry-run: report only
project-init add governance --target /path/to/proj --apply  # land it
project-init add memory obsidian-only --target /path --apply # memory takes a tier
project-init remove lifecycle --target /path/to/proj --apply # drop a concern
```

Concerns: `lifecycle`, `governance`, `observability`, `multi-model`, `docs`,
`renovate`, and `memory <stack>` (`auto` · `obsidian-only` · `obsidian-graphify` ·
`obsidian-graphify-rag` · `none`).

- **Dry-run by default** — without `--apply` it only reports what would change.
- **`--apply` is git-guarded** — it refuses a dirty work tree (so the change lands
  as one revertible diff); `--allow-dirty` overrides.
- **`remove` never destroys your edits** — it deletes a concern's files only when
  they are byte-identical to what it scaffolded; a file you edited is kept and
  reported.
- **Your notes are safe** — `remove memory` unwires the tier but **keeps**
  `.claude/memory/` and `.claude/vault/` (your accumulated notes) by default. To
  also handle that source data, opt in explicitly:

  ```bash
  project-init remove memory --target /path --apply --export ~/notes-backup  # move it out first
  project-init remove memory --target /path --apply --purge                  # delete it (destructive)
  ```

  `--purge` and `--export` are mutually exclusive; `--purge` prints what it will
  delete and (like all `--apply` runs) requires a clean tree, so the data is
  recoverable from git. The same flags also clean **governance** user files.

**Known limits.** `multi-model`'s CCR config lives in your global `~/.config`
(outside the project), so `--purge` does not touch it. A memory tier *downgrade*
done via `add memory <lower-tier>` keeps the now-unused higher-tier data in place;
to drop it, `remove memory --purge` then `add memory <tier>` again, or delete the
directory yourself.

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
Run `project-init --help` and pick from `core` (vault-free), `auto` (memory files, no vault), `obsidian-only`, `obsidian-graphify` (ADR-009), or `governed`. Custom presets go in `templates/presets/<name>.toml`.

## Positioning in the ecosystem

Where project-init sits relative to the (fast-moving) community landscape, so
adopters know what this tool owns and where it defers. For the full
four-category comparison and the moat, see
[docs/positioning.md](docs/positioning.md):

- **What this scaffolder owns**: project infrastructure files (CI workflows,
  `.gitignore`, GitHub issue/PR templates and board automation),
  preset composition with deterministic, tested rendering, and the integrated
  GitHub lifecycle (DAG-enforced issue → branch → PR → review → merge). No
  community plugin or scaffolder covers these.
- **Knowledge-graph memory**: the community has consolidated around
  [Graphify](https://github.com/safishamsi/graphify) for codebase knowledge
  graphs. The `obsidian-graphify` preset wires it in (ADR-009).
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
  repo and scaffolded projects keep both: `AGENTS.md` is the canonical source of
  truth and `CLAUDE.md` redirects to it — Claude Code still
  reads `CLAUDE.md` only because of the issue above (the #136 inversion shipped).

## Further reading

- [Using project-init in Your Project](https://github.com/VytCepas/project-init/blob/main/docs/guides/using-project-init.md) — full workflow, day-to-day usage, customization, and troubleshooting
- [Template System](https://github.com/VytCepas/project-init/blob/main/docs/development/template-system.md) — how layers and variables work
- [Contributing](https://github.com/VytCepas/project-init/blob/main/docs/development/contributing.md) — how to contribute to project-init itself

## Layout of this repo

```
project-init/
├── pyproject.toml              # uv-managed, rich-only runtime dep, ruff-only dev
├── install.sh                  # bootstrap one-liner
├── src/project_init/           # wizard CLI + scaffold engine (scaffold, concerns, surfaces, mcps, …)
├── templates/
│   ├── base/                   # always copied
│   ├── fallback/               # shared hooks/skills — rendered only with --no-plugin (ADR-010)
│   ├── presets/                # toml preset definitions
│   ├── obsidian/               # vault + agent-memory overlay
│   ├── graphify/               # Graphify memory overlay (implies obsidian)
│   ├── rag/                    # tier-3 RAG memory overlay
│   ├── lifecycle/              # git lifecycle enforcement (+ lifecycle_fallback for --no-plugin)
│   ├── multi_model/            # CCR model-switching overlay (--multi-model)
│   ├── observability/          # transcript metrics overlay (--observability)
│   ├── governance/             # AI governance overlay (--governance)
│   ├── auto/                   # always-on emitted artifacts
│   └── amp/ antigravity/ codex/ junie/  # per-surface wiring overlays (--agents)
└── tests/                      # focused pytest modules by behavior area
```

## Status

Actively developed and published to [PyPI](https://pypi.org/project/project-init/) (current release: v0.5.1). Contributions welcome — track and propose work in [GitHub Issues](https://github.com/VytCepas/project-init/issues), and use [GitHub Discussions](https://github.com/VytCepas/project-init/discussions) for questions, ideas, and feedback. Forks and pull requests are encouraged.

## License

Apache-2.0 — see [LICENSE](https://github.com/VytCepas/project-init/blob/main/LICENSE).
