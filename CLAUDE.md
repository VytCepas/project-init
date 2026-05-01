# project-init — agent notes

This repo is a **scaffolder**. It produces a `.claude/` layout inside *other* projects. Nothing here runs as a long-lived service.

**Scaffolder source ≠ scaffolded project.** The hooks and scripts under `.claude/` here are development infrastructure *for this repo*. A project produced by running `project-init` (the output) gets a richer set of hooks from `templates/` — including safety hooks like `secret-guard`, `bash-safety-guard`, and `pre-commit-gate` that are absent here. If you see a script or skill referenced in `templates/` that does not exist under `.claude/` in this repo, that is expected.

This is the canonical instruction file for agents working in this repository. [AGENTS.md](AGENTS.md) and [GEMINI.md](GEMINI.md) intentionally redirect here to avoid duplicated rules.

Use [README.md](README.md) for user-facing behavior.

Before doing any GitHub issue, branch, push, PR, review, CI, or merge work, read [.github/copilot-instructions.md](.github/copilot-instructions.md). Those instructions are mandatory for GitHub workflow details, including PR titles, PR bodies, board behavior, and lifecycle scripts.

## Layout

```
├── pyproject.toml          # uv-managed; core dep = rich; dev = ruff + pytest
├── install.sh              # user-facing bootstrap (curl | bash)
├── src/project_init/       # wizard CLI + scaffold engine
├── templates/
│   ├── base/               # always copied into target projects
│   ├── obsidian/           # overlay for both Obsidian-* presets
│   ├── lightrag/           # overlay for Obsidian+LightRAG preset
│   └── presets/            # toml preset definitions
└── tests/                  # focused pytest modules by behavior area
```

Template naming convention: directories stored as `dot_claude/`, `dot_gitignore` etc. The scaffolder renames them to `.claude/`, `.gitignore` on copy. This keeps templates visible in GitHub and avoids this repo being auto-loaded as a Claude Code config for itself.

## Conventions for agents working on this repo

- **Python only when needed** — the scaffolder must stay small. Don't reach for pyyaml / pydantic / click; `tomllib` and `argparse` cover most needs.
- **Deterministic** — copy/render logic is pure file ops; never call an LLM from the scaffolder itself.
- **uv everywhere** — `uv run …`, never `pip install` or `python -m venv`.
- **ruff only** — no black / isort / mypy.
- **Templates are tested by scaffolding into a temp dir** — any change to `templates/` should have a corresponding test in the focused `tests/test_*.py` module for that behavior. Create a new focused file if no existing module fits.

## Settings

`.claude/settings.json` wires deterministic hooks to Claude Code events. Active hooks in this repo:

| Event | Script | Purpose |
|---|---|---|
| PreToolUse(Bash) | `github-command-guard.sh` | Steers toward lifecycle scripts; blocks raw `git push main`, `gh pr merge` |
| PreToolUse(Bash) | `pre-merge-ci-check.sh` | Blocks merge if CI is pending or failing |
| UserPromptSubmit | `workflow-state-reminder.sh` | Injects workflow context when GitHub actions are mentioned |

`.claude/settings.local.json` pre-approves tool calls for development work (Bash, WebFetch, test paths). It is a convenience file — not a security boundary. Entries are auto-added by Claude Code when you approve a prompt; stale entries can be removed safely.

`$CLAUDE_PROJECT_DIR` in hook commands expands to the project root at runtime. To add a new hook, use the `add-hook` skill or edit `settings.json` directly following the existing pattern.

## GitHub workflow

For any push, PR, review, or merge work: load `.claude/skills/github-workflow/SKILL.md`.

Quick ref: branch = `<type>/PI-<n>-<slug>` | PR title = `[PI-N][type] desc` | body includes `Closes #N`.

Root `.claude/scripts/` lifecycle scripts exist here but may not cover every variant — they are scaffolded-project artifacts. If a script is missing, the skill documents the `git`/`gh` fallback.

Template skills (in `templates/base/dot_claude/skills/`) reference scripts like `create-issue.sh` and `start-issue.sh` that live in scaffolded projects, not in this source repo. The source `.claude/skills/INDEX.md` documents what's available here.

## CI Optimizations

This repo uses three strategies to reduce CI time and token usage:

1. **Test Parallelization** — Tests run with `pytest -n auto` via pytest-xdist. Cuts test time ~30-50% on multi-core runners.
2. **Split Heavyweight Tests** — `wheel-smoke` job only runs after `lint-and-test` succeeds, enabling fast feedback.
3. **Job Dependencies** — Integration/smoke tests are separate jobs that only run when main lint passes, avoiding wasted cycles on failures.

Scaffolded projects get a `ci.yml.tmpl` template with these patterns built in. See the comments in that file for how to customize conditional paths (skip docs-only changes, etc.)

## Extending the agent infrastructure

Use this table when adding new capabilities to this repo or its templates:

| You want to… | Add a… | Where |
|---|---|---|
| Automate a repeatable multi-step workflow | **Skill** (`SKILL.md` with frontmatter) | `.claude/skills/<name>/SKILL.md` — register in `INDEX.md` |
| Enforce a rule on every tool call or commit | **Hook** (bash/python script) | `.claude/hooks/` — wire in `settings.json`. Use the `add-hook` skill. |
| Expose a shortcut as `/command` | **Command** (markdown file) | `.claude/commands/<name>.md`. Use the `add-command` skill. |
| Add a reusable sub-agent persona | **Agent spec** | `.claude/agents/<name>.md` |

After creating a skill, add an entry to `.claude/skills/INDEX.md` so it is discoverable without reading every file.

## What this repo does NOT include

- No LLM calls from the scaffolder itself
- No long-running service
- No database (beyond what preset projects may install)
- Memory ingestion ships as scripts inside the LightRAG overlay
  (`templates/lightrag/dot_claude/scripts/`) — they run inside scaffolded
  projects, not as part of this repo's runtime.
