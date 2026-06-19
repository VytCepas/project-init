"""CLI entry point for `project-init` and `uvx project-init`."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
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
    # Branch model (ADR-014, #301): the git promotion chain, base first →
    # production last. Single-trunk (the default) is a length-1 chain.
    branch_chain: list[str] = field(default_factory=lambda: ["main"])


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
        "--branch-model",
        default=None,
        help=(
            "Git branch model (ADR-014): single-trunk (default), dev-test-main, "
            "dev-uat-preprod-main, or a custom comma chain base-first "
            "(e.g. dev,test,main). Opt-in; env branches are created post-clone "
            "by .claude/scripts/setup_env_branches.sh"
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


def _choose_branch_model_interactive() -> list[str]:
    """Present the branch-model options (ADR-014); default single-trunk."""
    from rich.console import Console
    from rich.prompt import IntPrompt

    console = Console()
    options = ["single-trunk", "dev-test-main", "dev-uat-preprod-main", "custom"]
    console.print("\n[bold]Branch model[/bold] (ADR-014 — opt-in, reworkable):")
    for i, name in enumerate(options, 1):
        console.print(f"  [cyan]{i}[/cyan]. {name} — {_BRANCH_MODEL_SUMMARY[name]}")
    console.print()
    choice = IntPrompt.ask("Choose a branch model", default=1)
    if choice < 1 or choice > len(options):
        console.print("[red]Invalid choice. Using single-trunk.[/red]")
        choice = 1
    if options[choice - 1] != "custom":
        return resolve_branch_chain(options[choice - 1])
    while True:
        raw = _prompt(
            "Custom chain, base first → production last (comma-separated, e.g. dev,test,main)",
            default="main",
        )
        try:
            return resolve_branch_chain(raw)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")


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


def _gather_inputs_interactive(
    default_name: str, *, no_plugin: bool, profile: str | None, no_egress: bool = False
) -> ScaffoldInputs:
    """Prompt for the profile, project basics, MCPs, governance, and overlays."""
    resolved_profile = profile or _choose_profile_interactive()
    no_plugin = _profile_delivery_no_plugin(resolved_profile, no_plugin)
    project_name = _prompt("Project name", default=default_name)
    project_description = _prompt("Description", default="")
    language = _prompt("Language (python/node/go/none)", default="none")
    if language not in {"python", "node", "go", "none"}:
        language = "none"

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
    branch_chain = _choose_branch_model_interactive()
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
        branch_chain=branch_chain,
    )


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


# Branch model (ADR-014): named promotion-chain presets + a validator. A chain is
# ordered base-first → production-last; single-trunk is just a length-1 chain.
_BRANCH_MODEL_PRESETS: dict[str, list[str]] = {
    "single-trunk": ["main"],
    "dev-test-main": ["dev", "test", "main"],
    "dev-uat-preprod-main": ["dev", "uat", "preprod", "main"],
}

_BRANCH_MODEL_SUMMARY = {
    "single-trunk": "one trunk (main); feature PRs target it — today's default",
    "dev-test-main": "promote dev → test → main by fast-forward",
    "dev-uat-preprod-main": "promote dev → uat → preprod → main by fast-forward",
    "custom": "your own ordered chain (base first → production last)",
}

# Long-lived env-branch names are kept simple (no slashes — those are for feature
# branches): a lowercase letter then letters/digits/dot/underscore/dash.
_BRANCH_NAME_RE = re.compile(r"^[a-z][a-z0-9._-]*$")


def resolve_branch_chain(raw: str) -> list[str]:
    """Parse/validate a --branch-model value into an ordered promotion chain.

    Accepts a preset name (single-trunk, dev-test-main, dev-uat-preprod-main) or a
    custom comma chain (base first → production last). Returns an ordered,
    de-duplicated list; a length-1 chain is single-trunk. Raises ValueError on an
    invalid branch name.
    """
    raw = (raw or "").strip()
    if not raw:
        return ["main"]
    if raw in _BRANCH_MODEL_PRESETS:
        return list(_BRANCH_MODEL_PRESETS[raw])
    names = [n.strip() for n in raw.split(",") if n.strip()]
    invalid = [n for n in names if not _BRANCH_NAME_RE.match(n)]
    if invalid:
        presets = ", ".join(_BRANCH_MODEL_PRESETS)
        msg = (
            f"invalid branch name(s): {', '.join(invalid)}. Use a preset "
            f"({presets}) or a custom chain of lowercase names like dev,test,main"
        )
        raise ValueError(msg)
    seen: set[str] = set()
    ordered: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered or ["main"]


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
        help="Accepted for CLI symmetry — upgrade never prompts",
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
        # Multi-agent support (PI-137): the agents list drives overlay layers
        # on upgrade re-render; per-agent flags gate conditional blocks.
        "agents": ",".join(agents),
        "codex": "true" if "codex" in agents else "",
        "gemini": "true" if "gemini" in agents else "",
        "ollama": "true" if "ollama" in agents else "",
        "multi_agent": "true" if ("codex" in agents or "gemini" in agents) else "",
        "other_agents": "true" if len(agents) > 1 else "",
        # Distribution profile (ADR-013, #247): recorded + drives the delivery
        # and enforcement defaults. The enforcing behavior lands in #251.
        "profile": inputs.profile,
        "enforcement": _profile_enforcement(inputs.profile),
        # Branch model (ADR-014, #301): the promotion chain. Single-trunk is a
        # length-1 chain; env branches are created post-clone. The engine has no
        # loop, so the chain renders as a flat string + flags.
        "branch_chain": ",".join(inputs.branch_chain),
        "branch_chain_yaml": ", ".join(f'"{b}"' for b in inputs.branch_chain),
        "base_branch": inputs.branch_chain[0],
        "production_branch": inputs.branch_chain[-1],
        "single_trunk": "true" if len(inputs.branch_chain) == 1 else "",
        "multi_env": "true" if len(inputs.branch_chain) > 1 else "",
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
        branch_chain = resolve_branch_chain(args.branch_model or "single-trunk")
    except ValueError as e:
        parser.error(str(e))
    profile = args.profile or "individual"
    no_plugin = _profile_delivery_no_plugin(profile, args.no_plugin)
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
        branch_chain=branch_chain,
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
        )
    target.mkdir(parents=True, exist_ok=True)

    # Agent overlays append to the preset's layers (PI-137); --no-plugin
    # restores the shared hooks/skills copies via the fallback layer
    # (PI-165, ADR-010 cutover). The preset dict is copied so the loaded
    # definition stays pristine.
    extra_layers = overlay_layers(inputs.agents, no_plugin=inputs.no_plugin)
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
