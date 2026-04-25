# Project: example-python

> Example scaffolded Python project

Scaffolded with [project-init](https://github.com/VytCepas/project-init) on 2026-04-25.

## Setup captured at init

- **Language/runtime**: python
- **Memory stack**: obsidian-only
- **Installed MCPs**: linear, github, context7

See [`config.yaml`](config.yaml) for the full record.

## Workflow

1. **Start of session** — agents should read [`memory/MEMORY.md`](memory/MEMORY.md) first, then glance at [`vault/`](vault/) for recent design/decision notes.
2. **During work** — append to memory when you learn something reusable (see [`memory/README.md`](memory/README.md) for the convention). Large docs go in [`vault/`](vault/), small facts in [`memory/`](memory/).
3. **End of session** — the `session-end` hook appends a session log to [`vault/sessions/`](vault/sessions/).

## Commands, skills, and agents

**Slash commands** (`.claude/commands/`):
- `/status` — project status: git state, recent commits, memory, open TODOs
- `/review [target]` — code review of staged changes, a commit range, or a file
- `/save-memory <fact>` — save a reusable fact to memory
- `/plan <task>` — write acceptance tests first, then implementation plan (TDD)

**Skills** (`.claude/skills/`):
- `session-summary` — summarize the session and save to vault
- `start-task` — create a Linear issue before starting non-trivial work

**Subagents** (`.claude/agents/`):
- `reviewer` — code review specialist (sonnet, focused on bugs + security)
- `researcher` — codebase explorer (sonnet, traces dependencies and architecture)

**Hooks** (`.claude/hooks/`, wired via `settings.json`):
- `bash-safety-guard.sh` — blocks destructive shell commands (rm -rf /, force push to main, DROP TABLE, etc.) before they run
- `pre-commit-gate.sh` — intercepts `git commit`, auto-fixes staged files, blocks commit if lint errors remain
- `post-edit-lint.sh` — auto-lints and formats files after Edit/Write/MultiEdit; injects errors into context so they get fixed in the same turn
- `session-end.sh` — appends a session log to `vault/sessions/` on Stop

## Coding standards

- **No comments** unless the WHY is non-obvious (a hidden constraint, a workaround for a specific bug). Never describe what the code does.
- **No premature abstractions** — three similar lines is better than an abstraction. Extract only when the pattern is stable.
- **No impossible error handling** — trust internal code and framework guarantees. Validate only at system boundaries (user input, external APIs).
- **No backwards-compatibility shims** — if something is removed, delete it completely.
- **Prefer editing existing files** over creating new ones.
- **Always lint before marking a task done** — `uv run ruff check .` must pass before closing a task.


## Test-driven development

**Write tests first.** Before implementing any function or feature, write the test that the implementation must pass. Tests define the contract; implementation fulfils it.

Workflow:
1. Use `/plan <task>` — it produces acceptance tests (red) before the implementation plan
2. Commit the failing tests
3. Implement until all tests pass (green)
4. Lint and clean up


Test conventions:
- One assertion per test
- Name: `test_<unit>_<scenario>` (e.g. `test_scaffold_renames_dot_prefix`)
- Run: `uv run pytest`
- A test that touches external services (DB, external API) must use a real instance, not a mock


## Linear task tracking

Before starting any non-trivial task:
1. Check whether a Linear issue already exists
2. If not, run `/start-task` to create one
3. Reference the issue ID in commit messages

> Every piece of meaningful work should be traceable to a Linear issue.

## Conventions

- **Deterministic first** — hooks and scripts in [`hooks/`](hooks/) and [`scripts/`](scripts/) prefer bash/python. LLM calls only for generative steps.
- **One folder for agentic infra** — everything lives under `.claude/`. Root only has `CLAUDE.md` / `AGENTS.md` redirects.
- **Markdown is canonical** — vault notes and memory files are plain markdown so they stay portable across agents.


## Python environment

This project uses [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                 # install deps
uv run <command>        # run in the project venv
uv run ruff check .     # lint
uv run ruff format .    # format
uv run pytest           # tests
```





## Reset or re-init

Re-run `/project-init` (or `project-init` from shell) in this project to re-select options. It will not overwrite existing memory or vault content.
