"""CLI entry point for `project-init` and `uvx project-init`."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from project_init import __repo_url__, __version__
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
    scaffold,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="project-init",
        description="Scaffold agentic-development infrastructure into a project.",
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
        help="Comma-separated MCP IDs from the core catalog (e.g. linear,github)",
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
        "--non-interactive",
        action="store_true",
        help="Skip all prompts (requires --preset, --name, --description)",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any {{...}} placeholder survives rendering (PI-17)",
    )
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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.non_interactive:
        missing = []
        if not args.preset:
            missing.append("--preset")
        if not args.name:
            missing.append("--name")
        if not args.description:
            missing.append("--description")
        if missing:
            parser.error(
                f"--non-interactive requires: {', '.join(missing)}"
            )

    target = Path(args.target).resolve()

    # Select preset BEFORE creating the target directory — a typo'd --preset
    # should fail without leaving an empty dir behind.
    presets = list_presets()
    if not presets:
        sys.stderr.write("error: no presets found in templates/presets/\n")
        return 1

    if args.preset:
        try:
            preset = load_preset(args.preset)
        except ValueError as e:
            parser.error(str(e))
    elif args.non_interactive:
        preset = presets[0]
    else:
        preset = _choose_preset_interactive(presets)

    target.mkdir(parents=True, exist_ok=True)

    # Gather variables.
    default_name = target.name
    if args.non_interactive:
        project_name = args.name
        project_description = args.description
        language = args.language or "none"
        try:
            selected_mcps = _resolve_mcps_non_interactive(
                args.mcps, args.db, args.browser
            )
        except ValueError as e:
            parser.error(str(e))
    else:
        project_name = _prompt("Project name", default=default_name)
        project_description = _prompt("Description", default="")
        language = _prompt("Language (python/node/go/none)", default="none")
        if language not in {"python", "node", "go", "none"}:
            language = "none"

        # MCP selection — three steps.
        core_mcps = _choose_mcps_interactive(MCP_CATALOG)
        db_mcp = _choose_db_interactive()
        want_browser = _choose_browser_interactive()

        selected_mcps = core_mcps
        if db_mcp:
            selected_mcps = selected_mcps + [db_mcp]
        if want_browser:
            selected_mcps = selected_mcps + [PLAYWRIGHT_MCP]

    is_python = language == "python"
    is_node = language == "node"
    is_go = language == "go"
    is_lightrag = "lightrag" in preset.get("name", "")
    has_obsidian = "obsidian" in preset.get("layers", [])

    # Per-language tooling commands (PI-16). Empty string when no convention
    # applies — templates should wrap usages in {{#if python}}/{{#if node}}/etc.
    if is_python:
        lint_command = "uv run ruff check ."
        format_command = "uv run ruff format ."
        test_command = "uv run pytest"
    elif is_node:
        lint_command = "bun run lint"
        format_command = "bun run format"
        test_command = "bun test"
    elif is_go:
        lint_command = "golangci-lint run"
        format_command = "gofmt -w ."
        test_command = "go test ./..."
    else:
        lint_command = ""
        format_command = ""
        test_command = ""

    variables: dict[str, str] = {
        "project_name": project_name,
        "project_description": project_description,
        "created_date": date.today().isoformat(),
        "project_init_version": __version__,
        "project_init_url": __repo_url__,
        "language": language,
        "memory_stack": preset.get("vars", {}).get("memory_stack", "obsidian-only"),
        "installed_mcps": format_installed_mcps(selected_mcps),
        "installed_mcps_yaml": format_installed_mcps_yaml(selected_mcps),
        "lint_command": lint_command,
        "format_command": format_command,
        "test_command": test_command,
        # Conditional block flags (truthy/falsy strings).
        "python": "true" if is_python else "",
        "node": "true" if is_node else "",
        "go": "true" if is_go else "",
        "lightrag": "true" if is_lightrag else "",
        "obsidian": "true" if has_obsidian else "",
    }

    try:
        created = scaffold(target, preset, variables, strict=args.strict)
    except TemplateRenderError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2
    _print_summary(target, created, preset["name"])
    _print_mcp_commands(selected_mcps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
