"""CLI entry point for `project-init` and `uvx project-init`."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from project_init import __plugin_version__, __repo_url__, __version__
from project_init.mcps import (
    DB_CATALOG,
    MCP_CATALOG,
    PLAYWRIGHT_MCP,
    format_installed_mcps,
    format_installed_mcps_yaml,
)
from project_init.scaffold import (
    TemplateRenderError,
    list_presets,
    load_preset,
    marketplace_source_vars,
    overlay_layers,
    scaffold,
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
    selected_mcps: list[dict]
    owner: str
    license_choice: str
    devcontainer: bool
    mise: bool
    vscode: bool
    agents: list[str]
    no_plugin: bool
    profile: str
    no_egress: bool = False
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


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="project-init",
        description="Scaffold agentic-development infrastructure into a project.",
        epilog=(
            "Subcommand: project-init upgrade [target] [--apply] — re-render "
            "from the recorded config and report drift (PI-142)."
        ),
    )
    p.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Target directory (default: current directory)",
    )
    p.add_argument("--preset", help="Preset name (skip interactive selection)")
    p.add_argument("--name", help="Project name")
    p.add_argument("--description", help="One-line project description")
    p.add_argument(
        "--language",
        choices=["python", "node", "go", "none"],
        help="Primary language/runtime",
    )
    p.add_argument(
        "--delivery",
        metavar="MODEL",
        default=None,
        # No argparse `choices`: resolve_delivery() validates so the documented
        # aliases (service-or-app, prototype-or-none) are accepted, not rejected
        # before normalization (PR #332 review).
        help=(
            "How the project is delivered (ADR-015): library (published package), "
            "service (deployed app — gets the container parity bundle), prototype "
            "(default — single trunk, nothing env-specific). service needs a "
            "language."
        ),
    )
    p.add_argument(
        "--deploy",
        metavar="TARGET",
        default=None,
        # Validated by resolve_deploy(); only meaningful for delivery=service.
        help=(
            "Deploy overlay for a service (ADR-015, opt-in): none (default — your "
            "platform/PaaS owns deploy, or not yet), cloud-run, fly, k8s, registry "
            "(publish image only), or custom. Requires --delivery service."
        ),
    )
    p.add_argument(
        "--iac",
        metavar="TOOL",
        default=None,
        # Validated by resolve_iac(); independent of delivery.
        help=(
            "Infrastructure-as-Code overlay (ADR-015, opt-in): none (default) or "
            "opentofu (emits an HCL skeleton + plan-on-PR workflow; apply is "
            "manual/gated). OpenTofu is the license-safe default vs BUSL Terraform."
        ),
    )
    p.add_argument(
        "--multi-model",
        action="store_true",
        help=(
            "Scaffold the opt-in multi-model switching overlay (ADR-016): a "
            "claude-code-router config + setup_models.sh installer to run other "
            "models (DeepSeek/Kimi/Ollama) through the Claude Code harness with "
            "live /model switching and background cost-routing. Clean by default."
        ),
    )
    p.add_argument(
        "--mcps",
        default="",
        help="Comma-separated MCP IDs from the core catalog (e.g. context7)",
    )
    p.add_argument(
        "--db",
        choices=["none", "postgres", "sqlite"],
        default="none",
        help="Database MCP to add (default: none)",
    )
    p.add_argument(
        "--browser",
        action="store_true",
        help="Add Playwright browser-automation MCP",
    )
    p.add_argument(
        "--license",
        choices=["mit", "apache-2.0", "proprietary", "none"],
        default="none",
        help="LICENSE file to render (default: none — no file)",
    )
    p.add_argument(
        "--owner",
        default="",
        help=(
            "Project owner/team: CODEOWNERS default owner (@user or "
            "@org/team), SECURITY contact, and LICENSE copyright holder"
        ),
    )
    p.add_argument(
        "--agents",
        default="claude",
        help=(
            "Comma-separated agents the project supports: claude (always "
            "included), codex, gemini, ollama. Codex/Gemini get native "
            "wiring overlays; ollama is instructions-level only (PI-137)"
        ),
    )
    p.add_argument(
        "--mise",
        action="store_true",
        help=(
            "Render mise.toml pinning toolchain versions (mise owns versions "
            "only; uv/bun own deps, just owns commands, .env owns environment)"
        ),
    )
    p.add_argument(
        "--vscode",
        action="store_true",
        help=(
            "Render .vscode/extensions.json + minimal settings.json "
            "(format-on-save wired to the preset formatter; nothing personal)"
        ),
    )
    p.add_argument(
        "--devcontainer",
        action="store_true",
        help=(
            "Render .devcontainer/ (base image + toolchain bootstrap) for "
            "Codespaces, fresh clones, and remote agent sessions"
        ),
    )
    p.add_argument(
        "--no-plugin",
        action="store_true",
        help=(
            "Copy hooks/skills into the project and wire them in settings "
            "instead of relying on the project-init-workflow plugin "
            "(offline / no-marketplace-trust fallback; ADR-010 cutover)"
        ),
    )
    p.add_argument(
        "--profile",
        choices=["individual", "standalone", "org"],
        default=None,
        help=(
            "Distribution profile (ADR-013): individual (default — plugin-first, "
            "track upstream, advisory), standalone (copied-in, owner-driven, "
            "pinned), org (fork source-of-truth, hard enforcement)"
        ),
    )
    p.add_argument(
        "--no-egress",
        action="store_true",
        help=(
            "Org no-egress mode: omit the external official marketplace "
            "(claude-plugins-official) and its plugins from scaffolded settings "
            "(ADR-013, #258). The project-init/fork marketplace is kept"
        ),
    )
    p.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip all prompts (requires --preset, --name, --description)",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any {{...}} placeholder survives rendering (PI-17)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _prompt(label: str, default: str = "") -> str:
    from rich.prompt import Prompt

    return Prompt.ask(label, default=default) or default


def _choose_preset_interactive(presets: list[dict]) -> dict:
    from rich.console import Console
    from rich.prompt import IntPrompt

    console = Console()
    console.print("\n[bold]Available presets:[/bold]")
    for i, p in enumerate(presets, 1):
        console.print(f"  [cyan]{i}[/cyan]. {p['name']} — {p['description']}")
    console.print()

    choice = IntPrompt.ask("Choose a preset", default=1)
    if choice < 1 or choice > len(presets):
        console.print("[red]Invalid choice. Using preset 1.[/red]")
        choice = 1
    return presets[choice - 1]


def _choose_mcps_interactive(catalog: list[dict]) -> list[dict]:
    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    console.print("\n[bold]MCPs to install:[/bold]")
    for i, m in enumerate(catalog, 1):
        console.print(f"  [cyan]{i}[/cyan]. {m['name']} — {m['description']}")
    console.print()

    raw = Prompt.ask(
        "Choose MCPs (comma-separated numbers, or Enter to skip)",
        default="",
    )
    if not raw.strip():
        return []

    selected = []
    seen: set[str] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(catalog) and catalog[idx]["id"] not in seen:
                selected.append(catalog[idx])
                seen.add(catalog[idx]["id"])
    return selected


def _choose_db_interactive() -> dict | None:
    from rich.console import Console
    from rich.prompt import IntPrompt

    console = Console()
    console.print("\n[bold]Database MCP:[/bold]")
    console.print("  [cyan]1[/cyan]. None")
    console.print("  [cyan]2[/cyan]. Postgres")
    console.print("  [cyan]3[/cyan]. SQLite")
    console.print()

    choice = IntPrompt.ask("Choose", default=1)
    if choice == 2:
        return DB_CATALOG["postgres"]
    if choice == 3:
        return DB_CATALOG["sqlite"]
    return None


def _choose_browser_interactive() -> bool:
    from rich.prompt import Confirm

    return Confirm.ask("\nAdd Playwright (browser automation)?", default=False)


def _choose_profile_interactive() -> str:
    """Present the three distribution profiles and what each bundles (#247)."""
    from rich.console import Console
    from rich.prompt import IntPrompt

    console = Console()
    console.print("\n[bold]Distribution profile[/bold] (ADR-013):")
    for i, name in enumerate(_PROFILES, 1):
        console.print(f"  [cyan]{i}[/cyan]. {name} — {_PROFILE_SUMMARY[name]}")
    console.print()
    choice = IntPrompt.ask("Choose a profile", default=1)
    if choice < 1 or choice > len(_PROFILES):
        console.print("[red]Invalid choice. Using individual.[/red]")
        choice = 1
    return _PROFILES[choice - 1]


def _resolve_mcps_non_interactive(
    mcps_arg: str,
    db_arg: str,
    browser_arg: bool,
) -> list[dict]:
    """Parse non-interactive MCP flags into a flat list of selected MCPs.

    Raises ValueError on unknown MCP IDs — silently ignoring them hides typos.
    """
    catalog_by_id = {m["id"]: m for m in MCP_CATALOG}
    selected: list[dict] = []
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

    if db_arg and db_arg != "none" and db_arg in DB_CATALOG:
        selected.append(DB_CATALOG[db_arg])

    if browser_arg:
        selected.append(PLAYWRIGHT_MCP)

    return selected


def _print_summary(target: Path, created: list[Path], preset_name: str) -> None:
    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    dirs = sorted({str(p.parent) for p in created if str(p.parent) != "."})
    files_count = len(created)

    body = f"[bold]Preset:[/bold] {preset_name}\n"
    body += f"[bold]Files:[/bold] {files_count} created/updated\n"
    body += f"[bold]Target:[/bold] {target.resolve()}\n\n"
    body += "[bold]Directories:[/bold]\n"
    for d in dirs[:15]:
        body += f"  {d}/\n"
    if len(dirs) > 15:
        body += f"  ... and {len(dirs) - 15} more\n"

    console.print()
    console.print(Panel(body.rstrip(), title="project-init", border_style="green"))
    console.print()


def _print_profile_notice(profile: str, *, no_plugin: bool, no_egress: bool) -> None:
    """Surface the resolved profile and its egress posture (#247/#258).

    Called on the non-interactive path so a default is never applied silently:
    it states the profile, the delivery, the egress posture, and enforcement.
    """
    from rich.console import Console

    delivery = "project-init copied in locally" if no_plugin else "plugin-first"
    # --no-plugin only copies project-init's own payload; the external official
    # marketplace stays enabled until no-egress mode (#258) omits it.
    egress = (
        "external official marketplace disabled (no egress)"
        if no_egress
        else "external official marketplace enabled (network egress)"
    )
    Console().print(
        f"[cyan]Profile:[/cyan] {profile} — {_PROFILE_SUMMARY[profile]}\n"
        f"[cyan]Delivery:[/cyan] {delivery}; {egress}; "
        f"[cyan]enforcement:[/cyan] {_profile_enforcement(profile)}"
    )


def _print_conflicts(conflicts: list[tuple[Path, Path]]) -> None:
    """Warn that user-owned files were kept; renders landed as .new siblings."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    body = (
        "Your existing files were [bold]not overwritten[/bold]. The new "
        "project-init version of each was written alongside as a sibling — "
        "review and merge what you want, then delete the sibling:\n\n"
    )
    body += "\n".join(f"  {original}  →  {sibling}" for original, sibling in sorted(conflicts))
    console.print(Panel(body, title="Existing files preserved", border_style="yellow"))
    console.print()


def _print_mcp_commands(selected: list[dict]) -> None:
    """Print the bare claude mcp add commands for the chosen MCPs."""
    if not selected:
        return

    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    body = "\n".join(m["command"] for m in selected)
    console.print(
        Panel(
            body,
            title="Next step — add MCPs (run in your project)",
            border_style="cyan",
        )
    )
    console.print()


def _require_non_interactive_args(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
    """Fail fast when --non-interactive is missing one of its required flags."""
    missing = []
    if not args.preset:
        missing.append("--preset")
    if not args.name:
        missing.append("--name")
    if not args.description:
        missing.append("--description")
    if missing:
        parser.error(f"--non-interactive requires: {', '.join(missing)}")


def _select_preset(
    args: argparse.Namespace, parser: argparse.ArgumentParser, presets: list[dict]
) -> dict:
    """Resolve the preset from flags or interactive choice (exits on bad --preset)."""
    if args.preset:
        try:
            return load_preset(args.preset)
        except ValueError as e:
            parser.error(str(e))
    # list_presets returns raw TOML; load the chosen one so `extends` inheritance
    # and the compat marker are resolved before scaffolding (#252).
    chosen = presets[0] if args.non_interactive else _choose_preset_interactive(presets)
    try:
        return load_preset(chosen["name"])
    except ValueError as e:
        parser.error(str(e))


def _resolve_iac_interactive(iac: str | None) -> str:
    """Resolve the IaC overlay for the interactive path: validate a flag, else prompt."""
    if iac:
        try:
            return resolve_iac(iac)
        except ValueError as e:
            from rich.console import Console

            Console().print(f"[red]{e}[/red]")
    return _choose_iac_interactive()


def _resolve_overlays_interactive(
    language: str, delivery: str | None, deploy: str | None, iac: str | None
) -> tuple[str, str, str]:
    """Resolve (delivery, deploy, iac) for the interactive path.

    A passed flag is validated; on a conflict (e.g. service + language none) or
    no flag, we prompt — never crash (the non-interactive path turns the same
    error into a parser.error). Deploy applies only to services; IaC is
    independent of delivery.
    """
    from rich.console import Console

    resolved_delivery = None
    if delivery:
        try:
            resolved_delivery = resolve_delivery(delivery, language)
        except ValueError as e:
            Console().print(f"[red]{e}[/red]")
    if resolved_delivery is None:
        resolved_delivery = _choose_delivery_interactive(language)

    resolved_iac = _resolve_iac_interactive(iac)

    if resolved_delivery != "service":
        if deploy and deploy.strip().lower() not in ("", "none"):
            Console().print(
                f"[yellow]--deploy {deploy} ignored: deploy targets apply only to "
                f"delivery=service (this is {resolved_delivery}).[/yellow]"
            )
        return resolved_delivery, "none", resolved_iac
    resolved_deploy = None
    if deploy:
        try:
            resolved_deploy = resolve_deploy(deploy, resolved_delivery)
        except ValueError as e:
            Console().print(f"[red]{e}[/red]")
    if resolved_deploy is None:
        resolved_deploy = _choose_deploy_interactive()
    return resolved_delivery, resolved_deploy, resolved_iac


def _gather_inputs_interactive(
    default_name: str,
    *,
    no_plugin: bool,
    profile: str | None,
    no_egress: bool = False,
    cli_overlays: tuple[str | None, str | None, str | None, bool] = (None, None, None, False),
) -> ScaffoldInputs:
    """Prompt for the profile, project basics, MCPs, governance, and overlays.

    ``cli_overlays`` pre-seeds the overlay flags (delivery, deploy, iac,
    multi_model) from the CLI; the string slots may be None to prompt, and
    multi_model=True skips the multi-model prompt (ADR-016, #351).
    """
    resolved_profile = profile or _choose_profile_interactive()
    no_plugin = _profile_delivery_no_plugin(resolved_profile, no_plugin)
    project_name = _prompt("Project name", default=default_name)
    project_description = _prompt("Description", default="")
    language = _prompt("Language (python/node/go/none)", default="none")
    if language not in {"python", "node", "go", "none"}:
        language = "none"
    delivery_flag, deploy_flag, iac_flag, multi_model_flag = cli_overlays
    resolved_delivery, resolved_deploy, resolved_iac = _resolve_overlays_interactive(
        language, delivery_flag, deploy_flag, iac_flag
    )

    # MCP selection — three steps.
    selected_mcps = _choose_mcps_interactive(MCP_CATALOG)
    db_mcp = _choose_db_interactive()
    if db_mcp:
        selected_mcps = selected_mcps + [db_mcp]
    if _choose_browser_interactive():
        selected_mcps = selected_mcps + [PLAYWRIGHT_MCP]

    # Governance (PI-145).
    owner = _prompt("Owner/team for CODEOWNERS + LICENSE (e.g. @org/team)", default="")
    license_choice = _prompt("License (mit/apache-2.0/proprietary/none)", default="none")
    if license_choice not in {"mit", "apache-2.0", "proprietary", "none"}:
        license_choice = "none"

    from rich.prompt import Confirm

    devcontainer = Confirm.ask(
        "Add a devcontainer (Codespaces / remote agent sessions)?", default=False
    )
    mise = Confirm.ask("Pin toolchain versions with mise (mise.toml)?", default=False)
    vscode = Confirm.ask("Add shared VS Code config (extensions + format-on-save)?", default=False)
    # Multi-model switching overlay (ADR-016, #351). The flag pre-accepts it; the
    # richer init-step messaging lands in #352.
    resolved_multi_model = multi_model_flag or Confirm.ask(
        "Set up multi-model switching via claude-code-router "
        "(run DeepSeek/Kimi/Ollama through Claude Code, with cost-routing)?",
        default=False,
    )
    while True:
        agents_raw = _prompt(
            "Agents to support (claude always; add codex/gemini/ollama, comma-separated)",
            default="claude",
        )
        try:
            agents = resolve_agents(agents_raw)
            break
        except ValueError as e:
            from rich.console import Console

            Console().print(f"[red]{e}[/red]")
    return ScaffoldInputs(
        project_name=project_name,
        project_description=project_description,
        language=language,
        selected_mcps=selected_mcps,
        owner=owner,
        license_choice=license_choice,
        devcontainer=devcontainer,
        mise=mise,
        vscode=vscode,
        agents=agents,
        no_plugin=no_plugin,
        profile=resolved_profile,
        no_egress=no_egress,
        delivery=resolved_delivery,
        deploy=resolved_deploy,
        iac=resolved_iac,
        multi_model=resolved_multi_model,
    )


_DELIVERY = ("library", "service", "prototype")

# Aliases accepted from the CLI/menu so the wording in docs ("service-or-app",
# "prototype-or-none") still resolves to the canonical token.
_DELIVERY_ALIASES = {
    "service-or-app": "service",
    "app": "service",
    "prototype-or-none": "prototype",
    "none": "prototype",
}

_DELIVERY_SUMMARY = {
    "library": "a package/library published to a registry (PyPI/npm/crate)",
    "service": "a deployed service or app — gets the container parity bundle",
    "prototype": "a prototype / not sure yet — single trunk, nothing env-specific",
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
            "--language python/node/go, or choose 'prototype'"
        )
    return value


def _choose_delivery_interactive(language: str) -> str:
    """Present the delivery options (ADR-015); default prototype.

    Re-prompts if the choice is invalid for the chosen language (a service needs
    a language toolchain).
    """
    from rich.console import Console
    from rich.prompt import IntPrompt

    console = Console()
    console.print("\n[bold]How is this delivered?[/bold]")
    for i, name in enumerate(_DELIVERY, 1):
        console.print(f"  {i}. [cyan]{name}[/cyan] — {_DELIVERY_SUMMARY[name]}")
    while True:
        choice = IntPrompt.ask("Choose a delivery model", default=3)
        if choice < 1 or choice > len(_DELIVERY):
            console.print("[red]Invalid choice. Using prototype.[/red]")
            return "prototype"
        try:
            return resolve_delivery(_DELIVERY[choice - 1], language)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")


_DEPLOY_TARGETS = ("none", "cloud-run", "fly", "k8s", "registry", "custom")

# Container-deploy targets get the build-once-by-digest deploy graph; registry is
# publication only; none = no Actions deploy overlay.
_DEPLOY_CONTAINER = ("cloud-run", "fly", "k8s", "custom")
# Targets whose scaffolded workflow uses cloud OIDC federation (GCP WIF / AWS
# role) — the cloud-integration seam doc (#326) applies. fly is token-based and
# k8s/custom auth varies, so they're excluded (the doc says others can reuse it).
_DEPLOY_OIDC = ("cloud-run",)

_DEPLOY_SUMMARY = {
    "none": "my platform/PaaS deploys it, or not deployed via Actions yet (default)",
    "cloud-run": "Google Cloud Run (build-once, promote the digest)",
    "fly": "Fly.io (build-once, promote the digest)",
    "k8s": "Kubernetes (kubectl/helm set image to the digest)",
    "registry": "publish the image to GHCR only — not a deployment",
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


def _choose_deploy_interactive() -> str:
    """Present the deploy options (ADR-015); default none. Shown only for services."""
    from rich.console import Console
    from rich.prompt import IntPrompt

    console = Console()
    console.print("\n[bold]How is this service deployed?[/bold]")
    for i, name in enumerate(_DEPLOY_TARGETS, 1):
        console.print(f"  {i}. [cyan]{name}[/cyan] — {_DEPLOY_SUMMARY[name]}")
    choice = IntPrompt.ask("Choose a deploy target", default=1)
    if choice < 1 or choice > len(_DEPLOY_TARGETS):
        console.print("[red]Invalid choice. Using none.[/red]")
        return "none"
    return _DEPLOY_TARGETS[choice - 1]


_IAC_OPTIONS = ("none", "opentofu")
_IAC_ALIASES = {"tofu": "opentofu", "terraform": "opentofu"}
_IAC_SUMMARY = {
    "none": "no infrastructure-as-code scaffolding",
    "opentofu": "OpenTofu (HCL) skeleton + plan-on-PR workflow; apply manual/gated",
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


def _choose_iac_interactive() -> str:
    """Present the IaC options (ADR-015); default none."""
    from rich.console import Console
    from rich.prompt import IntPrompt

    console = Console()
    console.print("\n[bold]Infrastructure-as-Code overlay?[/bold]")
    for i, name in enumerate(_IAC_OPTIONS, 1):
        console.print(f"  {i}. [cyan]{name}[/cyan] — {_IAC_SUMMARY[name]}")
    choice = IntPrompt.ask("Choose an IaC overlay", default=1)
    if choice < 1 or choice > len(_IAC_OPTIONS):
        console.print("[red]Invalid choice. Using none.[/red]")
        return "none"
    return _IAC_OPTIONS[choice - 1]


_VALID_AGENTS = ("claude", "codex", "gemini", "ollama")


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

# One-line summary of what each profile bundles — shown at selection time and in
# the non-interactive notice so the choice is never silent (ADR-013, #247).
_PROFILE_SUMMARY = {
    "individual": (
        "plugin-first (project-init + external official plugins), track upstream, "
        "advisory enforcement — today's default"
    ),
    "standalone": (
        "project-init payload copied in locally, owner-driven pinned updates, "
        "advisory enforcement (external official marketplace still enabled — "
        "full no-egress is the org mode, #258)"
    ),
    "org": ("fork as source-of-truth, host-adaptive delivery, hard (server-side) enforcement"),
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


# Per-language tooling commands (PI-16): (lint, format, test). Empty strings
# when no convention applies — templates should wrap usages in
# {{#if python}}/{{#if node}}/etc.
_LANGUAGE_COMMANDS: dict[str, tuple[str, str, str]] = {
    "python": ("uv run ruff check .", "uv run ruff format .", "uv run pytest"),
    # node recipes call the tools directly (PI-180): a freshly scaffolded
    # project has no package.json scripts to back `bun run lint`/`format`.
    "node": ("bunx eslint .", "bunx @biomejs/biome format --write .", "bun test"),
    "go": ("golangci-lint run", "gofmt -w .", "go test ./..."),
}


def _upgrade_main(argv: list[str]) -> int:
    """Parse and run the `project-init upgrade` subcommand (PI-142)."""
    from project_init.upgrade import (
        _enforce_clean_tree,
        _git_worktree_status,
        _print_undo_hint,
        run_upgrade,
    )

    p = argparse.ArgumentParser(
        prog="project-init upgrade",
        description=(
            "Re-render the recorded preset at the current template version "
            "and report drift. Without --apply no files are touched."
        ),
    )
    p.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Scaffolded project directory (default: current directory)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Apply non-conflicting changes; conflicts become .new siblings",
    )
    p.add_argument(
        "--no-plugin",
        action="store_true",
        help=(
            "Switch the project to the no-plugin fallback on this upgrade: "
            "re-render with copied hooks/skills + local settings wiring"
        ),
    )
    p.add_argument(
        "--non-interactive",
        action="store_true",
        help="Accepted for CLI symmetry — upgrade never prompts unless -i is given",
    )
    p.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help=(
            "With --apply, walk each changed/merged/conflicting file and choose "
            "update/skip/diff per file (#245). New-file additions still use "
            "--accept-new/--decline-new."
        ),
    )
    p.add_argument(
        "--accept-new",
        action="append",
        default=[],
        metavar="ID",
        help="Accept an addition group on --apply (repeatable; 'all' accepts every new group, #249)",
    )
    p.add_argument(
        "--decline-new",
        action="append",
        default=[],
        metavar="ID",
        help=(
            "Decline an addition group; recorded and suppressed on future "
            "--apply unless it changes materially ('all' declines every new group)"
        ),
    )
    p.add_argument(
        "--force",
        "--allow-dirty",
        action="store_true",
        dest="allow_dirty",
        help=(
            "Apply onto a dirty git work tree, bypassing the clean-tree guard "
            "(#242). Not recommended — the upgrade is then intermixed with your "
            "uncommitted edits in git diff. (--allow-dirty is an alias.)"
        ),
    )
    args = p.parse_args(argv)
    target = Path(args.target).resolve()

    # Clean-tree guard (#242): refuse --apply on a dirty git work tree so the
    # upgrade lands as one revertible diff. A CLI-layer precondition — kept out
    # of run_upgrade so programmatic callers manage their own safety.
    git_status = None
    if args.apply:
        git_status = _git_worktree_status(target)
        blocked = _enforce_clean_tree(git_status, allow_dirty=args.allow_dirty, target=target)
        if blocked is not None:
            return blocked

    rc = run_upgrade(
        target,
        apply=args.apply,
        no_plugin=args.no_plugin,
        accept_new=args.accept_new,
        decline_new=args.decline_new,
        interactive=args.interactive,
    )
    if args.apply and rc == 0:
        _print_undo_hint(git_status, target)
    return rc


def _build_variables(preset: dict, inputs: ScaffoldInputs) -> dict[str, str]:
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
    is_graphify = "graphify" in preset.get("name", "")
    has_obsidian = "obsidian" in preset.get("layers", [])
    lint_command, format_command, test_command = _LANGUAGE_COMMANDS.get(language, ("", "", ""))
    return {
        "project_name": project_name,
        "project_description": project_description,
        "created_date": date.today().isoformat(),
        "project_init_version": __version__,
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
        "memory_stack": preset.get("vars", {}).get("memory_stack", "obsidian-only"),
        "installed_mcps": format_installed_mcps(selected_mcps),
        "installed_mcps_yaml": format_installed_mcps_yaml(selected_mcps),
        "lint_command": lint_command,
        "format_command": format_command,
        "test_command": test_command,
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
        "justfile": "true" if language != "none" else "",
        "devcontainer": "true" if devcontainer else "",
        # A service delivery (ADR-015) gets a devcontainer automatically; the
        # standalone --devcontainer flag still works for non-service projects.
        "want_devcontainer": "true" if (devcontainer or inputs.delivery == "service") else "",
        # Multi-agent support (PI-137): the agents list drives overlay layers
        # on upgrade re-render; per-agent flags gate conditional blocks.
        "agents": ",".join(agents),
        "codex": "true" if "codex" in agents else "",
        "gemini": "true" if "gemini" in agents else "",
        "ollama": "true" if "ollama" in agents else "",
        "multi_agent": "true" if ("codex" in agents or "gemini" in agents) else "",
        "other_agents": "true" if len(agents) > 1 else "",
        # Multi-model switching overlay (ADR-016, #351): gates the multi_model
        # layer; recorded in config.yaml's variables block so `upgrade` re-derives
        # the same layer set (PI-189), exactly like the agents overlay.
        "multi_model": "true" if inputs.multi_model else "",
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
        "license_mit": "true" if license_choice == "mit" else "",
        "license_apache": "true" if license_choice == "apache-2.0" else "",
        "license_proprietary": "true" if license_choice == "proprietary" else "",
    }


def _resolve_inputs(args, parser, target: Path) -> ScaffoldInputs | None:
    """Resolve all scaffold inputs from flags; None means prompt instead.

    Validation errors call ``parser.error`` (exits) BEFORE the target dir is
    created (PI-20), so a typo'd flag never leaves an empty dir behind.
    """
    if not args.non_interactive:
        return None
    try:
        selected_mcps = _resolve_mcps_non_interactive(args.mcps, args.db, args.browser)
        agents = resolve_agents(args.agents)
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
    _print_profile_notice(profile, no_plugin=no_plugin, no_egress=args.no_egress)
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
        delivery=delivery,
        deploy=deploy,
        iac=iac,
        multi_model=args.multi_model,
    )


def _preset_main(argv: list[str]) -> int:
    """Parse and run `project-init preset new` — author a company preset (#252)."""
    from project_init.scaffold import generate_preset

    p = argparse.ArgumentParser(
        prog="project-init preset",
        description="Author company presets (inheritance, compat markers) — #252.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    new = sub.add_parser("new", help="Generate a starter company preset that extends a base preset")
    new.add_argument("name", help="New preset name (bare stem, e.g. acme-backend)")
    new.add_argument("--extends", required=True, help="Base preset to extend")
    new.add_argument("--description", default="", help="One-line description")
    new.add_argument(
        "--min-version",
        default=__version__,
        help="min_project_init_version compat marker (default: current version)",
    )
    args = p.parse_args(argv)
    try:
        path = generate_preset(
            args.name,
            extends=args.extends,
            description=args.description,
            version=args.min_version,
        )
    except ValueError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1
    sys.stdout.write(f"Created preset: {path}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the scaffolding CLI; return the process exit code."""
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if argv[:1] == ["upgrade"]:
        return _upgrade_main(argv[1:])
    if argv[:1] == ["preset"]:
        return _preset_main(argv[1:])
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.non_interactive:
        _require_non_interactive_args(args, parser)

    target = Path(args.target).resolve()

    # Select preset BEFORE creating the target directory — a typo'd --preset
    # should fail without leaving an empty dir behind.
    presets = list_presets()
    if not presets:
        sys.stderr.write("error: no presets found in templates/presets/\n")
        return 1
    preset = _select_preset(args, parser, presets)

    # Validate non-interactive args / gather interactive input BEFORE creating
    # the target directory (PI-20, PI-199: a bad flag OR a Ctrl-C at an
    # interactive prompt must not leave an empty dir behind).
    inputs = _resolve_inputs(args, parser, target)
    if inputs is None:
        inputs = _gather_inputs_interactive(
            default_name=target.name,
            no_plugin=args.no_plugin,
            profile=args.profile,
            no_egress=args.no_egress,
            cli_overlays=(args.delivery, args.deploy, args.iac, args.multi_model),
        )
    target.mkdir(parents=True, exist_ok=True)

    # Agent overlays append to the preset's layers (PI-137); --no-plugin
    # restores the shared hooks/skills copies via the fallback layer
    # (PI-165, ADR-010 cutover). The preset dict is copied so the loaded
    # definition stays pristine.
    extra_layers = overlay_layers(
        inputs.agents, no_plugin=inputs.no_plugin, multi_model=inputs.multi_model
    )
    if extra_layers:
        preset = {**preset, "layers": list(preset["layers"]) + extra_layers}

    variables = _build_variables(preset, inputs)

    # Overwrite protection (PI-179): scaffold() decides per file whether it is
    # user-owned (first scaffold, or an unresolved `.new` sibling still pending)
    # and writes a `.new` sibling rather than clobbering it. Always pass the list
    # so a re-run before the user merges a prior conflict stays protected too.
    conflicts: list[tuple[Path, Path]] = []
    try:
        created = scaffold(target, preset, variables, strict=args.strict, conflicts=conflicts)
    except TemplateRenderError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2

    # Record the scaffold inputs + rendered-content hashes so a later
    # `project-init upgrade` can re-render faithfully and detect drift.
    from project_init.upgrade import write_scaffold_record

    write_scaffold_record(target, preset["name"], variables, created)
    _print_summary(target, created, preset["name"])
    if conflicts:
        _print_conflicts(conflicts)
    _print_mcp_commands(inputs.selected_mcps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
