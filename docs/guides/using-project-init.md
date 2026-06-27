# Using project-init in Your Project

project-init scaffolds a `.claude/` folder into any project so that Claude Code (and other agents) have memory, documentation, hooks, and GitHub workflow infrastructure ready from day one.

---

## 1. Install (once)

```bash
curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh | bash
```

Installs `uv` if missing, clones the repo to `~/.local/share/project-init`, and writes a `/project-init` slash command into `~/.claude/commands/`.

---

## 2. Two Ways to Scaffold

### Option 1 — Inside Claude Code (interactive)

In any Claude Code session, run:

```
/project-init
```

The wizard asks for project name, language, memory stack, and MCPs — then scaffolds `.claude/` in the current project directory.

### Option 2 — From a shell (non-interactive, for CI or scripting)

```bash
cd your-project
uvx --from ~/.local/share/project-init project-init . \
  --non-interactive \
  --preset obsidian-only \
  --name my-app \
  --description "A short description" \
  --language python \
  --mcps context7
```

Available flags:

| Flag | Values | Default |
|------|--------|---------|
| `--preset` | `obsidian-only`, `obsidian-graphify` | (asked interactively) |
| `--language` | `python`, `node`, `go`, `none` | `none` |
| `--mcps` | `context7` (comma-separated) | none |
| `--browser` | flag (Playwright MCP) | off |
| `--strict` | flag (fail on unrendered placeholders) | off |

---

## 3. Choosing a Preset

| Preset | When to use |
|--------|-------------|
| **obsidian-only** | Small to medium projects. Plain markdown vault, no external APIs needed. Human-friendly and agent-readable. |
| **obsidian-graphify** | Code-heavy projects. Adds a Graphify code knowledge graph agents query before grepping. No API keys for IDE use (ADR-009). |

Start with `obsidian-only` when in doubt. Upgrade later by re-running with `--preset obsidian-graphify` — it merges without overwriting your existing memory or vault content.

---

## 4. What Gets Created

```
your-project/
├── AGENTS.md                    # Canonical agent instructions (most agents read this)
├── CLAUDE.md                    # Claude Code entry point — redirects to AGENTS.md
└── .claude/
    ├── project-init.md          # Workflow and conventions
    ├── config.yaml              # Record of wizard answers
    ├── settings.json            # Claude Code hooks
    ├── memory/
    │   ├── MEMORY.md            # Grep-able memory index
    │   ├── SCHEMA.md            # Memory type definitions
    │   ├── project_context.md   # Starter: project goals
    │   └── user_role.md         # Starter: team preferences
    ├── vault/                   # Obsidian vault — open this dir as vault root
    │   ├── log.md               # Operational log (auto-appended by hooks)
    │   ├── decisions/           # Architecture Decision Records
    │   ├── design/              # Design notes
    │   ├── sessions/            # Session summaries
    │   └── knowledge/           # Reference material
    ├── docs/                    # Agent-readable reference docs
    ├── hooks/                   # Deterministic safety hooks
    ├── scripts/                 # GitHub lifecycle scripts
    ├── skills/                  # Slash commands (/start_task, etc.)
    ├── rules/                   # Language-specific agent rules
    └── agents/                  # Sub-agent persona specs
```

Plus `.github/` additions: CI workflows, issue templates, PR template, board automation.

---

## 5. Day-to-Day Usage

### Agent Entry Point

Agents read `CLAUDE.md` first. It links to:

- `.claude/project-init.md` — workflow conventions, GitHub issue/PR patterns
- `.claude/memory/MEMORY.md` — memory index (context without loading every file)
- `.claude/docs/` — ADRs and development guides

Keep `CLAUDE.md` updated with project-specific rules as conventions emerge.

### Memory System

Memory lives in `.claude/memory/`. Four types:

| Type | What goes here |
|------|---------------|
| `user` | Team role, preferences, expertise |
| `feedback` | What approaches worked or failed |
| `project` | Current goals, deadlines, key decisions |
| `reference` | Where to find things (dashboards, issue trackers, etc.) |

Each memory is a markdown file with YAML frontmatter. `MEMORY.md` is the index — agents grep it without loading every file.

Run `/session_summary` at the end of each session to record what was done and update memory.

### Obsidian Vault

Open `.claude/vault/` as the vault root in Obsidian to get wikilinks, graph view, and Templater templates for ADRs, session notes, design notes, and knowledge entries.

Session notes land in `vault/sessions/` via `/session_summary` — a running operational log.

Write an ADR for every non-obvious architectural decision. Future agents will understand why choices were made.

