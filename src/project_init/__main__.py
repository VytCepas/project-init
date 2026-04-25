"""CLI entry point for `project-init` and `uvx project-init`."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from project_init import __repo_url__, __version__
from project_init.scaffold import list_presets, load_preset, scaffold


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
        "--non-interactive",
        action="store_true",
        help="Skip all prompts (requires --preset, --name, --description)",
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
    target.mkdir(parents=True, exist_ok=True)

    # Select preset.
    presets = list_presets()
    if not presets:
        sys.stderr.write("error: no presets found in templates/presets/\n")
        return 1

    if args.preset:
        preset = load_preset(args.preset)
    elif args.non_interactive:
        preset = presets[0]
    else:
        preset = _choose_preset_interactive(presets)

    # Gather variables.
    default_name = target.name
    if args.non_interactive:
        project_name = args.name
        project_description = args.description
        language = args.language or "none"
    else:
        project_name = _prompt("Project name", default=default_name)
        project_description = _prompt("Description", default="")
        language = _prompt("Language (python/node/go/none)", default="none")
        if language not in {"python", "node", "go", "none"}:
            language = "none"

    is_python = language == "python"
    is_lightrag = "lightrag" in preset.get("name", "")
    has_obsidian = "obsidian" in preset.get("layers", [])

    variables: dict[str, str] = {
        "project_name": project_name,
        "project_description": project_description,
        "created_date": date.today().isoformat(),
        "project_init_version": __version__,
        "project_init_url": __repo_url__,
        "language": language,
        "memory_stack": preset.get("vars", {}).get("memory_stack", "obsidian-only"),
        "installed_mcps": "none",
        "installed_mcps_yaml": "[]",
        "python_linter": "ruff" if is_python else "none",
        "test_framework": "pytest" if is_python else "none",
        # Conditional block flags (truthy/falsy strings).
        "python": "true" if is_python else "",
        "lightrag": "true" if is_lightrag else "",
        "obsidian": "true" if has_obsidian else "",
    }

    created = scaffold(target, preset, variables)
    _print_summary(target, created, preset["name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
