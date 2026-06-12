# justfile — canonical command interface for this repo (PI-139 dogfood).
# `just --list` shows every recipe. Recipes are thin wrappers — logic lives
# in the tools and their configs, never in this file.

# install/sync dev dependencies
setup:
    uv sync --extra dev

# lint (docstring + complexity gates per pyproject.toml)
lint:
    uv run ruff check .

# auto-format
format:
    uv run ruff format .

# run the test suite
test:
    uv run pytest -n auto --tb=short -q

# serve the docs site locally
docs:
    uv run --extra docs mkdocs serve

# what CI runs
ci: lint test

# sync the plugin payload from templates (PI-129)
sync-plugin:
    uv run python tools/sync_plugin.py
