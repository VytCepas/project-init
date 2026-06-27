# Contributing to project-init

Thanks for your interest! **project-init** is a scaffolder that drops a `.claude/`
agentic-development layout into other projects. Bug reports, ideas, docs fixes,
and pull requests are all welcome.

## Ways to contribute

- **Ask a question or float an idea** → [GitHub Discussions](https://github.com/VytCepas/project-init/discussions).
- **Report a bug or request a feature** → [open an Issue](https://github.com/VytCepas/project-init/issues/new/choose) using one of the templates.
- **Send a fix or improvement** → fork, branch, and open a pull request (see below).

## Development setup

This repo uses [`uv`](https://docs.astral.sh/uv/) and a `justfile` as the command surface.

```bash
git clone https://github.com/VytCepas/project-init.git
cd project-init
just setup          # uv sync + dev deps
just --list         # see all recipes
```

| Recipe | What it does |
|---|---|
| `just lint` | ruff check + format check (the gate hooks/CI enforce) |
| `just format` | ruff format |
| `just test` | full pytest suite (`pytest -n auto`) |
| `just docs` | build the MkDocs site |
| `just ci` | lint + test (run before pushing) |

Tooling conventions: **uv** for everything (never `pip`/`venv`), **ruff** only
(no black/isort/mypy), and keep dependencies minimal — `tomllib` + `argparse`
cover most needs. The scaffolder stays small and deterministic (no LLM calls).

## Making changes

1. **Fork** the repo and create a branch named `type/short-slug`
   (e.g. `fix/wizard-typo`, `feat/new-preset`). Types: `feat` `fix` `chore` `docs` `test`.
2. **Templates are tested by scaffolding into a temp dir** — any change under
   `templates/` should have a matching test in the focused `tests/test_*.py`
   module for that behavior. Create a new focused file if none fits.
3. **Run `just ci`** locally and make sure it's green.
4. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/)
   (`type: description`), then open a pull request.

## Pull requests

- Use a Conventional-Commits PR title: `type: description` (the title becomes the
  squash-merge commit message).
- Fill in the pull request template — describe *what* changed and *why*, and link
  any related issue with `Closes #N`.
- CI runs lint, the full test suite, a secret scan, and a wheel smoke test. All
  checks must pass before merge.

## License

By contributing you agree that your contributions are licensed under the
project's [Apache-2.0](LICENSE) license.
