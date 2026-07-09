# project-init — agent notes

This repo is a **scaffolder**. It produces a `.agents/` layout inside *other* projects. Nothing here runs as a long-lived service.

**Scaffolder source ≠ scaffolded project.** The hooks and scripts under `.agents/` here are development infrastructure *for this repo*. A project produced by running `project-init` (the output) gets a richer set of hooks from `templates/` — including `pre_commit_gate.sh` and git-level enforcement (gitleaks pre-commit secret scan, lifecycle pre-push gate; ADR-007) that are absent here. If you see a script or skill referenced in `templates/` that does not exist under `.agents/` in this repo, that is expected.

This is the canonical instruction file for agents working in this repository. [AGENTS.md](AGENTS.md) intentionally redirects here to avoid duplicated rules.

Use [README.md](README.md) for user-facing behavior.

Before doing any GitHub issue, branch, push, PR, review, CI, or merge work, read [.github/copilot-instructions.md](.github/copilot-instructions.md). Those instructions are mandatory for GitHub workflow details, including PR titles, PR bodies, board behavior, and lifecycle scripts.

## Layout

```
├── pyproject.toml          # uv-managed; core dep = rich; dev = ruff + pytest
├── install.sh              # user-facing bootstrap (curl | bash)
├── src/project_init/       # wizard CLI + scaffold engine
├── plugins/                # synced plugin payloads (tools/sync_plugin.py; ADR-010)
├── tools/                  # sync_plugin.py, third-party update checker, benchmark
├── templates/
│   ├── base/               # always copied into target projects
│   ├── auto/               # agent memory files (memory tiers auto and higher)
│   ├── fallback/           # shared hooks/skills — rendered only with --no-plugin (ADR-010)
│   ├── lifecycle/          # GitHub lifecycle enforcement (default; --lifecycle none opts out)
│   ├── lifecycle_fallback/ # lifecycle guard hooks + skills for --no-plugin
│   ├── obsidian/           # vault overlay for both Obsidian-* presets
│   ├── graphify/           # Graphify overlay (implies obsidian)
│   ├── rag/                # tier-3 RAG memory overlay
│   ├── multi_model/        # CCR model-switching overlay (--multi-model)
│   ├── governance/         # AI governance overlay (--governance)
│   ├── observability/      # transcript metrics overlay (--observability)
│   ├── codex/ antigravity/ amp/ junie/  # per-surface wiring overlays (--agents)
│   └── presets/            # toml preset definitions
└── tests/                  # focused pytest modules by behavior area (unit/contract/integration/smoke)
```

Template naming convention: directories stored as `dot_agents/`, `dot_gitignore` etc. The scaffolder renames them to `.agents/`, `.gitignore` on copy. This keeps templates visible in GitHub and avoids this repo being auto-loaded as a Claude Code config for itself.

## Conventions for agents working on this repo

- **Python only when needed** — the scaffolder must stay small. Don't reach for pyyaml / pydantic / click; `tomllib` and `argparse` cover most needs.
- **Deterministic** — copy/render logic is pure file ops; never call an LLM from the scaffolder itself.
- **uv everywhere** — `uv run …`, never `pip install` or `python -m venv`.
- **ruff only** — no black / isort / mypy.
- **justfile is the command surface** — `just --list` shows the canonical recipes (`setup`, `lint`, `format`, `test`, `test-quick`, `docs`, `ci`); prefer `just <recipe>` over raw tool invocations. Recipes stay thin wrappers — no logic in the justfile.
- **Templates are tested by scaffolding into a temp dir** — any change to `templates/` should have a corresponding test in the focused `tests/test_*.py` module for that behavior. Create a new focused file if no existing module fits.
- **Self-explaining wizard (ADR-023)** — every *selectable concern* the wizard offers must explain its value before asking (a `rich.Panel` with what·`Helps:`·cost·default, or an annotated `name — description` option list). When you add an optional concern, add its chooser, a `WIZARD_CONCERN_FLAGS` entry, and `--help`/README copy — `test_wizard_explanations.py` partitions every CLI flag into concern-with-explainer or mechanical and fails if a new flag is unclassified.
- **Keep tool output out of context (token-efficiency; PI-641)** — filter *before* text enters the transcript, because every tool result is re-sent on each subsequent turn. While iterating, use `just test-quick` (fail-fast, quiet) not `just test`; pipe noisy commands (`… 2>&1 | tail -n 40`, `grep FAILED`); read line ranges not whole files; delegate broad searches to the `Explore` agent so file dumps stay in the subagent and only the conclusion returns. Run the full `just test` once for the final green check.

