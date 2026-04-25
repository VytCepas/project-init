# project-init — agent notes

This repo is a **scaffolder**. It produces a `.claude/` layout inside *other* projects. Nothing here runs as a long-lived service.

Start by reading [README.md](README.md) and [AGENTS.md](AGENTS.md). Issue tracking: Linear project "Project Init".

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
└── tests/
```

Template naming convention: directories stored as `dot_claude/`, `dot_gitignore` etc. The scaffolder renames them to `.claude/`, `.gitignore` on copy. This keeps templates visible in GitHub and avoids this repo being auto-loaded as a Claude Code config for itself.

## Linear ↔ GitHub

| Thing | Format | Effect |
|---|---|---|
| Branch | `<username>/pi-<N>-<slug>` — **copy from Linear** | Copying triggers "Started" status + self-assign |
| Commit | `PI-N: <what and why>` | Linear links the commit to the issue |
| PR title + body | `PI-N: <title>` + `Fixes PI-N` in body | Moves issue to Done on merge |

**Always get the branch name from Linear's "Copy git branch" button** — that action is what fires the "move to Started" and "assign to self" automations. Manually typed branch names that happen to match the format do not trigger them. For agents: if no branch name is provided, construct it as `<linear-username>/pi-<N>-<title-slug>` (lowercase, hyphens only).

## Conventions for agents working on this repo

- **Python only when needed** — the scaffolder must stay small. Don't reach for pyyaml / pydantic / click; `tomllib` and `argparse` cover most needs.
- **Deterministic** — copy/render logic is pure file ops; never call an LLM from the scaffolder itself.
- **uv everywhere** — `uv run …`, never `pip install` or `python -m venv`.
- **ruff only** — no black / isort / mypy.
- **Templates are tested by scaffolding into a temp dir** — any change to `templates/` should have a corresponding test that runs the wizard with a preset and diffs the output.
- **No duplicate tests** — before writing a new test, scan `tests/` for existing coverage of the same behaviour. If a happy-path case already exists, skip restating it and write edge-case / error-path tests instead (bad inputs, boundary values, missing files, conflicting flags, etc.).
- **Type-annotate everything** — all function signatures and class attributes must carry type hints using stdlib `typing` and built-in generics (`list[str]`, `dict[str, Path]`, etc.). Pydantic is excluded (would add a runtime dep); use `dataclasses` + annotations for structured data. Any JavaScript added to templates must be TypeScript with `"strict": true` in `tsconfig.json`.

## What this repo does NOT include

- No LLM calls from the scaffolder itself
- No long-running service
- No database (beyond what preset projects may install)
- Memory ingestion (PI-6) ships as scripts inside the LightRAG overlay
  (`templates/lightrag/dot_claude/scripts/`) — they run inside scaffolded
  projects, not as part of this repo's runtime.
