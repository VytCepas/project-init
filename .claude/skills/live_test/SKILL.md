---
name: live_test
description: Live E2E of the scaffolder — build+install the wheel, scaffold real mini-projects, and *use* them to surface bugs the pytest suite can't. Drives the real install path, exercises hooks/guards in the correct mode, walks the local git/PR lifecycle against a stubbed gh, and writes a severity-ranked REPORT.md.
when_to_use: Use when the user says "/live_test", "run the live E2E", "live-test the scaffolder", or wants to validate that scaffolded projects actually work end-to-end (not just that pytest passes).
argument-hint: "[--matrix=1,2,3] [--keep]"
allowed-tools: Bash Read Write Glob Grep
disable-model-invocation: true
effort: high
---

Run a live end-to-end test of the **project-init scaffolder**. Deterministic pytest
coverage (`tests/smoke/test_packaging.py`, the `wheel-smoke` CI job, ~70 contract tests)
already proves files land with the right exec bits. This command tests what those can't:
whether a **scaffolded project actually works in real use** — do its hooks fire, do
lifecycle scripts run, does `just ci` pass, would an agent landing in the project find
coherent instructions. It captures the manual 0.4.0 "external live test" (which found 13
real bugs, epics #440–444) as a repeatable procedure.

It builds the wheel once, installs it into a throwaway venv, scaffolds a representative
matrix of mini-projects, fans out **one isolated subagent per project** to exercise four
depths, and aggregates a timestamped severity-ranked `REPORT.md`. **No GitHub side effects,
no auto-issue-filing, no merge path.**

## Execution model (with fallback)

The default is a **parallel one-subagent-per-project fan-out** (general-purpose or Explore
subagent). If the subagent/Task tool is unavailable or refused, **fall back to a serial
single-agent loop** that runs the same per-project steps and writes the same `result.json`
files. The fan-out is an optimization, not a hard dependency.

Claude (the orchestrator) runs Steps 1–3 centrally, fans out Step 4, then runs Steps 5–6
after the barrier.

## Steps

Define the run root up front and print it before any fan-out:

```bash
RUNID="${1:-$(date +%s 2>/dev/null || echo run)}"   # arg wins; never rely on a clock for correctness
RUN="${SCRATCHPAD:-$(mktemp -d)}/live-test-$RUNID"
mkdir -p "$RUN"/{build,logs}
echo "RUN=$RUN"
```

### 1. Build once, isolated

From the repo root, gate on `uv` (mirror `has_uv_and_can_build()` in `tests/helpers.py`;
if `uv` is absent, print a clear skip message and stop — nothing else can run).

```bash
command -v uv >/dev/null || { echo "SKIP: uv not installed — cannot build wheel"; exit 0; }
uv build --wheel -o "$RUN/build"                 # single FRESH wheel — never dist/*.whl (can be stale)
uv venv "$RUN/venv"
uv pip install --python "$RUN/venv" "$RUN"/build/*.whl
PI="$RUN/venv/bin/project-init"                   # resolved installed binary
"$PI" --version
```

### 2. Build the stateful local GitHub stub

Create `"$RUN/stub-bin/gh"` — a **stateful** stub that logs every argv to a per-project log
and returns canned responses for every shape the *exercised* lifecycle scripts use. Clear
`GH_TOKEN`/`GITHUB_*` and prepend the stub dir to `PATH` so `gh` can **never** reach the real
API. Each subagent asserts `command -v gh` resolves to the stub before running anything.

**The stub command→response table is the source of truth — embed it, don't leave it to future
diligence.** Enumerated from `create_issue.sh`, `start_issue.sh`, `push_branch.sh` /
`promote_review.sh` (both shim to `dag_workflow.py`), and `monitor_pr.sh`:

| `gh` invocation | Canned response (stdout) |
|---|---|
| `gh repo view --json owner -q .owner.login` | `livetest-owner` |
| `gh repo view --json name -q .name` | `<project>` |
| `gh repo view --json nameWithOwner ...` | `livetest-owner/<project>` |
| `gh repo view --json url -q .url` | `https://example.invalid/livetest-owner/<project>` |
| `gh label list --search <n> --json name -q '.[].name'` | empty (label absent → caller creates it) |
| `gh label create <n> ...` | exit 0, no output |
| `gh issue create ...` | `https://example.invalid/.../issues/101` |
| `gh issue view <n> --json title -q '.title'` | `Stubbed issue <n>` |
| `gh api .../issues/<n> --jq '.node_id'` | `I_stubnode101` |
| `gh api graphql -f query=...` | `{"data":{}}` (project-board mutations no-op) |
| `gh pr create ...` | `https://example.invalid/.../pull/202` |
| `gh pr view <n> --json isDraft -q .isDraft` | `true` |
| `gh pr view <n> --json headRefName -q .headRefName` | the current branch name |
| `gh pr view <n> --json url -q .url` | `https://example.invalid/.../pull/202` |
| `gh pr view --json number,reviewDecision` | `{"number":202,"reviewDecision":""}` |
| `gh pr ready <n>` | exit 0, no output |
| anything else | log argv, exit 0, empty stdout |

A reference generator for the stub (the skill writes this file, then `chmod +x`):

```bash
cat > "$RUN/stub-bin/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >> "${GH_STUB_LOG:-/dev/null}"
proj="${GH_STUB_PROJECT:-proj}"; branch="$(git branch --show-current 2>/dev/null || echo main)"
case "$*" in
  "repo view --json owner"*)        echo "livetest-owner" ;;
  "repo view --json name"*)         echo "$proj" ;;
  "repo view --json nameWithOwner"*) echo "livetest-owner/$proj" ;;
  "repo view --json url"*)          echo "https://example.invalid/livetest-owner/$proj" ;;
  "label list"*)                    : ;;                         # empty → caller creates
  "label create"*)                  : ;;
  "issue create"*)                  echo "https://example.invalid/livetest-owner/$proj/issues/101" ;;
  "issue view"*"title"*)            echo "Stubbed issue" ;;
  "api graphql"*)                   echo '{"data":{}}' ;;
  "api"*"node_id"*)                 echo "I_stubnode101" ;;
  "pr create"*)                     echo "https://example.invalid/livetest-owner/$proj/pull/202" ;;
  "pr view"*"isDraft"*)             echo "true" ;;
  "pr view"*"headRefName"*)         echo "$branch" ;;
  "pr view"*"reviewDecision"*)      echo '{"number":202,"reviewDecision":""}' ;;
  "pr view"*"url"*)                 echo "https://example.invalid/livetest-owner/$proj/pull/202" ;;
  "pr ready"*)                      : ;;
  *)                                : ;;
esac
STUB
chmod +x "$RUN/stub-bin/gh"
```

Per subagent: `export GH_STUB_LOG="$RUN/<proj>/gh.log" GH_STUB_PROJECT="<proj>"`,
`export PATH="$RUN/stub-bin:$PATH"`, `unset GH_TOKEN GITHUB_TOKEN GITHUB_ACTIONS`.

**Validation boundary:** plugin-mode hook execution validates the **repo plugin payload**
(`plugins/project-init-workflow/hooks/*` from the source checkout); the installed wheel
validates **scaffolder/template installation**. Keep these distinct in findings so a
plugin-source drift isn't reported as a wheel-install failure.

### 3. Scaffold the matrix (default ~5, representative — each hits a distinct path)

All non-interactive, `--non-interactive --strict --name <n> --description <d>`. `--matrix=`
selects a subset by number.

1. `--preset obsidian-only --language python` (**plugin mode** — designate this the
   plugin-mode hook-resolution project; see depth 2)
2. `--preset obsidian-graphify --language node --no-plugin`
3. `--preset governed --language python --governance --observability`
4. `--preset obsidian-only --language go --delivery service --deploy cloud-run --iac opentofu`
5. `--preset obsidian-only --language python --agents claude,codex,cursor,antigravity --multi-model --mcps context7 --browser`

**+ 1 interactive smoke:** drive the *full* wizard prompt sequence via piped stdin (the real
sequence in `main()` / the interactive gather path — **not** the leaf helpers in
`test_interactive_prompts.py`, which don't cover the full flow). Feed Enter-defaults; a
prompt-order mismatch is a **finding**, not a crash.

```bash
"$PI" --non-interactive --strict --preset obsidian-only --language python \
      --name lt1 --description "live-test project 1" "$RUN/proj1"
```

### 4. Fan out — one isolated subagent per mini-project

Each subagent gets: its project dir, its own `PATH` with the stub `gh` + per-project
`GH_STUB_LOG`, its own **local bare remote**, and **must write `"$RUN/<proj>/result.json"`**.
It first asserts `command -v gh` resolves to the stub. **Wrap every external command in an
explicit `timeout`**; a timeout is a finding with captured stdout/stderr paths.

**Shared per-project git bootstrap — run ONCE before both the gate and lifecycle depths,
idempotently:** `git init`, an initial `main` commit, `git init --bare "$RUN/<proj>.git"`
added as `origin`. Both `just scan` (needs a repo + staged content) and the lifecycle walk
reuse this single bootstrap. `push_branch.sh`'s real `git push -u origin` then succeeds
offline against the bare remote.

`result.json` schema (fixed):

```json
{
  "project": "proj1",
  "depths": {
    "gates":     {"status": "pass|fail|skipped", "note": ""},
    "hooks":     {"status": "pass|fail|skipped", "note": ""},
    "lifecycle": {"status": "pass|fail|skipped", "note": ""},
    "read":      {"status": "pass|fail|skipped", "note": ""}
  },
  "findings": [
    {"severity": "P1|P2|P3", "what": "", "repro": "", "suspected_file": "", "fix_sketch": ""}
  ]
}
```

The four depths:

- **Run scaffolded gates.** `cd` in; **preflight each tool** (`just`, `uv`/`bun`/`go`/
  `golangci-lint`, `gitleaks`). A missing tool ⇒ `status:skipped` "not exercised: missing X",
  **distinct from fail**. Then `just ci` (lint+test). For `just scan`: reuse the bootstrap
  repo and stage a harmless file first (the recipe runs `gitleaks git --pre-commit --staged`,
  meaningless without a repo + staged content); no-git/no-staged ⇒ skipped, not fail.
  `just ci` for node/go *may* fetch deps — allowed (matches a real user); a **network failure
  is reported distinctly**, not as scaffold breakage.
- **Exercise hooks & guards — in the correct mode:**
  - *Plugin-mode project (#1):* the **event-wired** guard hooks
    (`github_command_guard.sh`, `pre_commit_gate.sh`, `session_setup.sh`,
    `workflow_state_reminder.sh`, `post_edit_lint.sh`) are supplied by the **plugin payload**
    — invoke `plugins/project-init-workflow/hooks/*` with `CLAUDE_PLUGIN_ROOT` +
    `CLAUDE_PROJECT_DIR` set. Note: the scaffolded project still carries a **reduced** local
    `.claude/hooks/` (`dag_workflow.py`, `prod_guard.py`, `_py.sh`) because the lifecycle
    scripts shim to `../hooks/dag_workflow.py` and `enabledPlugins` lists
    `project-init-workflow@project-init` — the same hook *set* fires in both modes
    (`capabilities.py`), plugin mode just sources the wired ones from the plugin. Specifically
    verify scripts-dir/redirect resolution honors `$CLAUDE_PROJECT_DIR` — **the exact 0.4.0
    P1.** First-class depth.
  - *`--no-plugin` project (#2):* invoke the scaffolded `.claude/hooks/*`.
  - Feed banned commands and confirm **block**; feed allowed and confirm **pass**; run
    `pre_commit_gate.sh` with stdin JSON.
- **Walk the git/PR lifecycle (fully local, scoped).** Reuse the bootstrap repo + bare
  `origin`, run `install_hooks.sh`, make a commit (commit-msg + pre-commit fire), then run
  `create_issue.sh`, `start_issue.sh`, `push_branch.sh`, `promote_review.sh` against the stub.
  **Skip `finish_pr.sh`** — it chains into `dag_workflow.py finish` → `monitor_pr.sh --merge`,
  which carries CI/review/merge assumptions a stub can't honestly satisfy; note the merge path
  as "not exercised by design".
- **Read-as-an-agent sanity.** Read `AGENTS.md`/`CLAUDE.md`/`settings.json`/per-surface
  configs; judge whether instructions are coherent and non-contradictory.

### 5. Aggregate & report

After *all* subagents finish, read every `result.json` and write one timestamped
`"$RUN/REPORT.md"`: a summary table (project × depth × pass/fail/skipped) + severity-ranked
findings (what / repro / suspected file / fix sketch). **No auto-filing of GitHub issues.**

### 6. Cleanup

**Always preserve `REPORT.md`.** Before deleting any *passing* project dir, copy its
per-project logs (subagent stdout/stderr, `gh.log`, timeout artifacts) into
`"$RUN/logs/<project>/"` so audit trails survive even for clean passes. Then delete only the
*passing* project dirs; preserve any failing project dir whole. `--keep` preserves everything.
Print all preserved paths.

## Rules

- **No network/GitHub side effects.** `gh` is stubbed; `GH_TOKEN`/`GITHUB_*` cleared; the only
  remote is a local bare repo. Never run the real merge path.
- **`skipped` ≠ `fail`.** A missing host tool (`just`, `go`, `gitleaks`, `golangci-lint`) is a
  skip with a reason, never a failure.
- **Single fresh wheel** from an isolated `-o` build dir — never `dist/*.whl`.
- **Timeout-wrap every external command;** a timeout is a finding.
- **Mode-aware hooks:** plugin project → repo plugin payload; `--no-plugin` project →
  scaffolded `.claude/hooks/*`. Don't cross-report.
- **Deterministic-clock-free:** never depend on `date`/`Date.now()` for correctness; the runid
  is a label, passed in or best-effort.
- This skill is **source-only** — it lives under this repo's `.claude/skills/`, is **not** in
  `templates/fallback/` and **not** part of `tools/sync_plugin.py`. It tests the scaffolder; it
  is not shipped into scaffolded output.
