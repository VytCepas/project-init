# Contributing

## Setup

```bash
git clone https://github.com/VytCepas/project-init.git
cd project-init
uv sync --extra dev
```

## Workflow

1. `gh issue list` — pick or create an issue
2. Create a branch for the issue work using `PI-<issue-number>` in the name
3. Write failing tests first (TDD)
4. Implement until tests pass
5. `uv run ruff check . && uv run ruff format .` — lint and format
6. `uv run pytest` — all tests pass
7. Open a PR following `.github/copilot-instructions.md`

## PR checklist

- [ ] Title: `[PI-IssueNumber][type] description`
- [ ] Body includes `Closes #<number>`
- [ ] New template files have a corresponding test
- [ ] No unrendered `{{...}}` placeholders in template output
- [ ] `uv run ruff check .` passes
- [ ] `uv run pytest` passes

## Principles

- Keep the scaffolder small — no new dependencies unless unavoidable
- Deterministic — scaffold output must be identical for the same inputs
- No LLM calls from the scaffolder itself
- `uv` everywhere — never `pip install` or `python -m venv`
