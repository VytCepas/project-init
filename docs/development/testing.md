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

Tests live in `tests/<family>/<tier>/test_<aspect>.py` (harbor naming standard): the family is the
function under test, the tier is the kind of test. Tiers are auto-marked in `tests/conftest.py`.

## Suite layout

| Tier directory | Marker | Purpose |
|---|---|---|
| `tests/<family>/unit/` | `unit` | Small checks for preset parsing, MCP formatting, and direct render behavior. |
| `tests/<family>/contracts/` | `contract` | Scaffolded file layout, template content, strict rendering, and agent instruction contracts. |
| `tests/<family>/integration/` | `integration` | CLI calls, scaffolded hooks/scripts, git-backed memory linting, and fake-`gh` workflow behavior. |
| `tests/<family>/smoke/` | `smoke` | Installed wheel/package smoke tests. |


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

- Pure helper or parser behavior: `tests/<family>/unit/`
- A promised scaffolded file, setting, or instruction: `tests/<family>/contracts/`
- A subprocess, hook, shell script, CLI, or git interaction: `tests/<family>/integration/`
- Build/install/package verification: `tests/<family>/smoke/`

Any change to `templates/` should have a corresponding contract or integration
test. Use integration coverage when a generated script can be run without real
network access by faking tools such as `gh`.

## CI

GitHub Actions runs the full suite with pytest. The wheel smoke test validates
that packaged templates are accessible after installation.
