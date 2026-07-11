# justfile — canonical command interface for this repo (PI-139 dogfood).
# `just --list` shows every recipe. Recipes are thin wrappers — logic lives
# in the tools and their configs, never in this file.

# install/sync dev dependencies + enable the local pre-push gate (dogfood).
# core.hooksPath points git at .githooks/, so `just fast-ci` runs before every push.
[doc("install/sync dev dependencies + enable the local pre-push gate (dogfood).")]
setup:
    uv sync --group dev
    git config core.hooksPath .githooks
    uv run python tools/sync_claude_dir.py

# lint + format check (docstring + complexity gates per pyproject.toml). The
# format check dogfoods the gate the template's python scaffold ships (PI-772),
# so `ruff format .` is now the expected fix — no longer a footgun.
[doc("lint + format check (docstring + complexity gates per pyproject.toml)")]
lint:
    uv run ruff check .
    uv run ruff format --check .

# auto-format
format:
    uv run ruff format .

# static type-check src/ under mypy --strict (config in mypy.ini; #639). mypy is
# pulled in ephemerally via `uv run --with`, mirroring the scaffolded
# justfile.tmpl — no dev-dependency to forget. ruff lints; it does not type-check.
[doc("static type-check src/ under mypy --strict (config in mypy.ini; #639)")]
typecheck:
    uv run --with "mypy>=1.10" --with pip mypy --install-types --non-interactive src/

# Parallel locally for dev-loop speed (~halves wall-clock). CI runs this suite
# SERIALLY on purpose — a rare cross-test interference surfaces under parallel
# scheduling (PI-762); a local flake is low-stakes (re-run), but CI must stay
# deterministic. Remove `-n auto` here too if a local flake ever bites.
# run the test suite in parallel (xdist)
[doc("Parallel locally for dev-loop speed (~halves wall-clock)")]
test:
    uv run pytest -n auto --tb=short -q

# Coverage (#636) is drift visibility, no floor. Kept off `just test` so the
# default loop stays fast; CI runs this one (serially — see `test`).
# run the test suite with a coverage report
[doc("Coverage (#636) is drift visibility, no floor")]
test-cov:
    uv run pytest --tb=short -q --cov --cov-report=term-missing

# fast iterate loop — stop at first failure, minimal output. Use while
# debugging to keep test noise out of agent context; run `just test` for the
# final full green check. (token-efficiency; see PI-641)
[doc("fast iterate loop")]
test-quick:
    uv run pytest -x -q --tb=short

# serve the docs site locally
docs:
    uv run --extra docs mkdocs serve

# scan dependencies for known CVEs (#637). pip-audit is pulled in ephemerally
# via `uv run --with`, mirroring the pattern the scaffolded ci.yml.tmpl ships —
# no dev-dependency to forget. Complements gitleaks (which scans for secrets,
# not vulnerable-but-correctly-spelled deps already in the lockfile).
#
# --all-extras is load-bearing: pip-audit scans the *installed* environment, and
# the advisories this recipe first caught (idna/urllib3) live in the `docs`
# extra (mkdocs-material -> requests), which is a real CI path (docs.yml) but is
# NOT synced by `lint-and-test`'s `uv sync --group dev`. Without --all-extras the
# gate would run in an env where those packages aren't even installed and report
# clean while a docs-extra CVE ships — a gate that can't fire (#637 review).
[doc("scan dependencies for known CVEs (#637)")]
audit:
    uv run --all-extras --with pip-audit pip-audit

# dependency license compliance scan (#579) — fail on copyleft (GPL/AGPL; also
# LGPL, since --partial-match is substring-based). Advisory in CI (not in
# ci-gate), matching the template's rollout. Mirrors the scaffolded `just license`.
[doc("dependency license compliance scan (#579)")]
license:
    uv run --with pip-licenses pip-licenses --from=mixed --fail-on "GPL;AGPL" --partial-match

# what CI runs (the full gate)
ci: lint typecheck test audit

# Deliberately lighter than `ci` — no typecheck/audit here; CI is the full
# backstop, so we don't re-run the whole gate before every push (PI-759). Keeps
# the push→CI loop fast while still catching the common break (a failing test).
# fast local gate for the pre-push hook: lint + parallel tests
[doc("fast local gate for the pre-push hook: lint + parallel tests")]
fast-ci: lint test

# sync the plugin payload from templates (PI-129)
sync-plugin:
    uv run python tools/sync_plugin.py

# regenerate this repo's own .claude/ mirror from .agents/ (dogfood; PI-627).
# Claude Code reads .claude/ only, so this is what makes the repo's own guard
# hooks and skills load. Run after editing anything under .agents/.
[doc("regenerate this repo's own .claude/ mirror from .agents/ (dogfood; PI-627).")]
sync-claude:
    uv run python tools/sync_claude_dir.py

# semi-scaffold: sync this repo's own .agents/ shared set from templates/
# (dogfood; PI-685). Run after template changes to shared files, then
# `just sync-claude`. CI enforces via tests/contracts/test_agents_template_sync.py.
[doc("sync this repo's own .agents/ shared set from templates/ (semi-scaffold; PI-685)")]
sync-agents:
    uv run python tools/sync_agents_from_templates.py

# regenerate .agents/docs/CODE_MAP.md — the low-token "what does what" index
# agents read before grepping (PI-685 dogfood). Run after public-API changes.
[doc("regenerate .agents/docs/CODE_MAP.md")]
code-map:
    uv run python .agents/scripts/gen_code_map.py
    uv run python tools/sync_claude_dir.py

# advisory: show drift between personal ~/.claude/skills copies and their
# template source (PI-681). Not a gate — the personal dir is outside VCS.
[doc("show drift between personal ~/.claude/skills copies and their template source (advisory)")]
skill-drift:
    uv run python tools/skill_drift.py
