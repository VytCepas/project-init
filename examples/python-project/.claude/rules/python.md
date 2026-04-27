---
description: Python environment, tooling, and test conventions
globs: ["**/*.py", "pyproject.toml", "uv.lock"]
alwaysApply: false
---

## Python environment

Uses [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                      # install deps
uv run <command>             # run in the project venv
uv run ruff check .          # lint
uv run ruff format .         # format
uv run pytest -q --tb=short  # tests
```

## Test conventions

- One assertion per test; name: `test_<unit>_<scenario>`
- External services (DB, API) use a real instance, not a mock
