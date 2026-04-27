# Codex Review — project-init

## What is Good

- The runtime dependency surface is appropriately small: `pyproject.toml:15-17` keeps production dependencies to `rich`, and `pyproject.toml:19-23` confines `ruff` and `pytest` to dev extras.
- The architecture has a clean split between CLI interaction and deterministic scaffolding: `src/project_init/__main__.py:207-294` gathers inputs, while `src/project_init/scaffold.py:80-124` performs copy/render work without prompts or network calls.
- Template packaging is handled deliberately: `pyproject.toml:31-35` force-includes `templates/` into the wheel, and `src/project_init/scaffold.py:10-14` has a dev-mode fallback for running from the checkout.
- Presets are simple, layered, and easy to reason about: `templates/presets/obsidian-only.toml:4-10` and `templates/presets/obsidian-lightrag.toml:4-13` make the base/overlay structure explicit.
- MCP commands are centralized in one catalog (`src/project_init/mcps.py:10-56`), with tests enforcing the bun-only convention (`tests/test_scaffold.py:584-603`).
- The idempotency rule is encoded in one place (`src/project_init/scaffold.py:23-27`, `src/project_init/scaffold.py:69-77`) and covered by tests for memory/vault preservation and config refresh (`tests/test_scaffold.py:249-288`).
- Verification is currently green when `uv` can write its cache: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` passed, and `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` reported 88 passed and 4 skipped.

## What is Bad

1. Executable shell scripts are stored with CRLF line endings, so direct execution fails on Unix with `/usr/bin/env: 'bash\r': No such file or directory`. This affects `install.sh:1`, `templates/base/dot_claude/hooks/bash-safety-guard.sh:1`, `templates/base/dot_claude/hooks/post-edit-lint.sh:1`, `templates/base/dot_claude/hooks/pre-commit-gate.sh:1`, and `templates/obsidian/dot_claude/hooks/session-end.sh:1`; generated settings invoke those hook files directly at `templates/obsidian/dot_claude/settings.json.tmpl:20`, `templates/obsidian/dot_claude/settings.json.tmpl:25`, `templates/obsidian/dot_claude/settings.json.tmpl:37`, and `templates/obsidian/dot_claude/settings.json.tmpl:49`.

2. `secret-guard.py` leaks part of the secret it just detected. `templates/base/dot_claude/hooks/secret-guard.py:98` includes `match.group()[:40]` in the finding text, and `templates/base/dot_claude/hooks/secret-guard.py:140-148` emits that text to the hook response. For shorter secrets such as AWS access key IDs, this can expose the full matched value.

3. One command template ships an unresolved placeholder because it is not named `.tmpl`. `templates/base/dot_claude/commands/plan.md:50` contains `{{python_linter}}`, but the renderer only processes files ending in `.tmpl` (`src/project_init/scaffold.py:101-114`), so scaffolded projects get the literal placeholder in `/plan`.

4. Non-Python projects get invalid lint guidance. `src/project_init/__main__.py:282` sets `python_linter` to `none` outside Python projects, but `templates/base/CLAUDE.md.tmpl:21` and `templates/base/dot_claude/project-init.md.tmpl:50` still render `none check .` as a command.

5. Generated docs contain broken internal references. `templates/base/dot_claude/memory/MEMORY.md.tmpl:9` links to `project_overview.md`, but no template creates that file. `templates/base/dot_claude/project-init.md.tmpl:123-125` points users to `scripts/mcp-manage.sh`, but no such script exists under `templates/`.

6. `config.yaml` rendering is not YAML-safe for user input. `templates/base/dot_claude/config.yaml.tmpl:5-6` writes `project_name` and `project_description` unquoted, while the CLI accepts arbitrary strings through flags (`src/project_init/__main__.py:33-34`) and prompts (`src/project_init/__main__.py:250-251`). A colon, hash, quote, or newline can create invalid YAML or change the parsed structure.

7. The generated hook enforcement can silently do nothing on common setups. The Bash hooks exit successfully when `jq` is missing (`templates/base/dot_claude/hooks/bash-safety-guard.sh:9-13`, `templates/base/dot_claude/hooks/pre-commit-gate.sh:10-14`, `templates/base/dot_claude/hooks/post-edit-lint.sh:12-16`), and the lint hooks call bare `ruff` instead of `uv run ruff` (`templates/base/dot_claude/hooks/post-edit-lint.sh:25-29`, `templates/base/dot_claude/hooks/pre-commit-gate.sh:27-33`), so they may skip checks even when the project has ruff installed in its uv environment.

8. Session logs can overwrite each other. `templates/obsidian/dot_claude/hooks/session-end.sh:12-13` names logs only to the minute, and `templates/obsidian/dot_claude/hooks/session-end.sh:34` writes with `>`, so two Stop events in the same minute destroy the earlier log.

9. The LightRAG YAML config is effectively decorative. `templates/lightrag/dot_claude/memory/lightrag.yaml.tmpl:1-2` says the config is used by the scripts, but `templates/lightrag/dot_claude/scripts/ingest_sessions.py:30-69` and `templates/lightrag/dot_claude/scripts/query_memory.py:30-68` hard-code the working directory, provider functions, embedding dimension, and model wiring instead of reading the config.

10. The installer ignores custom install locations in the generated slash command. `install.sh:17` supports `PROJECT_INIT_HOME`, but the command written at `install.sh:56-63` hard-codes `$HOME/.local/share/project-init`; the printed shell usage at `install.sh:81` uses `$INSTALL_DIR`, so the installed Claude command and the displayed shell command can disagree.

11. The repository docs are stale relative to the implementation. `README.md:52-58` says the wizard asks for lint/test tooling, but `_build_parser` has no lint/test option (`src/project_init/__main__.py:32-60`). `README.md:91` says the MCP suggestion menu is next, while the CLI already implements MCP selection (`src/project_init/__main__.py:256-265`). `CLAUDE.md:31-36` says memory ingestion is not included, while LightRAG ingestion scripts exist at `templates/lightrag/dot_claude/scripts/ingest_sessions.py:1-86`.

## What is Improvable

1. Normalize all shell templates to LF and add a CI check that rejects CRLF in executable scripts. Effort: 0.25 day.

2. Add scaffold integrity tests per preset: assert no unresolved `{{...}}` placeholders remain, every relative markdown link points to a generated file or directory, and every documented script exists. This would catch `templates/base/dot_claude/commands/plan.md:50`, `templates/base/dot_claude/memory/MEMORY.md.tmpl:9`, and `templates/base/dot_claude/project-init.md.tmpl:123-125`. Effort: 1 day.

3. Make template rendering strict. Keep the tiny renderer if desired, but fail when unknown variables or unclosed conditionals remain after rendering (`src/project_init/scaffold.py:50-59`). Effort: 0.5 day.

4. Introduce explicit rendered command variables such as `lint_command`, `format_command`, and `test_command` instead of deriving docs from `python_linter` alone (`src/project_init/__main__.py:272-289`). Effort: 0.5 day.

5. Replace shell-hook JSON parsing with small Python helpers or inline Python so `jq` is not a hidden dependency. Also run Python lint through `uv run ruff` where a `pyproject.toml`/`uv.lock` exists. Effort: 1 day.

6. Make `config.yaml` safe by rendering YAML scalar values with a quoting helper or by writing JSON-compatible strings for user-provided values. This can stay dependency-free using `json.dumps` for scalars. Effort: 0.5 day.

7. Decide whether LightRAG should be configured by file or by code. If by file, switch to a stdlib-readable config format such as TOML or JSON and have both scripts load it; if by code, remove `lightrag.yaml.tmpl` and stop telling users to edit it. Effort: 1 day.

8. Improve non-interactive validation: validate the preset before creating the target directory (`src/project_init/__main__.py:224-234`), reject unknown MCP IDs instead of silently ignoring them (`src/project_init/__main__.py:150-153`), and de-duplicate repeated MCP IDs in the non-interactive path. Effort: 0.5 day.

9. Add an installed-wheel smoke test that builds the package, runs `project-init` from the wheel into a temp directory, and verifies packaged templates, executable bits, and preset discovery (`pyproject.toml:31-35`, `src/project_init/scaffold.py:10-14`). Effort: 0.5 day.

10. Reconcile `README.md`, `CLAUDE.md`, and generated templates after each feature ticket. The current drift around MCPs and LightRAG shows the docs need to be part of the same acceptance criteria as code changes. Effort: 0.25 day.

## Verdict

The project has a solid small-core architecture and the current Python test suite is green, but the generated artifact quality is weaker than the scaffolder engine itself. The highest-priority fixes are the CRLF executable breakage, secret redaction, unresolved/broken template references, and hook enforcement gaps; after those are addressed, the repo is a practical foundation for deterministic agent-project scaffolding.
