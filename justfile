# justfile — canonical command interface for this repo (PI-139 dogfood).
# `just --list` shows every recipe. Recipes are thin wrappers — logic lives
# in the tools and their configs, never in this file.

# install/sync dev dependencies + enable the local pre-push CI gate (dogfood).
# core.hooksPath points git at .githooks/, so `just ci` runs before every push.
setup:
    uv sync --group dev
    git config core.hooksPath .githooks
    uv run python tools/sync_claude_dir.py

# lint (docstring + complexity gates per pyproject.toml)
lint:
    uv run ruff check .

# auto-format
format:
    uv run ruff format .

# run the test suite
test:
    uv run pytest --tb=short -q

# fast iterate loop — stop at first failure, minimal output. Use while
# debugging to keep test noise out of agent context; run `just test` for the
# final full green check. (token-efficiency; see PI-641)
test-quick:
    uv run pytest -x -q --tb=short

# serve the docs site locally
docs:
    uv run --extra docs mkdocs serve

# what CI runs
ci: lint test

# sync the plugin payload from templates (PI-129)
sync-plugin:
    uv run python tools/sync_plugin.py

# regenerate this repo's own .claude/ mirror from .agents/ (dogfood; PI-627).
# Claude Code reads .claude/ only, so this is what makes the repo's own guard
# hooks and skills load. Run after editing anything under .agents/.
sync-claude:
    uv run python tools/sync_claude_dir.py

# semi-scaffold: sync this repo's own .agents/ shared set from templates/
# (dogfood; PI-685). Run after template changes to shared files, then
# `just sync-claude`. CI enforces via tests/contracts/test_agents_template_sync.py.
sync-agents:
    uv run python tools/sync_agents_from_templates.py

# regenerate .agents/docs/CODE_MAP.md — the low-token "what does what" index
# agents read before grepping (PI-685 dogfood). Run after public-API changes.
code-map:
    uv run python .agents/scripts/gen_code_map.py
    uv run python tools/sync_claude_dir.py
