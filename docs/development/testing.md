# Testing

## Running tests

```bash
uv run pytest           # all tests
uv run pytest -k foo    # filter by name
uv run pytest --tb=short -q  # CI-style output
```

## Test structure

`tests/test_scaffold.py` contains all tests. They scaffold into `tmp_path` (pytest fixture) and inspect the output files.

## Key test classes

| Class | What it covers |
|---|---|
| `TestScaffoldBasic` | All presets scaffold without errors |
| `TestScaffoldIntegrity` | No unrendered `{{...}}` placeholders in output |
| `TestScaffoldIdempotency` | Re-run preserves memory/vault content |
| `TestNonInteractiveArgs` | CLI arg validation happens before target dir creation |
| `TestInstalledWheel` | Wheel installs and runs scaffold end-to-end |

## Adding tests for template changes

Any change to `templates/` must have a corresponding test:

```python
def test_my_new_file_exists(tmp_path):
    scaffold(tmp_path, load_preset("obsidian-only"), variables={...})
    assert (tmp_path / ".claude/my-new-file.md").exists()
```

## CI

GitHub Actions runs `uv run pytest --tb=short -q` on every PR. The wheel smoke test also validates that packaged templates are accessible after installation.
