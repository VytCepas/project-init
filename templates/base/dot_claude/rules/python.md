---
description: Python environment, tooling, and test conventions
globs: ["**/*.py", "pyproject.toml", "uv.lock"]
alwaysApply: false
---

## Python environment

Uses [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                           # install deps
uv run <command>                  # run in the project venv
uv run ruff check .               # lint
uv run ruff format .              # format
uv run --with "mypy>=1.10" mypy src/  # type check (strict mode, per mypy.ini)
uv run pytest -n auto -q          # tests (parallel mode, requires pytest-xdist)
uv run pytest -q --tb=short       # tests (single-threaded fallback)
just test-cov                     # tests + coverage gate (>= 70%, per justfile) — CI always runs this
just audit                        # dependency CVE/advisory scan (pip-audit) — CI always runs this
```

ruff lints; it does not type-check. `just typecheck` (mypy, strict) is a separate
gate — type errors do not surface as ruff findings.

ruff's `select` also covers `RUF`/`PERF`/`PTH`/`RET`/`ARG`/`A`/`S` — Ruff-native
rules, perf anti-patterns, pathlib-over-os.path, return-statement clarity,
unused arguments, builtin shadowing, and bandit-derived security checks
(cheap and instant; complements Semgrep's CI-only SAST rather than
duplicating it). `S` is exempted under `tests/**` — plain `assert` is the
point of a test, not a vulnerability.

**Test Optimization**: Use `pytest -n auto` in CI to parallelize tests across CPU cores (30-50% faster). Requires `pytest-xdist` in dev dependencies. See `ci.yml.tmpl` for a full optimized CI config.

## Test conventions

- One assertion per test; name: `test_<unit>_<scenario>`
- External services (DB, API) use a real instance, not a mock