## Settings

`.agents/settings.json` wires deterministic hooks to Claude Code events. Active hooks in this repo:

| Event | Script | Purpose |
|---|---|---|
| PreToolUse(Bash) | `github_command_guard.sh` | Thin shim → `dag_workflow.py guard`. Blocks `git push main`, `gh pr merge`, `gh api .../merge`, `gh pr ready/create`, `gh pr checks --watch`, raw `git push`. |
| UserPromptSubmit | `workflow_state_reminder.sh` | Injects the full lifecycle DAG, banned-command → wrapper-script map, and naming rules into context when a workflow keyword is mentioned. |
| (library) | `dag_workflow.py` | Stdlib DAG state machine. `check <node>` walks prerequisites for lifecycle scripts; `guard` is the hook entrypoint. Adding a banned command means editing `COMMAND_RULES` there, not the shell shim. |

`.agents/settings.local.json` pre-approves tool calls for development work (Bash, WebFetch, test paths). It is a convenience file — not a security boundary. Entries are auto-added by Claude Code when you approve a prompt; stale entries can be removed safely.

`$CLAUDE_PROJECT_DIR` in hook commands expands to the project root at runtime. To add a new hook, use the `add_hook` skill or edit `settings.json` directly following the existing pattern.

**`.claude/` is a generated mirror — edit `.agents/`, never `.claude/`.** Claude Code reads project config (settings.json, hooks, skills, commands) from `.claude/` only; it does *not* read a top-level `.agents/` natively (verified empirically against the CLI). This repo authors everything under `.agents/`, so `.claude/` is a committed, delete-aware mirror of the committed `.agents/` entries (`settings.json`, `hooks/`, `scripts/`, `skills/`) — that's what actually makes the repo's own guard hooks and skills load in a Claude session. It's a copy, not a symlink, because git's default `core.symlinks=false` on macOS and Windows would check a committed symlink out as a plain text file and silently hide the config. After editing anything under `.agents/`, run `just sync-claude` (also run by `just setup`); `tests/contracts/test_claude_dir_sync.py` fails CI if the mirror drifts. Scaffolded projects get the same mirror via `_generate_claude_projection`.

## GitHub workflow

For any push, PR, review, or merge work: load `.agents/skills/github_workflow/SKILL.md`.

Quick ref: branch = `<type>/PI-<n>-<slug>` | PR title = `type(PI-N): desc` (no scope = no issue) | body includes `Closes #N`.

Root `.agents/scripts/` lifecycle scripts exist here but may not cover every variant — they are scaffolded-project artifacts. If a script is missing, the skill documents the `git`/`gh` fallback.

Template skills (in `templates/base/dot_agents/skills/`) reference scripts like `create_issue.sh` and `start_issue.sh` that live in scaffolded projects, not in this source repo. The source `.agents/skills/INDEX.md` documents what's available here.

## Reference (on demand)

CI optimization strategies, the extend-the-infrastructure table (skill vs
hook vs agent spec), and this repo's non-goals live in
[`.agents/docs/guides/repo-reference.md`](.agents/docs/guides/repo-reference.md)
— consult when adding capabilities or tuning CI, not needed per turn.