### Hooks

Wired in `.claude/settings.json`:

| Hook | Trigger | Purpose |
|------|---------|---------|
| `pre_commit_gate.sh` | Pre-commit | Runs lint and format before every commit |
| `github_command_guard.sh` | git/gh commands | Steers toward lifecycle scripts |

Security enforcement is agent-agnostic (ADR-007): a gitleaks `pre-commit`
git hook scans staged changes for secrets, `commit-msg`/`pre-push` git hooks
gate the lifecycle (install once per clone with
`.claude/scripts/install_hooks.sh`), and CI mirrors both with a
`secret-scan` job and the `validate-pr` workflow. Claude-side guidance comes
from the official `security-guidance` plugin, enabled in `settings.json`.

### Skills (Slash Commands)

| Skill | Purpose |
|-------|---------|
| `/start_task` | Create GitHub issue + branch + draft PR |
| `/session_summary` | Save session note and update memory |
| `/github_workflow` | Load PR lifecycle instructions |
| `/add_hook` | Add a new hook to `settings.json` |
| `/add_adr` | Record an architectural decision (MADR template) |
| `/add_command` | Create a new slash command |
| `/audit` | Review for security and quality issues |

Use `/start_task` before any non-trivial work — one issue, one branch, one PR keeps work traceable.

---

## 6. Graphify (Optional — Code-Heavy Projects)

If you chose `obsidian-graphify`, run the one-time setup and build the graph:

```bash
.claude/scripts/setup_graphify.sh   # installs the CLI, skill, and post-commit hook
# then inside your agent: /graphify .
```

The graph rebuilds incrementally per commit; agents query `graphify-out/graph.json` before grepping (see `.claude/rules/graphify.md`). No API keys needed for IDE use.

---

## 7. Common Customization

**Add a hook**: run `/add_hook` or edit `.claude/settings.json` directly. Scripts go in `.claude/hooks/`.

**Add a slash command**: run `/add_command`. Creates a `SKILL.md` in `.claude/skills/<name>/`. Register it in `.claude/skills/INDEX.md`.

**Re-run to update**: `/project-init` is safe to re-run anytime. It never overwrites `memory/` or `vault/` content.

**Add or remove a whole concern later**: to opt into a tier you declined at init —
or drop one you no longer want — use `add` / `remove` instead of re-running the
wizard. They toggle one concern and re-render the shared wiring:

```bash
project-init add governance --target . --apply        # opt into a declined tier
project-init add memory obsidian-only --target . --apply
project-init remove lifecycle --target . --apply       # drop a concern
```

Concerns: `lifecycle`, `governance`, `observability`, `multi-model`, `docs`,
`renovate`, `memory <stack>`. Both default to a **dry-run** (report only) until you
pass `--apply`, which requires a clean git tree.

`remove` deletes only the files it scaffolded unchanged — your edits are kept. And
`remove memory` **keeps your notes** (`memory/`, `vault/`) by default; to also move
or delete that source data, add `--export <dir>` (move it out first) or `--purge`
(delete it — destructive, commit first so git can recover it):

```bash
project-init remove memory --target . --apply --export ~/notes-backup
project-init remove memory --target . --apply --purge
```

---

## 8. Validation After Scaffolding

```bash
# Verify hooks are in place
ls .claude/hooks/

# Lint memory index integrity
bash .claude/scripts/lint_memory.sh

# Confirm pre_commit_gate fires
git commit --allow-empty -m "test: verify hooks"
```

---

## 9. Troubleshooting

| Problem | Fix |
|---------|-----|
| `/project-init` not found | Re-run install script; check `~/.claude/commands/project-init.md` exists |
| `uv: command not found` | Add `export PATH="$HOME/.local/bin:$PATH"` to shell profile |
| `bunx: command not found` when adding MCPs | `curl -fsSL https://bun.sh/install \| bash` |
| Hooks don't fire on commit | Check `python3 --version`; hooks need `python3` on PATH |
| Hooks never fire on native Windows | Install [Git for Windows](https://gitforwindows.org/) and run from Git Bash. The hooks are bash; without Git Bash, Claude Code falls back to PowerShell, which can't run them. PowerShell-only is unsupported (no `.ps1` variants). WSL avoids this entirely. |
| Unrendered `{{...}}` in output | Re-run with `--strict` to surface the missing variable |
| `lint_memory.sh` reports errors | Each file in `memory/` needs a matching entry in `MEMORY.md` |
| CRLF line ending errors on WSL | Edit and commit from inside WSL, not Git Bash on Windows |
