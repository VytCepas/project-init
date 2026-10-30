# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Each entry is generated from the GitHub release notes of its tag.

## [Unreleased]

## [1.2.2] - 2026-07-21

### Bug Fixes

- *(PI-882)* Bug: issue guard's --repo slug comparison ignores gh's optional host, letting same-repo creates bypass create_issue.sh (#883)
- *(PI-881)* Bug: PI-845 guard fix ships in project-init-lifecycle without a version bump — existing installs keep the stale hook (#884)
- *(PI-880)* Bug: `upgrade` does not splice new config.yaml blocks (`ci:`, `monitor_ignore_checks`) into existing scaffolds (#885)

### Miscellaneous Tasks

- Release 1.2.2 (#886)

## [1.2.1] - 2026-07-20

### Bug Fixes

- *(PI-869)* Multi-model overlay seeds CCR config to ~/.agents-code-router, a path CCR never reads (PI-606 rename regression) (#871)
- *(PI-872)* Observability overlay reads transcripts from ~/.agents/projects, but Claude Code writes ~/.claude/projects (PI-606 rename regression) (#875)
- *(PI-877)* Install.sh writes /project-init to ~/.agents/commands — Claude Code never loads it, so the advertised install produces a dead slash command (#878)

### Miscellaneous Tasks

- Release 1.2.1 (#879)

## [1.2.0] - 2026-07-17

### Bug Fixes

- *(PI-839)* Post_edit_lint.sh auto-fix races multi-edit sequences: strips imports added one edit before their usage (#841)
- *(PI-837)* Monitor_pr.sh deadlocks on a known-dead check (billing-locked GitHub-hosted job); check runs cross-contaminate sibling branches sharing a head commit (#851)
- *(PI-838)* Review gate cannot terminate on individual profile when the review agent never responds (#852)
- Rewrap reviewer-absent echo lines on sentence boundaries (#856)
- *(PI-854)* Test_register_ollama_model_without_pull does a real multi-GB ollama pull on hosts where ollama exists (#855)
- Bump project-init-workflow plugin to 0.8.1 (#857)
- *(PI-858)* Monitor_pr.sh CI wait can break on an ignored-only check rollup before real CI registers (#859)
- *(PI-844)* Fix: all language rule files emitted regardless of selected `language` (#861)
- *(PI-842)* Fix: MCP servers launch via `bunx` on non-JS scaffolds → ENOENT (#862)
- *(PI-849)* Fix: rag.md rule loads full RAG-stack description even when RAG is not wired (#864)
- *(PI-846)* Fix: graphify hook-guard matcher too broad — fires on every Bash/Read/Glob incl. non-source tasks (#865)
- *(PI-845)* Fix: report_upstream_issue skill unusable — github_command_guard blocks its prescribed upstream issue-create command (#866)
- *(PI-843)* Fix: skills double-installed — checked-in .claude/skills/ duplicates enabled project-init plugins (#867)
- *(PI-848)* Fix: scaffold emits local custom agents that duplicate plugin/built-in agents (#863)
- *(PI-847)* Fix: config.yaml python_floor (3.14) contradicts .python-version / pyproject requires-python (3.13) (#860)

### Documentation

- *(PI-840)* Self-hosted runner guide: document required host binaries (jq missing = exit-127 jobs masquerading as PR failures) (#853)

### Miscellaneous Tasks

- Release 1.2.0 (#868)

## [1.1.8] - 2026-07-16

### Bug Fixes

- *(PI-833)* Stop the wizard reading as two conflicting memory questions (#835)
- *(PI-832)* Rendered agent_guard_adapter.py fails its own ruff format gate (#834)

### Miscellaneous Tasks

- Release 1.1.8 (#836)

## [1.1.7] - 2026-07-13

### Features

- *(PI-828)* Descriptor contract: optional ci.status_url — declare a non-forge CI status endpoint (#829)

### Miscellaneous Tasks

- *(PI-830)* Release 1.1.7 — ship the optional ci.status_url descriptor block (#828) (#831)

## [1.1.6] - 2026-07-13

### Bug Fixes

- *(PI-825)* Check ruleset-required status checks too, not just classic protection (#826)

### Miscellaneous Tasks

- Release 1.1.6 (#827)

## [1.1.5] - 2026-07-13

### Bug Fixes

- *(PI-822)* A PR-only required check is not a phantom — stop guessing without a PR (#823)

### Miscellaneous Tasks

- Release 1.1.5 (#824)

## [1.1.4] - 2026-07-13

### Bug Fixes

- *(PI-819)* Name the required check that nothing reports (#820)

### Miscellaneous Tasks

- Release 1.1.4 (#821)

## [1.1.3] - 2026-07-12

### Bug Fixes

- *(PI-816)* Upgrade deleted the project's own files during the .agents migration (#817)

### Miscellaneous Tasks

- Release 1.1.3 (#818)

## [1.1.2] - 2026-07-12

### Bug Fixes

- *(PI-809)* Restore plugin manifests to .claude-plugin/ and drop the duplicate hooks key (#810)
- *(PI-811)* Pre-commit hook silently destroyed unstaged work it couldn't isolate (#812)
- *(PI-813)* Upgrade could not upgrade any pre-v1.0.1 scaffold (#814)

### Miscellaneous Tasks

- Release 1.1.2 (#815)

## [1.1.1] - 2026-07-12

### Bug Fixes

- *(PI-802)* Benchmark harness looks for Claude creds in ~/.agents, not ~/.claude — blocks subscription-auth measurement (#803)
- *(PI-806)* Text-field gate accepts C1 control chars (0x80-0x9F) that corrupt config.yaml (#807)

### Features

- *(PI-804)* Add edge-case-dense benchmark tasks (semver, csvparse) so measurement has real headroom (#805)

### Miscellaneous Tasks

- Release 1.1.1 (#808)

## [1.1.0] - 2026-07-12

### Bug Fixes

- *(PI-627)* Scope & harden the .claude projection; resolve bug-review findings (#634)
- Pin scaffolded workflow actions to commit SHAs (#629) (#630)
- *(PI-673)* Semgrep via uvx — pip install fails on self-hosted runners (#675)
- *(PI-674)* PI_CI_TIMEOUT override for the monitor CI wait (#676)
- *(PI-691)* Create_issue.sh: host-aware --parent URLs and --agent-ready validation (#693)
- *(PI-698)* Fresh scaffold fails its own ruff gate: compressor hook PTH violations + pre-edit guard S-rules (#699)
- *(PI-631)* Fix: start_issue.sh derives the project key from the current directory name, not config (#702)
- *(PI-668)* Upgrade round-trip tests flake under pytest-xdist full-suite runs (#703)
- *(PI-633)* Fix: start_issue.sh cannot create the draft PR when the branch has no commits (#704)
- *(PI-632)* Fix: finish_pr.sh / monitor_pr.sh merge step races the last CI check (#705)
- *(PI-678)* Finish_pr/monitor_pr: delete the merged local branch after a successful merge (#707)
- *(PI-706)* Gate the CI verdict on the API head matching the pushed tip (#712)
- *(PI-628)* Pin one Python version across mise, mypy, and the CI matrix (#713)
- *(PI-715)* Make the review gate satisfiable by the agents that review (#716)
- *(PI-719)* Review-status.yml never loaded — invalid Actions trigger (#720)
- *(PI-689)* Kill the third CCR pin literal and document the checker's scope (#722)
- *(PI-726)* Add a real format gate, and stop rules docs promising one (#728)
- *(PI-725)* Make clippy see test code; give go and rust a typecheck recipe (#734)
- *(PI-727)* Run just fuzz in CI for every language, nightly and non-blocking (#736)
- *(PI-738)* Stop license-scan swallowing a stale lockfile, and unbreak fresh scaffolds (#741)
- *(PI-779)* Fresh node scaffold fails 'just lint' on day one — biome format has no ignore config, scans .agents/ and JSON configs (#783)
- *(PI-781)* Fresh Rust scaffold is day-one CI red; Go+Rust fail pre-push fast-ci — missing source-existence guards on test/typecheck (#782)
- *(PI-780)* Just --list shows garbled comment fragments as recipe descriptions (all langs + this repo) (#784)
- *(PI-789)* Board cards for closed issues stay frozen — sync to Done on issue close + one-time backfill (#790)

### Documentation

- Reframe Ollama support — capable local models via --multi-model (#635)
- Add GitHub lifecycle DAG state diagram (#669)
- Record two earned conventions, and ship them to scaffolded projects (#730)
- *(PI-743)* Ship the 'assert behaviour, not text' refinement to scaffolds (#744)
- *(PI-745)* Scope TDD to design; point the break-it rule at mutmut where it exists (#746)
- *(PI-684)* Worked grounding example for the diagram skill (#752)
- *(PI-683)* Align ADR template and Obsidian design vault with diagram folder convention (#753)

### Features

- *(PI-643)* Enrich scaffolded git-config & editor-hiding for new overlays (#644)
- *(PI-645)* Polish interactive wizard UI (theme, preset table, spinner, summary) (#646)
- *(PI-647)* Propagate token-efficiency conventions to templates + token_efficiency skill (#648)
- *(PI-649)* Deduplicate and trim the workflow_state_reminder injection (#650)
- *(PI-653)* Monitor_pr review-wait frames only on reviewDecision change (#654)
- *(PI-651)* Cap failure-path hook output at 40 lines (#652)
- *(PI-655)* Attribute tool_result context volume per tool in usage_report (#656)
- *(PI-657)* Trim always-loaded AGENTS.md reference blocks into enforcement guide (#658)
- *(PI-661)* Ship zero-token statusline context meter in scaffolded settings (#662)
- *(PI-663)* Checkpoint skill — checkpoint-and-clear session handoff (#664)
- *(PI-665)* Diagram skill — collaborative Mermaid-first diagramming (#667)
- *(PI-666)* CI_RUNS_ON self-hosted-runner escape hatch for scaffolded ci.yml (#670)
- *(PI-671)* Local_ci skill + monitor_pr billing-lockout hint (#672)
- *(PI-685)* Reconcile repo's own .agents/ hooks and skills with templates (already diverged) (#690)
- *(PI-679)* Propagate folder-per-diagram + mandatory-render convention into templated diagram skill (#692)
- *(PI-696)* PostToolUse tool-output compressor for oversized git-diff-class results (prototype) (#697)
- *(PI-714)* Make review cycles configurable and explained in the wizard (#717)
- *(PI-687)* Give the explore subagent an orientation contract (#723)
- *(PI-686)* Enforce staleness for the scaffolded CODE_MAP and own skills INDEX (#724)
- *(PI-729)* Give TypeScript a blocking security lint, and unbreak its toolchain (#731)
- *(PI-747)* Verify-test-strength skill: agentic mutation loop to prove guards can fail (#756)
- *(PI-759)* Lighter pre-push gate (both surfaces); CI parallelization deferred to #762 (#760)
- *(PI-762)* Shard CI tests into parallel jobs (race-free, ~4x faster) (#764)
- *(PI-765)* Gate repo coverage at 85% (nightly full-suite run) (#766)
- *(PI-767)* Add gitleaks pre-commit secret scan to the repo (#768)
- *(PI-769)* Semgrep + license-scan advisory jobs on repo CI (#770)
- *(PI-761)* Scaffolded CI resolves matrix per event (floor per-PR, full nightly) (#774)
- *(PI-544)* Add `project-init doctor` health-check subcommand (#775)
- *(PI-545)* Colorize the unified diff in upgrade/add/remove reports (#776)
- *(PI-777)* Auto-apply area:<slug> labels from the issue body Area field (#778)
- *(PI-786)* Publish descriptor + usage-event JSON schemas as a consumable, versioned artifact (ship in wheel) (#788)
- *(PI-796)* DAG command guard logs decision+command to usage.jsonl (WS3 producer side) (#797)

### Miscellaneous Tasks

- Add fast-iterate test recipe and token-efficiency conventions (#642)
- *(PI-659)* Dedupe project-init.md format table and compaction list (#660)
- *(PI-694)* Token-budget lint gate for always-loaded context files + memory size lint (#695)
- *(PI-700)* Reduce scaffold turn-tax: actionable guard denials, gate batching, benchmark-derived token guidance, profile routing (#701)
- *(PI-708)* Reconcile monitor_pr.sh divergence: sync root copy from the template (#709)
- *(PI-710)* Reconcile push_wiki.sh divergence: upstream --prune + bot identity, keep host-aware clone (#711)
- *(PI-636)* Measure coverage without gating on it (#718)
- *(PI-733)* CI does not install bun, so the TS behavioral gates silently skip (#735)
- *(PI-737)* Install just in CI so the commit-hook gates run, and fail closed (#740)
- *(PI-739)* Parse workflow YAML in contract tests instead of slicing strings (#742)
- *(PI-637)* Add dependency vulnerability scanning (pip-audit or Dependabot) (#748)
- *(PI-638)* CI Python version matrix doesn't match declared support (3.11-3.13) (#749)
- *(PI-639)* Confirm whether the no-mypy stance for this repo's own code is still intended (#750)
- *(PI-681)* Drift convention/helper for personal ~/.claude skills vs templates (#754)
- *(PI-688)* Map-not-territory rule + deterministic prose/diagram staleness checks (#755)
- *(PI-757)* Quality-gate policy doc + required-gate drift guard (epic #751) (#758)
- *(PI-589)* CI clustering policy + concurrency-cancel (#763)
- *(PI-772)* Adopt ruff format gate on the scaffolder repo (reformat + enforce) (#773)
- *(PI-791)* SHA-pin all GitHub Actions in repo workflows and scaffolded workflow templates (#792)
- *(PI-793)* Finish DAG-guard hardening and reconcile its "enforced" framing with ADR-007 (#795)
- *(PI-794)* Split __main__.py (2,153 lines) into parser / wizard-prompts / variables / subcommands (#798)
- *(PI-799)* Unify duplicated python-floor extractor and add a direct test (mutmut survivors) (#800)
- Release 1.1.0 (#801)

### Testing

- *(PI-785)* Producer contract-conformance test: validate emitted config.yaml against descriptor.schema.json + assert surface locations (#787)

## [1.0.1] - 2026-07-07

### Bug Fixes

- *(PI-614)* Derive mypy python version from project floor correctly (#621)
- *(PI-625)* Fix day-one live-test scaffold failures (#626)

### Features

- *(PI-606)* Migrate to .agents and resolve test failures (#620)
- *(PI-619)* Scaffold .agents/AGENTS.md for Antigravity (#622)
- *(PI-605)* Guards log the governance signal (decision + command) (#623)
- *(PI-603)* Update templates and schemas for contract v2 (#624)

## [1.0.0] - 2026-07-04

### Bug Fixes

- Resolve full QA-sweep findings across CLI, wizard, and templates (#601)

### Documentation

- Release v1.0.0 — docs/wizard-copy audit fixes + version bump (#602)

## [0.6.1] - 2026-07-04

### Bug Fixes

- *(PI-592)* Scaffolder robustness — typecheck stubs + audit fixes (#594)
- Unbreak fresh-scaffold lint gate (shfmt + ruff S on emitted scripts) (#595)
- Resolve project-review audit findings — day-one gates, language parity, correctness (#597)
- Resolve full-codebase review findings and release v0.6.1 (#598)

### Features

- Shift-left static checks into commit/push hooks (repo + scaffolded) (#596)
- Make the release dispatchable when a tag can't be pushed (#599)

## [0.6.0] - 2026-07-02

### Bug Fixes

- Resolve registered scaffold/governance bugs + release v0.5.3 (#552–556)
- Resolve review findings across engine, guard, templates, and CI (#590)

### Documentation

- Prep v0.6.0 release (migration note + README release line) (#591)

### Features

- Backlog quality/security toolchain hardening + Rust support [PI-558, 559, 561-565]
- *(PI-576)* Add OpenSSF Scorecard as a scheduled CI job (#581)
- *(PI-577)* Scan built container images with Trivy (delivery=service) (#582)
- *(PI-578)* Lint the Dockerfile with hadolint (delivery=service) (#583)
- *(PI-575)* Add SLSA build provenance attestation to release artifacts (#584)
- *(PI-574)* Generate a CycloneDX SBOM in release, attach to Releases (#585)
- *(PI-579)* Add dependency license compliance scanning (#586)
- *(PI-580)* Wire up property-based testing / fuzzing per language (#587)
- Self-populating board metadata + upstream bug-routing skill (#588)

### Miscellaneous Tasks

- Bump version to 0.6.0
- *(PI-570)* Raise per-language quality gates to their strictest practical ceiling (#571)
- *(PI-569)* Enforce a blocking test coverage threshold in CI (#572)
- *(PI-568)* Add dependency vulnerability (CVE/advisory) scanning to CI (#573)

## [0.5.2] - 2026-06-28

### Bug Fixes

- Correct project-init-workflow plugin description (#548)
- *(PI-550)* Mask free-text flag values in command-guard + release v0.5.2 (#551)

### Documentation

- *(PI-542)* Lead README with ICP + above-the-fold quickstart (#547)

### Miscellaneous Tasks

- Add marketplace manifest description (#549)

## [0.5.1] - 2026-06-27

### Bug Fixes

- *(PI-526)* Gate concern-decoupled skills (save_memory/status/session_summary) (#527)
- *(PI-535)* Harden never-clobber + idempotence in emission layer (#536)
- *(PI-537)* Post-dogfooding hardening batch (8 bugs) (#538)

### Documentation

- *(PI-521)* Discoverability quick-wins (#522)
- *(PI-533)* Document add/remove/purge/export concern commands (#534)

### Features

- *(PI-528)* Concern add/remove subcommands (engine + toggle concerns) (#529)
- *(PI-531)* Remove --purge / --export for concern source data (#532)

### Miscellaneous Tasks

- *(PI-539)* Release v0.5.1 — version bump, docs renewal, contributor onboarding (#540)

### Testing

- *(PI-524)* Compose-over-X interop tests (never-clobber overlay) (#530)

## [0.5.0] - 2026-06-27

### Bug Fixes

- *(PI-296)* Preserve hand-edited config.yaml on re-scaffold (#345)
- *(PI-360)* MacOS bash-3.2/BSD breakage in always-on hooks (mapfile, sha256sum) (#375)
- *(PI-361)* Route all Python invocations through a canonical _py.sh resolver (#376)
- *(PI-396)* Refresh multi-model CCR config — current model IDs, Gemini provider, gateway/LiteLLM (#400)
- *(PI-394)* Run prod_guard on non-Claude surfaces — destructive-command guard was Claude-only (#401)
- Codex review follow-ups — prod_guard fail-open, stale doc refs, cross-surface test coverage (#414)
- *(PI-441)* Harden CI-gate + start_issue key/draft-PR in lifecycle scripts (#446)
- *(PI-440)* Render full observability HTML report + robust token parsing (#445)
- *(PI-442)* Close command-guard CWD/refspec holes; mark codex hook advisory (#447)
- *(PI-443)* Antigravity serverUrl MCP, upgrade LF newlines, advisory IaC gate (#448)
- *(PI-444)* Align README AGENTS/CLAUDE direction with output; gate GEMINI INDEX link (#449)
- Remove stray `link` file committed by accident in #465 (#468)
- Stop scaffold from leaking template __pycache__/*.pyc into projects (#487)
- *(PI-488)* Guard OpenTofu (tofu) in prod_guard deny-table (#489)
- Model bare gh pr view --json number in live_test stub (#490)
- *(PI-491)* Ship the base plan skill to non-Claude surfaces (#492)
- *(PI-516)* Harden scaffolder bad-paths found in e2e sweep (#517)
- *(PI-518)* Node/go gitignore + gate docs/ tree on --no-docs (#519)

### Documentation

- *(PI-254)* Enterprise GitHub compatibility support matrix (#260)
- *(PI-246)* ADR-013 distribution & governance model (three profiles) (#261)
- *(PI-256)* Org fork lifecycle runbook skeleton (#262)
- *(PI-270)* Measurement methodology + metric taxonomy (#293)
- *(PI-299)* ADR-014 environment promotion-chain branch model (#300)
- *(PI-311)* Operator branch-model note + skill/copilot cross-refs (#312)
- *(PI-317)* ADR-015 env/deploy model + operator decision guide (#331)
- *(PI-328)* Document delivery/deploy/iac flags in README + consistency test (#342)
- *(PI-350)* ADR-016 model-agnostic switching via CCR (#357)
- *(PI-353)* Model-switching user guide (providers, Ollama list, caveats) (#370)
- *(PI-367)* Local-vs-cloud enforcement boundary + surface support matrix (#383)
- *(PI-384)* Add mobile/remote dev-access guide (Remote Control + tmux fallback) (#393)
- *(PI-413)* ADR-018 — AI-governance overlay (#417)
- *(PI-407)* Observability guides + ADR-019 (Track A closeout) (#422)
- *(PI-467)* ADR-021 — quality vs lifecycle tier boundary (spike) (#474)
- *(PI-471)* ADR-022 — toolchain gate map (keep conditionals, no overlays) (#475)
- *(PI-478)* Add ADR-024 memory-tier model (#499)
- *(PI-479)* Add ADR-025 agentic-OS root-layer spike + design note (#507)
- *(PI-512)* Aggregate-by-tier + connection/transport model for agentic-os (#513)
- Deploy MkDocs Material site to GitHub Pages (#481)

### Features

- *(PI-255)* Enterprise GitHub host support (#263)
- *(PI-247)* Distribution profile (individual/standalone/org) (#264)
- *(PI-248)* Host-aware marketplace source + version-record fields (#265)
- *(PI-259)* Local observability record (#266)
- *(PI-258)* Org no-egress mode (#267)
- *(PI-249)* Opt-in consent for new additions during upgrade (#288)
- *(PI-250)* Pull-and-recommend (version-span + recommendations) (#289)
- *(PI-251)* Hybrid enforcement (org hard layer binds) (#290)
- *(PI-252)* Company preset authoring (inheritance + generator) (#291)
- *(PI-257)* Org fork lifecycle end-to-end + release plumbing (#292)
- *(PI-242)* Guard upgrade --apply on a dirty git tree + undo hint (#294)
- *(PI-243)* Config-driven preserve list (#295)
- *(PI-301)* Wizard --branch-model option + config branch_model block (#302)
- *(PI-303)* Config-driven base branch in the shared lifecycle (#304)
- *(PI-305)* Promote-env fast-forward promotion command (#306)
- *(PI-307)* Setup_env_branches.sh — create + protect the promotion chain (#308)
- *(PI-309)* Retarget scaffolded CI/PR-validation to base branch + promote-env --no-verify (#310)
- *(PI-313)* Epic-sizing guidance — keep child tickets small (#314)
- *(PI-318)* Delivery-model wizard question + config field (#332)
- *(PI-319)* Container parity bundle for delivery=service (#333)
- *(PI-320)* CI build-once image job for delivery=service (#334)
- *(PI-321)* Document agent production-ref boundary in github_workflow skill (#335)
- *(PI-322)* Library release workflow (publish disabled by default) (#336)
- *(PI-323)* Opt-in deploy overlay — GitHub Environments, build-once-by-digest (#337)
- *(PI-324)* Tiered prod gate + setup_env_protection.sh + whats_deployed.sh (#338)
- *(PI-325)* Opt-in IaC overlay — OpenTofu/HCL skeleton, gated apply (#339)
- *(PI-326)* Cloud-integration seam — OIDC + env contract (#340)
- *(PI-240)* 3-way auto-merge for upgrade conflicts (#346)
- *(PI-245)* Per-file interactive apply for upgrade (#347)
- *(PI-241)* Upgrade-as-a-PR workflow (#348)
- *(PI-244)* Surface changelog/migration notes during upgrade (#349)
- *(PI-351)* CCR multi-model overlay — config + setup_models.sh installer (#368)
- *(PI-352)* Init-step messaging for the multi-model wizard prompt (#369)
- *(PI-358)* Day-2 models helper — add/switch/remove models after setup (#371)
- *(PI-356)* Scheduled third-party update + security-review task (#373)
- *(PI-366)* Emit multi-surface MCP + hooks config from a canonical source (#381)
- *(PI-374)* Generate an agnostic capabilities inventory (#382)
- *(PI-395)* Ship reusable subagent specs (code-reviewer, explore) + refresh agents README (#402)
- *(PI-397)* Add Amp + JetBrains Junie MCP surfaces + HTTP/streamable catalog entry (#408)
- *(PI-410)* Governance overlay foundation + usage-track docs (#415)
- *(PI-412)* Governance product track — system card + AIBOM + CI gate (#416)
- *(PI-404)* --observability flag plumbing + upgrade round-trip (#419)
- *(PI-405)* Observability analyzer + report (usage_report.py + observability.sh) (#420)
- *(PI-406)* Guarded hook self-log (_usage_log.sh + prod_guard.py) (#421)
- *(PI-271)* Benchmark collection harness (tools/benchmark/) (#423)
- *(PI-272)* Latency & cost capture (prices.py + latency.py) (#424)
- *(PI-273)* Accuracy/task-success scoring (scoring.py) (#425)
- *(PI-275)* Cost-benefit Pareto report (report.py) (#426)
- *(PI-466)* Make memory backend à-la-carte (memory=none, core preset) (#473)
- *(PI-476)* Extract GitHub lifecycle into an opt-out --lifecycle overlay (#482)
- *(PI-477)* Add a docs axis and gate renovate.json (#483)
- *(PI-472)* Self-explaining wizard standard with a coverage test (#484)
- *(PI-497)* Split memory/ from vault/ into an auto tier + staleness lint (#501)
- *(PI-496)* Add a low-token code-map for agents (documentation axis) (#502)
- *(PI-498)* Standardize the cross-project memory descriptor (#503)
- *(PI-505)* Add tier-3 RAG opt-in seam — docs, setup stub, descriptor (#506)
- *(PI-498)* Finish the Agentic-OS memory descriptor contract (#508)
- *(PI-510)* Add --json output for orchestrator-driven scaffolding (#511)
- *(PI-495)* Wire tier-3 RAG engine (cocoindex-code, keyless on-device) (#514)

### Miscellaneous Tasks

- Gitignore mkdocs site/ and plan scratch (#297)
- *(PI-329)* Remove branch-per-env; extract shared base-branch protection (#330)
- *(PI-343)* Drop GitHub Pages docs-site auto-deploy (#344)
- *(PI-354)* De-hardcode Anthropic model IDs in skill/agent doc examples (#372)
- *(PI-362)* Shell portability hardening sweep (jq, .gitattributes, stat, shebangs, gh guards, engine LF) (#377)
- *(PI-365)* Non-CLI surface capability matrix (spike) (#379)
- *(PI-364)* ADR-017 — canonical hook/MCP spec → per-surface generator (#380)
- *(PI-388)* Migrate hooks to documented PreToolUse decision schema + Codex MCP secret passthrough (#389)
- *(PI-387)* Remove postgres + sqlite DB MCP entries (#390)
- *(PI-386)* Retire dead Gemini-CLI overlay; make Antigravity the Google surface (#391)
- *(PI-385)* Fix GUI-surface hook stdin parsing + deny shapes (Cursor, Antigravity) (#392)
- *(PI-399)* Post-PI-386 hygiene — reconcile stale Gemini doc bodies (#409)
- Remove merged PLAN-276 governance working artifacts (#418)
- *(PI-450)* Remove redundant GEMINI.md redirect; clarify .claude/ vs per-surface wiring (#451)
- *(PI-452)* Benchmark harness supports Claude subscription auth (#453)
- *(PI-454)* Verify current schema in add_hook/add_command; fix stale dev copy (#455)
- *(PI-456)* Fix skill/command/hook audit findings (fabricated APIs, deprecated schema, legacy drift) (#457)
- *(PI-458)* Finish_pr verifies branch matches PR head before pushing (#459)
- *(PI-460)* Add /live_test agent-driven live E2E command for the scaffolder (#461)
- *(PI-463)* Pin shell:bash on hooks + document Git for Windows + add Windows CI (#464)
- *(PI-462)* Make plugin-mode scaffold docs mode-aware + fix ADR path (#465)
- *(PI-493)* Gate cross-stack examples by language/cloud (#494)
- Remove LightRAG residue (ADR-024) (#504)
- Release 0.5.0 (#520)

### Testing

- *(PI-327)* Lock config.yaml env schema + upgrade backfill/normalization (#341)
- *(PI-363)* Cross-platform portability regression tests + macOS CI runner (#378)
- Add a combination-matrix smoke test (#485)
- Enforce the cross-path variable contract globally (#486)

## [0.4.0] - 2026-06-17

### Bug Fixes

- *(PI-183)* Upload only build artifacts; harden the pypi environment (#185)
- *(PI-204)* Install_hooks replaces a symlinked hook, not its referent (#223)
- *(PI-206)* Give start_issue a fallback slug for non-alphanumeric titles (#224)
- *(PI-187)* Parse multi-line YAML safety.allow lists, not just inline JSON (#233)
- *(PI-197)* Reject wrong-typed record fields with a clean UpgradeError (#217)
- *(PI-196)* Key first-scaffold on the record marker, not config existence (#218)
- *(PI-188)* Reject path traversal in load_preset (#225)
- *(PI-205)* Require matching {{/if name}} in the render engine (#226)
- *(PI-199)* Gather interactive input before creating the target dir (#227)
- *(PI-201)* Write planning metadata into the issue body (issue lifecycle) (#219)
- *(PI-198)* Block gh-api merges regardless of flag position (#220)
- *(PI-202)* Push wrapper refuses main/master for any push, not just force (#221)
- *(PI-203)* Resync root monitor_pr.sh — stop reporting false merge success (#222)
- *(PI-207)* Repair board automation on user-owned repos (resolver + repo pin) (#211)
- *(PI-210)* Set GH_REPO so validate-pr can resolve the repo for gh (#212)
- *(PI-208)* Stop pinning CI to Python 3.12; let uv resolve the version (#213)
- *(PI-186)* Bound the monitor_pr CI-wait loop so it can't hang forever (#216)
- *(PI-209)* Install CI dev deps via `uv sync --group dev` (PEP 735) (#215)

### Documentation

- *(PI-192)* Add ADRs 005-012 and the usage guide to the docs nav (#228)
- *(PI-193)* Note ADR-006 supersession in ADR-003 and ADR-005 (#229)
- *(PI-194)* Fix README phantom examples/ and justfile test-cov comment (#230)

### Features

- *(PI-214)* Derive scaffolded CI Python matrix from requires-python (#238)

### Miscellaneous Tasks

- *(PI-200)* Validate-pr verifies title key matches the Closes number (#232)
- *(PI-189)* Share overlay_layers + _new_sibling across scaffold/upgrade (#235)
- *(PI-190)* ScaffoldInputs dataclass + one source for variable defaults (#237)
- Bump version to 0.4.0 (#239)

### Testing

- *(PI-195)* Cover the interactive wizard leaf parsers and install.sh (#231)

## [0.3.0] - 2026-06-14

### Bug Fixes

- *(ci)* Point cache-dependency-glob to pyproject.toml (uv.lock is gitignored)
- *(PI-179)* Prevent first-scaffold data loss, repair dev loop and license owner (#182)

### Documentation

- *(PI-135)* Document Claude-first positioning and add developer onboarding guide (#149)
- Clarify git-hook enforcement requires per-clone install (#150)
- *(PI-134)* Add ecosystem positioning section to README (#151)
- Use full .claude/scripts path for install_hooks.sh in README (#159)

### Features

- *(PI-138)* Quality and documentation toolchain for scaffolded projects (#154)
- *(PI-139)* Justfile as canonical command interface in templates and this repo (#155)
- *(PI-142)* Project-init upgrade with drift report and --apply (#160)
- *(PI-145)* Governance starter files and branch protection bootstrap (#161)
- *(PI-146)* SessionStart bootstrap hook and opt-in devcontainer (#162)
- *(PI-140)* Mise pinning, env/secret pattern, and .vscode overlays (#163)
- *(PI-130)* Graphify memory preset; LightRAG demoted to legacy (#164)
- *(PI-129)* Plugin + same-repo marketplace, dual-shipped (#166)
- *(PI-137)* Opt-in multi-agent overlays — Codex, Gemini, Ollama tier (#167)
- *(PI-169)* Publish to PyPI via trusted publishing (#170)
- *(PI-172)* Remove the legacy LightRAG overlay and dead weight (#173)
- *(PI-168)* Prod-safety guard — deny destructive commands, stricter in auto mode (#174)
- *(PI-165)* Plugin cutover — scaffolds are plugin-first (#175)

### Miscellaneous Tasks

- *(PI-141)* Adopt Conventional Commits for commit messages and PR titles (#147)
- *(PI-132)* Make LightRAG model names template variables (#148)
- *(PI-133)* Modernize skill frontmatter and add validation tests (#152)
- *(PI-131)* Replace custom safety hooks with plugin and git/CI enforcement (#153)
- *(PI-144)* Tagged releases, changelog, release-pinned install.sh (#156)
- *(PI-143)* Renovate for this repo and scaffolded projects (#157)
- *(PI-136)* Make AGENTS.md canonical; CLAUDE.md and GEMINI.md redirect (#158)
- Extend push_wiki to prune stale pages and refresh wiki content (#176)
- PyPI release readiness: LICENSE, metadata, absolute links, v0.3.0 (#177)
- Relicense to Apache-2.0 before first PyPI release (#178)

### PI-19

- Codex evaluation, CRLF regression test, regen example

[Unreleased]: https://github.com/VytCepas/project-init/compare/v1.2.2...HEAD
[1.2.2]: https://github.com/VytCepas/project-init/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/VytCepas/project-init/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/VytCepas/project-init/compare/v1.1.8...v1.2.0
[1.1.8]: https://github.com/VytCepas/project-init/compare/v1.1.7...v1.1.8
[1.1.7]: https://github.com/VytCepas/project-init/compare/v1.1.6...v1.1.7
[1.1.6]: https://github.com/VytCepas/project-init/compare/v1.1.5...v1.1.6
[1.1.5]: https://github.com/VytCepas/project-init/compare/v1.1.4...v1.1.5
[1.1.4]: https://github.com/VytCepas/project-init/compare/v1.1.3...v1.1.4
[1.1.3]: https://github.com/VytCepas/project-init/compare/v1.1.2...v1.1.3
[1.1.2]: https://github.com/VytCepas/project-init/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/VytCepas/project-init/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/VytCepas/project-init/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/VytCepas/project-init/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/VytCepas/project-init/compare/v0.6.1...v1.0.0
[0.6.1]: https://github.com/VytCepas/project-init/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/VytCepas/project-init/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/VytCepas/project-init/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/VytCepas/project-init/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/VytCepas/project-init/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/VytCepas/project-init/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/VytCepas/project-init/releases/tag/v0.3.0
