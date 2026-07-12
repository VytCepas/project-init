"""project-init variable resolution: flag→prompt→preset precedence + template context.

ScaffoldInputs, the pure resolvers (delivery/deploy/iac/agents/profile), the
per-language command table, and _build_variables/_resolve_inputs live here so the
most bug-prone surface (the ignored-flags class the 2026-07 review flagged) is a
leaf module, isolated from the CLI spine (__main__) and the wizard prompts
(PI-794). This module imports only scaffold/console/mcps — never the wizard or
subcommands.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from project_init import __plugin_version__, __repo_url__, __version__
from project_init.mcps import (
    MCP_CATALOG,
    PLAYWRIGHT_MCP,
    format_installed_mcps,
    format_installed_mcps_yaml,
)
from project_init.scaffold import (
    CONTRACT_VERSION,
    marketplace_source_vars,
    memory_tier,
    overlay_layers,
    slugify,
)


@dataclass(frozen=True)
class ScaffoldInputs:
    """The resolved wizard inputs as one named record (PI-190).

    Replaces an 11-element positional tuple that was built and unpacked by hand
    across the interactive, non-interactive, and main paths — where a field
    reorder silently mis-mapped values with no error.
    """

    project_name: str
    project_description: str
    language: str
    selected_mcps: list[dict[str, Any]]
    owner: str
    license_choice: str
    devcontainer: bool
    mise: bool
    vscode: bool
    agents: list[str]
    no_plugin: bool
    profile: str
    no_egress: bool = False
    # Memory backend (#466): the resolved memory_stack — "obsidian-only",
    # "obsidian-graphify", or "none" (vault-free). Drives the obsidian/graphify
    # overlays via overlay_layers() and the memory/obsidian/graphify gate vars.
    # Resolved with precedence flag > interactive > preset var > "obsidian-only".
    memory: str = "obsidian-only"
    # GitHub lifecycle tier (#476, ADR-021): "github" ships the issue→branch→PR
    # →review→merge automation (DAG hooks/scripts, board/wiki/validation
    # workflows, issue/PR templates, lifecycle skills); "none" declines it for a
    # forge-agnostic / minimalist scaffold. Opt-OUT — default ON. Drives the
    # lifecycle/lifecycle_fallback overlays + the `lifecycle` gate var. Resolved
    # with precedence flag > interactive > preset var > "github". Forge-portable
    # quality hooks (commit-msg, gitleaks, lint/format gate, prod-safety) are
    # core and stay regardless.
    lifecycle: str = "github"
    # Delivery model (epic #316, ADR-015): how the project ships — drives the
    # env/CI/release bundle. "prototype" is the safe minimal default.
    delivery: str = "prototype"
    # Deploy target (epic #316, ADR-015): opt-in deploy overlay for services.
    # "none" = my platform owns deploy, or not deployed via Actions yet.
    deploy: str = "none"
    # IaC overlay (ADR-015, opt-in): none | opentofu. Independent of delivery.
    iac: str = "none"
    # Multi-model switching overlay (ADR-016, epic #315, opt-in): scaffolds the
    # claude-code-router config + setup_models.sh installer. Off by default.
    multi_model: bool = False
    # AI-governance overlay (ADR-018, epic #276, opt-in): scaffolds the
    # governance-as-code layer (AUP/system-card docs + CI gate). Off by default.
    # Distinct from the PI-145 CODEOWNERS/LICENSE governance prompts.
    governance: bool = False
    # Observability overlay (ADR-019, epic #269 Track A, opt-in): scaffolds the
    # file-based usage-report layer (transcript parser + guarded self-log +
    # stdlib HTML report). Off by default; no Docker/OTEL.
    observability: bool = False
    # Docs tooling axis (#477, ADR-022): gates the local docs-preview configs
    # (mkdocs for python, typedoc for node) so a project can decline them. Opt-OUT
    # — default ON; the per-tool language gate still applies (mkdocs→python,
    # typedoc→node), so this only narrows, it never forces docs on a new language.
    want_docs: bool = True
    # Renovate config (#477, ADR-022): gates renovate.json (dependency-update bot).
    # Opt-OUT — default ON to preserve today's always-shipped config.
    renovate: bool = True
    # Target CPython for a Python scaffold (#628). One value renders into
    # mise.toml (toolchain pin), mypy.ini (typeshed baseline), and the CI
    # matrix floor — before this, those three disagreed on day one. Empty means
    # "derive": an existing pyproject.toml's requires-python floor, else 3.11.
    # A declared requires-python is authoritative (CI derives its matrix from it
    # at run time), so a --python-version that disagrees is rejected outright
    # rather than half-applied; see _reject_conflicting_python_version.
    python_version: str = ""
    # Review-fix cycles the scaffolded monitor_pr.sh runs before it stops asking
    # for another pass (#714). Rendered into .agents/config.yaml and read back by
    # gh_host.sh's review_cycles(). 0 = no review control (merge on green CI).
    # Only meaningful with the GitHub lifecycle; a --lifecycle none project ships
    # no monitor_pr.sh, so the wizard doesn't ask and the key isn't rendered.
    review_cycles: int = 2


SUPPORTED_PYTHON_VERSIONS: tuple[str, ...] = ("3.11", "3.12", "3.13", "3.14")


def _python_floor_from_pyproject(target: Path | None) -> str | None:
    """The requires-python floor declared by an existing pyproject.toml, if any.

    Returns None for a greenfield scaffold — the case #628 is about, where no
    file declares a version and every consumer used to invent its own.
    """
    if not target or not (target / "pyproject.toml").exists():
        return None
    try:
        import tomllib

        with (target / "pyproject.toml").open("rb") as f:
            data = tomllib.load(f)
        req = data.get("project", {}).get("requires-python", "")
        if not req:
            req = data.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python", "")
        if req:
            import re

            m = re.search(r"(?:>=?|==|~=?|\^|^\s*)\s*(\d+\.\d+)", req)
            if m and m.group(1):
                return m.group(1)
    except Exception:
        return None
    return None


def _validate_review_cycles(
    args: argparse.Namespace, parser: argparse.ArgumentParser, effective_lifecycle: str | None
) -> None:
    """Reject an unusable --review-cycles before the target dir or any prompt.

    Runs on BOTH paths (PR #717 review). The interactive wizard used to copy the
    raw value, so `--review-cycles -1` recorded a count that later crashed
    monitor_pr.sh, and a lifecycle-none pairing was dropped in silence.

    ``effective_lifecycle`` is the tier this run will actually scaffold, or None
    when it isn't knowable yet. A *preset* may set ``lifecycle = "none"`` with no
    --lifecycle flag in sight (PR #717 review, cycle 2), so checking args alone
    let that combination through. In an interactive run the preset only seeds the
    prompt's default, so the tier stays unknown here and the wizard warns instead.
    """
    if args.review_cycles is None:
        return
    if args.review_cycles < 0:
        parser.error(
            f"--review-cycles must be a non-negative integer (got {args.review_cycles}); "
            "0 disables review control."
        )
    if effective_lifecycle == "none":
        parser.error(
            f"--review-cycles {args.review_cycles} requires the GitHub lifecycle "
            "(the run resolves to lifecycle 'none'); no merge gate is scaffolded "
            "to run them."
        )


def _resolve_review_cycles(args: argparse.Namespace, effective_lifecycle: str) -> int:
    """The non-interactive count (#714). _validate_review_cycles has already run."""
    if effective_lifecycle == "none":
        return 0
    return 2 if args.review_cycles is None else args.review_cycles


def _resolve_mcps_non_interactive(
    mcps_arg: str,
    browser_arg: bool,
) -> list[dict[str, Any]]:
    """Parse non-interactive MCP flags into a flat list of selected MCPs.

    Raises ValueError on unknown MCP IDs — silently ignoring them hides typos.
    """
    catalog_by_id = {m["id"]: m for m in MCP_CATALOG}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    unknown: list[str] = []

    for raw_id in mcps_arg.split(","):
        mcp_id = raw_id.strip().lower()
        if not mcp_id:
            continue
        if mcp_id not in catalog_by_id:
            unknown.append(mcp_id)
            continue
        if mcp_id in seen:
            continue
        selected.append(catalog_by_id[mcp_id])
        seen.add(mcp_id)

    if unknown:
        valid = ", ".join(catalog_by_id.keys())
        msg = f"unknown MCP id(s): {', '.join(unknown)}. Valid: {valid}"
        raise ValueError(msg)

    if browser_arg:
        selected.append(PLAYWRIGHT_MCP)

    return selected


_MEMORY_STACKS = (
    "none",
    "auto",
    "obsidian-only",
    "obsidian-graphify",
    "obsidian-graphify-rag",
)


def _normalize_memory(value: str | None) -> str | None:
    """Normalize a --memory value to a canonical memory_stack, or None if unset.

    Accepts the friendly ``obsidian`` alias for ``obsidian-only`` (#466).
    """
    if not value:
        return None
    return "obsidian-only" if value == "obsidian" else value


_LIFECYCLE_TIERS = ("github", "none")


def _normalize_lifecycle(value: str | None) -> str | None:
    """Normalize a --lifecycle value to a canonical tier, or None if unset (#476)."""
    return value or None


_DELIVERY = ("library", "service", "prototype")


_DELIVERY_ALIASES = {
    "service-or-app": "service",
    "app": "service",
    "prototype-or-none": "prototype",
    "none": "prototype",
}


_DELIVERY_SUMMARY = {
    "library": "a package/library published to a registry (PyPI/npm/crate)",
    "service": (
        "a deployed service or app — adds a Dockerfile + CI that builds the "
        "same container locally and in CI"
    ),
    "prototype": "just exploring / not sure yet — minimal setup, no deploy extras (default)",
}


def resolve_delivery(raw: str | None, language: str) -> str:
    """Normalize a delivery value; default 'prototype'.

    Rejects ``service`` + ``language none`` — there is no safe generic Dockerfile
    or test command for an unknown runtime (ADR-015). Raises ValueError otherwise.
    """
    value = (raw or "").strip().lower() or "prototype"
    value = _DELIVERY_ALIASES.get(value, value)
    if value not in _DELIVERY:
        valid = ", ".join(_DELIVERY)
        raise ValueError(f"invalid delivery '{raw}'. Choose one of: {valid}")
    if value == "service" and language == "none":
        raise ValueError(
            "delivery 'service' needs a language toolchain — pass "
            "--language python/node/go/rust, or choose 'prototype'"
        )
    return value


_DEPLOY_TARGETS = ("none", "cloud-run", "fly", "k8s", "registry", "custom")


_DEPLOY_CONTAINER = ("cloud-run", "fly", "k8s", "custom")


_DEPLOY_OIDC = ("cloud-run",)


_DEPLOY_SUMMARY = {
    "none": "my platform/PaaS deploys it, or not deployed via Actions yet (default)",
    "cloud-run": "Google Cloud Run (build one image, ship that exact image to prod)",
    "fly": "Fly.io (build one image, ship that exact image to prod)",
    "k8s": "Kubernetes (kubectl/helm set image to the built image)",
    "registry": ("publish the image to GitHub Container Registry (GHCR) only — not a deployment"),
    "custom": "container deploy with a TODO ship step you fill in",
}


def resolve_deploy(raw: str | None, delivery: str) -> str:
    """Normalize a deploy target; default 'none'.

    Deploy targets apply only to ``delivery=service`` — a non-'none' target on a
    library/prototype is a configuration error. Raises ValueError otherwise.
    """
    value = (raw or "").strip().lower() or "none"
    if value not in _DEPLOY_TARGETS:
        valid = ", ".join(_DEPLOY_TARGETS)
        raise ValueError(f"invalid deploy target '{raw}'. Choose one of: {valid}")
    if value != "none" and delivery != "service":
        raise ValueError(
            "deploy targets apply only to delivery=service "
            f"(got delivery={delivery!r}). Use --delivery service, or --deploy none"
        )
    return value


_IAC_OPTIONS = ("none", "opentofu")


_IAC_ALIASES = {"tofu": "opentofu", "terraform": "opentofu"}


_IAC_SUMMARY = {
    "none": "no infrastructure-as-code scaffolding (default)",
    "opentofu": (
        "OpenTofu (open-source Terraform) starter under infra/ + a plan preview "
        "on each PR; applying stays manual"
    ),
}


def resolve_iac(raw: str | None) -> str:
    """Normalize an --iac value; default 'none'. Raises ValueError on an unknown tool.

    `tofu`/`terraform` alias to `opentofu` (we always emit plain HCL run by the
    OpenTofu binary — the license-safe default; ADR-015).
    """
    value = (raw or "").strip().lower() or "none"
    value = _IAC_ALIASES.get(value, value)
    if value not in _IAC_OPTIONS:
        valid = ", ".join(_IAC_OPTIONS)
        raise ValueError(f"invalid iac tool '{raw}'. Choose one of: {valid}")
    return value


_VALID_AGENTS = (
    "claude",
    "codex",
    "ollama",
    "cursor",
    "antigravity",
    "vscode",
    "amp",
    "junie",
)


_AGENT_SURFACES = (
    ("vscode", "VS Code (MCP config for the editor)"),
    ("cursor", "Cursor (generated hooks + MCP)"),
    ("antigravity", "Antigravity (skills layer + generated hooks/MCP)"),
    ("codex", "Codex (native overlay)"),
    ("amp", "Amp (skills layer + generated MCP config)"),
    ("junie", "Junie (skills layer + generated MCP config)"),
    ("ollama", "Ollama (portable AGENTS.md; full harness via --multi-model)"),
)


def resolve_agents(raw: str) -> list[str]:
    """Parse/validate an --agents value; claude is always included first."""
    selected = [a.strip().lower() for a in raw.split(",") if a.strip()]
    unknown = [a for a in selected if a not in _VALID_AGENTS]
    if unknown:
        msg = f"unknown agent(s): {', '.join(unknown)}. Valid: {', '.join(_VALID_AGENTS)}"
        raise ValueError(msg)
    ordered = ["claude"]
    ordered += [a for a in _VALID_AGENTS if a != "claude" and a in selected]
    return ordered


def agent_layers(agents: list[str]) -> list[str]:
    """Template layers contributed by the selected agents (no fallback)."""
    return overlay_layers(agents, no_plugin=False)


_PROFILES = ("individual", "standalone", "org")


_PROFILE_SUMMARY = {
    "individual": (
        "you maintain it — updates arrive through the project-init plugin, "
        "rules are advisory (default)"
    ),
    "standalone": (
        "everything copied into the repo, no plugin dependency — you apply "
        "updates yourself, rules stay advisory"
    ),
    "org": (
        "your organization runs a project-init fork and controls updates — "
        "rules are enforced server-side"
    ),
}


def _profile_delivery_no_plugin(profile: str, explicit_no_plugin: bool) -> bool:
    """Resolve copied-in vs plugin delivery for a profile.

    ``standalone`` is copied-in by definition; ``individual``/``org`` default to
    plugin delivery (``org``'s copied-in-on-EMU is decided host-side, #248). An
    explicit ``--no-plugin`` always forces copied-in.
    """
    return explicit_no_plugin or profile == "standalone"


def _profile_enforcement(profile: str) -> str:
    """Profile-derived enforcement default (the enforcing behavior lands in #251)."""
    return "hard" if profile == "org" else "advisory"


_LANGUAGE_COMMANDS: dict[str, tuple[str, str, str, str]] = {
    "python": (
        "uv run ruff check .",
        "uv run ruff format .",
        "uv run pytest",
        "uv run python -m {project_slug}",
    ),
    # node recipes call the tools directly (PI-180): a freshly scaffolded
    # project has no package.json scripts to back `bun run lint`/`format`.
    "node": ("bunx eslint .", "bunx @biomejs/biome format --write .", "bun test", "bun run start"),
    "go": ("golangci-lint run", "golangci-lint fmt", "go test ./...", "go run ."),
    "rust": (
        "cargo clippy -- -D warnings -D clippy::pedantic "
        "-D clippy::cognitive_complexity -D missing_docs",
        "cargo fmt",
        "cargo test",
        "cargo run",
    ),
}


def render_run_command(run_command: str, project_slug: str) -> str:
    """Fill ``{project_slug}`` in a language ``run_command``.

    Only the Python command uses the placeholder (``uv run python -m
    {project_slug}``), and a module name can't contain the hyphens ``slugify()``
    emits — so substitute the underscore module form. A no-op for the other
    languages, whose ``run_command`` has no ``{project_slug}``. Shared by the
    scaffold and upgrade/backfill paths so the module name can't drift back to
    the invalid kebab form on `project-init upgrade`.
    """
    return run_command.replace("{project_slug}", (project_slug or "my-app").replace("-", "_"))


def _build_variables(
    preset: dict[str, Any], inputs: ScaffoldInputs, target: Path | None = None
) -> dict[str, str]:
    """Assemble the template render context from the resolved inputs."""
    project_name = inputs.project_name
    project_description = inputs.project_description
    language = inputs.language
    selected_mcps = inputs.selected_mcps
    owner = inputs.owner
    license_choice = inputs.license_choice
    devcontainer = inputs.devcontainer
    mise = inputs.mise
    vscode = inputs.vscode
    agents = inputs.agents
    no_plugin = inputs.no_plugin
    # Memory backend variable contract (#466) — derived from the resolved
    # memory_stack, NOT the preset name/layers (which no longer carry obsidian/
    # graphify). none → all empty; obsidian-only → obsidian; obsidian-graphify →
    # obsidian + graphify. _backfill_variables and _migrate_semantic_config emit
    # the same table so scaffold + upgrade never diverge.
    memory_stack = inputs.memory
    # Tier 3 (obsidian-graphify-rag, ADR-024 §4) is a strict superset of tier 2,
    # so it lights up obsidian + graphify too, then adds the rag seam on top.
    is_rag = memory_stack == "obsidian-graphify-rag"
    has_obsidian = memory_stack in ("obsidian-only", "obsidian-graphify", "obsidian-graphify-rag")
    is_graphify = memory_stack in ("obsidian-graphify", "obsidian-graphify-rag")
    has_memory = memory_stack != "none"
    # GitHub lifecycle gate (#476, ADR-021): drives the lifecycle/lifecycle_fallback
    # overlays + every {{#if lifecycle}} block (settings hooks, pre-push branch
    # rule, AGENTS/project-init prose). Recorded so `upgrade` re-derives the same
    # set (PI-189); _backfill_variables / _migrate_semantic_config emit it too.
    has_lifecycle = inputs.lifecycle != "none"
    lint_command, format_command, test_command, run_command = _LANGUAGE_COMMANDS.get(
        language, ("", "", "", "")
    )

    # #628: one value answers "what Python is this project on" for mise.toml,
    # mypy.ini, and the CI matrix floor. A declared requires-python is the
    # source of truth (CI re-derives from it on every run); --python-version —
    # or the wizard's answer, which lands in the same field — supplies the
    # value when nothing declares one, and a contradicting flag was already
    # rejected by _reject_conflicting_python_version. Neither: oldest supported.
    python_floor = (
        _python_floor_from_pyproject(target)
        or inputs.python_version
        or SUPPORTED_PYTHON_VERSIONS[0]
    )

    return {
        "python_floor": python_floor,
        # #714: read back by gh_host.sh's review_cycles(); only rendered under
        # the {{#if lifecycle}} gate in config.yaml.tmpl.
        "review_cycles": str(inputs.review_cycles),
        "project_name": project_name,
        # Kebab-cased name for identifier-ish slots (deploy app-name stubs);
        # a name with no ASCII alphanumerics falls back to a generic slug.
        "project_slug": slugify(project_name) or "my-app",
        "project_description": project_description,
        "created_date": date.today().isoformat(),
        "project_init_version": __version__,
        "project_init_contract_version": CONTRACT_VERSION,
        "project_init_url": __repo_url__,
        # Host-aware plugin-marketplace source (ADR-013, #248) — replaces the
        # github.com-only removeprefix. Provides project_init_repo + _url +
        # _github/_enterprise flags so non-github.com forks get a valid source.
        **marketplace_source_vars(__repo_url__),
        # Version-record fields (#248): plugin version + the previous scaffolder
        # version (set on upgrade) for span detection (#250).
        "project_init_plugin_version": __plugin_version__,
        "project_init_version_prev": "",
        "language": language,
        # Delivery model (ADR-015): recorded in config; the parity bundle and
        # release/deploy overlays (later #316 tickets) gate on these flags.
        "delivery": inputs.delivery,
        "delivery_library": "true" if inputs.delivery == "library" else "",
        "delivery_service": "true" if inputs.delivery == "service" else "",
        "not_delivery_service": "" if inputs.delivery == "service" else "true",
        # Deploy overlay (ADR-015, opt-in): the deploy.yml / environments.yaml
        # templates gate on these. deploy_container = build-once-by-digest graph;
        # deploy_registry = publish-image-only; both imply deploy_enabled.
        "deploy_target": inputs.deploy,
        "deploy_enabled": "true" if inputs.deploy != "none" else "",
        "deploy_container": "true" if inputs.deploy in _DEPLOY_CONTAINER else "",
        "deploy_registry": "true" if inputs.deploy == "registry" else "",
        "deploy_cloud_run": "true" if inputs.deploy == "cloud-run" else "",
        "deploy_fly": "true" if inputs.deploy == "fly" else "",
        "deploy_k8s": "true" if inputs.deploy == "k8s" else "",
        # IaC overlay (ADR-015, opt-in): infra/ HCL skeleton + infra.yml gate on this.
        "iac": inputs.iac,
        "iac_enabled": "true" if inputs.iac != "none" else "",
        # Cloud-OIDC integration seam (#326): set whenever a deploy or IaC workflow
        # authenticates to a cloud via OIDC, so the contract doc ships for them.
        "cloud_oidc": ("true" if (inputs.deploy in _DEPLOY_OIDC or inputs.iac != "none") else ""),
        "memory_stack": memory_stack,
        "memory_tier": memory_tier(memory_stack),
        "memory": "true" if has_memory else "",
        # GitHub lifecycle tier (#476): the recorded value + the gate flag, plus
        # the inverse flag for the engine's else-less {{#if}} blocks (e.g. the
        # pre-push main/master remediation reads differently with the lifecycle
        # scripts absent), mirroring vscode_off / egress_ok.
        "lifecycle_tier": inputs.lifecycle,
        "lifecycle": "true" if has_lifecycle else "",
        "lifecycle_off": "" if has_lifecycle else "true",
        "installed_mcps": format_installed_mcps(selected_mcps),
        "installed_mcps_yaml": format_installed_mcps_yaml(selected_mcps),
        "lint_command": lint_command,
        "format_command": format_command,
        "test_command": test_command,
        "run_command": render_run_command(run_command, slugify(project_name)),
        # Docs tooling axis + Renovate gate (#477, ADR-022). Default-ON opt-outs;
        # recorded so `upgrade` re-derives the same set (PI-189). The mkdocs/typedoc
        # gates AND want_docs; renovate.json gates on renovate alone.
        "want_docs": "true" if inputs.want_docs else "",
        "renovate": "true" if inputs.renovate else "",
        # Governance (PI-145). license_holder falls back to the project name
        # so a LICENSE rendered without --owner still has a copyright line.
        # The leading "@" is required for CODEOWNERS (project_owner) but is a
        # GitHub-handle artifact in a legal copyright notice, so strip it for
        # the license holder only (PI-181).
        "project_owner": owner,
        "license": license_choice,
        "license_holder": (owner or project_name).removeprefix("@"),
        "created_year": date.today().strftime("%Y"),
        # Conditional block flags (truthy/falsy strings).
        "python": "true" if language == "python" else "",
        "node": "true" if language == "node" else "",
        "go": "true" if language == "go" else "",
        "rust": "true" if language == "rust" else "",
        "justfile": "true" if language != "none" else "",
        "devcontainer": "true" if devcontainer else "",
        # A service delivery (ADR-015) gets a devcontainer automatically; the
        # standalone --devcontainer flag still works for non-service projects.
        "want_devcontainer": "true" if (devcontainer or inputs.delivery == "service") else "",
        # Multi-agent support (PI-137): the agents list drives overlay layers
        # on upgrade re-render; per-agent flags gate conditional blocks.
        "agents": ",".join(agents),
        "codex": "true" if "codex" in agents else "",
        "ollama": "true" if "ollama" in agents else "",
        # Antigravity has a flag (it ships an .agents/skills layer + an AGENTS.md
        # support note, PI-386). No flag for vscode: its config is generated
        # from the `agents` list by surfaces.emit (PI-366), not by templates
        # ("vscode" here would also collide with the VS Code var). Cursor/Amp/
        # Junie flags gate only their AGENTS.md support-tier notes (2026-07 QA);
        # their config is likewise generated by surfaces.emit.
        "antigravity": "true" if "antigravity" in agents else "",
        "cursor": "true" if "cursor" in agents else "",
        "amp": "true" if "amp" in agents else "",
        "junie": "true" if "junie" in agents else "",
        # The guard adapter is needed by every surface that wires a hook to it
        # (codex + the GUI surfaces cursor/antigravity); PI-366.
        "multi_agent": "true"
        if any(a in agents for a in ("codex", "cursor", "antigravity"))
        else "",
        "other_agents": "true" if len(agents) > 1 else "",
        # Multi-model switching overlay (ADR-016, #351): gates the multi_model
        # layer; recorded in config.yaml's variables block so `upgrade` re-derives
        # the same layer set (PI-189), exactly like the agents overlay.
        "multi_model": "true" if inputs.multi_model else "",
        # AI-governance overlay (ADR-018, #410): gates the governance layer and is
        # recorded so `upgrade` re-derives the same set. Unlike multi_model it can
        # also come from a preset's [vars] (the `governed` preset) — the CLI flag
        # takes precedence, falling back to the preset var. Mirror this resolution
        # in overlay_layers() at the call sites (scaffold + upgrade) so the layer
        # and the recorded variable can never disagree.
        "governance": "true"
        if (inputs.governance or preset.get("vars", {}).get("governance"))
        else "",
        # Observability overlay (ADR-019, #404): gates the observability layer
        # and is recorded so `upgrade` re-derives the same set, exactly like
        # multi_model. A flag-only overlay (no preset var in v1).
        "observability": "true" if inputs.observability else "",
        # Distribution profile (ADR-013, #247): recorded + drives the delivery
        # and enforcement defaults. The enforcing behavior lands in #251.
        "profile": inputs.profile,
        "enforcement": _profile_enforcement(inputs.profile),
        # Single trunk: feature PRs target 'main'. Pinned to 'main' (not the live
        # default branch) so the rendered workflows and gh_host's base_branch()
        # agree. Templates that key off the trunk (ci.yml, validate-pr.yml,
        # start_issue.sh) consume this.
        "base_branch": "main",
        # No-egress mode (#258): omit the external official marketplace. egress_ok
        # is the inverse flag the template gates on (the engine has no else-branch).
        "no_egress": "true" if inputs.no_egress else "",
        "egress_ok": "" if inputs.no_egress else "true",
        # Plugin cutover (PI-165): inverse pair, same pattern as vscode_off.
        "plugin_mode": "" if no_plugin else "true",
        "no_plugin": "true" if no_plugin else "",
        "mise": "true" if mise else "",
        "vscode": "true" if vscode else "",
        # Inverse flag: the template engine has no else-branch, and without
        # --vscode the gitignore must keep personal .vscode/ fully ignored.
        "vscode_off": "" if vscode else "true",
        "graphify": "true" if is_graphify else "",
        "obsidian": "true" if has_obsidian else "",
        "rag": "true" if is_rag else "",
        "license_mit": "true" if license_choice == "mit" else "",
        "license_apache": "true" if license_choice == "apache-2.0" else "",
        "license_proprietary": "true" if license_choice == "proprietary" else "",
    }


def _resolve_inputs(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    target: Path,
    preset_memory: str = "obsidian-only",
    preset_lifecycle: str = "github",
) -> ScaffoldInputs | None:
    """Resolve all scaffold inputs from flags; None means prompt instead.

    Validation errors call ``parser.error`` (exits) BEFORE the target dir is
    created (PI-20), so a typo'd flag never leaves an empty dir behind.

    ``preset_memory`` is the chosen preset's memory_stack and ``preset_lifecycle``
    its lifecycle tier — the fallbacks when --memory / --lifecycle are not given
    (#466, #476); the flags win.
    """
    if not args.non_interactive:
        return None
    try:
        selected_mcps = _resolve_mcps_non_interactive(args.mcps, args.browser)
        # Only an absent flag (None) defaults to claude; an explicit value —
        # including `--agents ""` — is passed through so resolve_agents validates
        # it (an empty string still yields the always-included ["claude"]).
        agents = resolve_agents(args.agents if args.agents is not None else "claude")
    except ValueError as e:
        parser.error(str(e))
    profile = args.profile or "individual"
    no_plugin = _profile_delivery_no_plugin(profile, args.no_plugin)
    try:
        delivery = resolve_delivery(args.delivery, args.language or "none")
        deploy = resolve_deploy(args.deploy, delivery)
        iac = resolve_iac(args.iac)
    except ValueError as e:
        parser.error(str(e))
    # #714: the tier this run actually scaffolds — a preset may set it, with no
    # --lifecycle flag present (PR #717 review, cycle 2).
    effective_lifecycle = _normalize_lifecycle(args.lifecycle) or preset_lifecycle
    return ScaffoldInputs(
        project_name=args.name,
        project_description=args.description,
        language=args.language or "none",
        selected_mcps=selected_mcps,
        owner=args.owner,
        license_choice=args.license,
        devcontainer=args.devcontainer,
        mise=args.mise,
        vscode=args.vscode,
        agents=agents,
        no_plugin=no_plugin,
        profile=profile,
        no_egress=args.no_egress,
        python_version=args.python_version or "",
        review_cycles=_resolve_review_cycles(args, effective_lifecycle),
        delivery=delivery,
        deploy=deploy,
        iac=iac,
        multi_model=args.multi_model,
        governance=args.governance,
        observability=args.observability,
        memory=_normalize_memory(args.memory) or preset_memory,
        lifecycle=effective_lifecycle,
        want_docs=not args.no_docs,
        renovate=not args.no_renovate,
    )


def _resolve_preset_memory(preset: dict[str, Any], parser: argparse.ArgumentParser) -> str:
    """Normalize + validate a preset's ``memory_stack`` (#466).

    Normalizes the friendly ``obsidian`` alias and rejects a typo'd stack up
    front — otherwise a bad preset memory_stack silently yields a ``memory=true``
    config with no obsidian/graphify/rag gate set and zero memory files
    (PI review 2026-07).
    """
    raw = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    resolved = _normalize_memory(raw) or "obsidian-only"
    if resolved not in _MEMORY_STACKS:
        parser.error(
            f"preset {preset['name']!r} declares an invalid memory_stack "
            f"{raw!r}; valid: {', '.join(_MEMORY_STACKS)}"
        )
    return resolved


def _resolve_preset_lifecycle(preset: dict[str, Any], parser: argparse.ArgumentParser) -> str:
    """Validate a preset's ``lifecycle`` tier (#476).

    Only the exact string ``"none"`` disables the lifecycle downstream
    (``inputs.lifecycle != "none"``), so an off-meaning value — a TOML boolean
    ``false``, ``"off"``, a typo'd ``"None"`` — would silently ship the full
    lifecycle overlay, the opposite of the preset author's intent. Reject it up
    front instead (mirrors _resolve_preset_memory).
    """
    raw = preset.get("vars", {}).get("lifecycle", "github")
    if raw not in _LIFECYCLE_TIERS:
        parser.error(
            f"preset {preset['name']!r} declares an invalid lifecycle "
            f"{raw!r}; valid: {', '.join(_LIFECYCLE_TIERS)}"
        )
    # raw matched a tier in _LIFECYCLE_TIERS (all str), so str() is a no-op that
    # only narrows the JSON/TOML-sourced Any back to str for the checker.
    return str(raw)


def _text_field_error(flag: str, value: str, *, allow_empty: bool = False) -> str | None:
    """Return why *value* would corrupt config.yaml, or None if it is clean.

    Shared by the non-interactive gate (:func:`_validate_text_inputs`) and the
    wizard's per-field re-prompt, so an interactive user is corrected at the
    field instead of losing the whole wizard to ``parser.error`` at the end
    (PI review 2026-07). The returned message names *flag* without a ``--`` so
    each caller can prefix it as appropriate.
    """
    # name/description are required, single-line, human-facing fields: a value
    # that is empty or only whitespace slips past the `if not args.name` check
    # (a space is truthy) and renders literal blanks into pyproject.toml / docs.
    if not allow_empty and not value.strip():
        return f"{flag} must not be empty or whitespace-only"
    if (
        '"' in value
        or "\\" in value
        # DEL (0x7F) + the C1 control block (0x80-0x9F, which includes NEL 0x85)
        # are non-printable in the YAML spec — a strict parser (the descriptor
        # oracle + the orchestrator) rejects them even inside a double-quoted
        # scalar (PI-806, found via property-based test). 0x2028/0x2029 are
        # > 0x9F but Python's str.splitlines() breaks a single-line value on
        # them (PI-535). C0 (< 0x20) covers the rest.
        or any(
            ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F or ord(ch) in (0x2028, 0x2029) for ch in value
        )
    ):
        return (
            f"{flag} must not contain double-quotes, backslashes, newlines, or "
            "control/line-separator characters (they corrupt the generated config.yaml)"
        )
    return None
