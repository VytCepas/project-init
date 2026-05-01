# Testing

## Running tests

```bash
uv run pytest                  # all tests
uv run pytest -m unit           # fast pure-Python checks
uv run pytest -m contract       # scaffolded template contract checks
uv run pytest -m integration    # CLI, hook, and script behavior
uv run pytest -m smoke          # packaging smoke checks
uv run pytest --tb=short -q     # CI-style output
```

Tests are grouped by directory and auto-marked in `tests/conftest.py`.

## Suite layout

| Directory | Marker | Purpose |
|---|---|---|
| `tests/unit/` | `unit` | Small checks for preset parsing, MCP formatting, and direct render behavior. |
| `tests/contracts/` | `contract` | Scaffolded file layout, template content, strict rendering, and agent instruction contracts. |
| `tests/integration/` | `integration` | CLI calls, scaffolded hooks/scripts, git-backed memory linting, and fake-`gh` workflow behavior. |
| `tests/smoke/` | `smoke` | Installed wheel/package smoke tests. |

`optional_dependency` marks tests that need dependencies outside the default dev extra, such as `lightrag-hku`.

## What To Test

This repository is a scaffolder, so template contract tests are useful. A small
string or file-existence assertion is acceptable when it protects a documented
scaffold contract, such as a generated hook path or workflow setting.

Prefer behavior tests when the generated artifact has executable logic:

- run Python hooks/scripts with representative JSON or CLI inputs
- run shell scripts with fake commands on `PATH` when external services are involved
- scaffold into `tmp_path` and verify rerun/idempotency behavior
- keep one packaging smoke test that validates templates are included in the wheel

Avoid adding many independent tests that only assert adjacent strings in the
same file. Use one focused contract test for related content, or a behavior test
if the script can be executed cheaply.

## Adding Tests

Place new tests by intent, not by implementation file:

- Pure helper or parser behavior: `tests/unit/`
- A promised scaffolded file, setting, or instruction: `tests/contracts/`
- A subprocess, hook, shell script, CLI, or git interaction: `tests/integration/`
- Build/install/package verification: `tests/smoke/`

Any change to `templates/` should have a corresponding contract or integration
test. Use integration coverage when a generated script can be run without real
network access by faking tools such as `gh`.

## CI

GitHub Actions runs the full suite with pytest. The wheel smoke test validates
that packaged templates are accessible after installation.
