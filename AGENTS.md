# AGENTS.md

For agents working on the **project-init** codebase itself (not projects it scaffolds).

See [CLAUDE.md](CLAUDE.md) for repo-specific conventions and [README.md](README.md) for what this project does.

## Rules of the road

- Core runtime dep is `rich`. Stdlib (`tomllib`, `argparse`, `pathlib`, `subprocess`, `string.Template`) covers the rest. Don't add deps without a specific justification.
- `uv` for all Python ops: `uv sync`, `uv run ruff check .`, `uv run pytest`.
- Ruff only — no black, isort, or mypy.
- The scaffolder itself is deterministic: no LLM calls. LLM usage belongs inside scaffolded projects (e.g. the LightRAG overlay), never in the wizard.
- Templates under `templates/` use `dot_claude/` / `dot_gitignore` naming; the scaffolder renames to `.claude/` / `.gitignore` on copy.
- Placeholders in `*.tmpl` files use `{{variable_name}}` syntax.
- **Type-annotate everything** — every function signature and class attribute must carry type hints using stdlib `typing` and built-in generics (`list[str]`, `dict[str, Path]`, etc.). Pydantic is excluded (runtime dep); use `dataclasses` + annotations for structured data. Any JavaScript added to templates must be TypeScript with `"strict": true` in `tsconfig.json`.

## Testing templates

When adding or changing a template, add a test under `tests/` that runs the scaffolder with the relevant preset into a temp dir and diffs the output against an expected tree. Tests must run offline.

## Writing tests

Before adding any test, scan `tests/` to check whether the behaviour is already covered. If a happy-path case exists, do not restate it — write edge-case and error-path tests instead (invalid inputs, boundary values, missing files, conflicting CLI flags, permission errors, etc.). Duplicate tests waste CI time and obscure real coverage gaps.

## Linear

Work is tracked in the Linear project "Project Init" at <https://linear.app/vytautas-project/project/project-init-467fe1178d8a/overview>. Issue IDs in commit messages should reference the ticket (e.g. `PI-2:`).
