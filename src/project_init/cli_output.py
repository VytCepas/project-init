"""project-init CLI output — result payloads, summary panels, and tree rendering.

The `--json` payloads and the human summary/tree/notice printers, extracted from
the CLI spine so __main__ stays orchestration-only (PI-794). Imports rendering
helpers from console and presentation constants from variables; never imports the
wizard or subcommands.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rich.tree import Tree

from project_init.console import console, is_interactive
from project_init.scaffold import load_preset
from project_init.variables import (
    _PROFILE_SUMMARY,
    ScaffoldInputs,
    _profile_enforcement,
)

_MEMORY_NEXT_STEPS = {
    "none": "",
    "auto": "Memory: flat agent facts in .agents/memory/ — nothing to install.",
    "obsidian-only": "Memory: .agents/memory/ + Obsidian vault — open .agents/vault/ in Obsidian (optional).",
    "obsidian-graphify": (
        "Memory: build the code graph — run "
        "[bold]uv tool install graphifyy && .agents/scripts/setup_graphify.sh[/bold]"
    ),
    "obsidian-graphify-rag": (
        "Memory: code graph + semantic RAG — run "
        "[bold]uv tool install graphifyy && .agents/scripts/setup_graphify.sh[/bold], "
        "then [bold].agents/scripts/setup_rag.sh[/bold] (installs cocoindex-code — "
        "keyless, on-device; see .agents/docs/guides/using-rag.md)"
    ),
}


def _presets_payload(presets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Machine-readable preset list for an orchestrator (#510).

    Name, description, and the default memory stack each preset scaffolds — enough
    for a root layer to choose a preset before driving a non-interactive scaffold.
    Each preset is re-resolved through ``load_preset`` so ``extends`` inheritance
    is applied (e.g. ``governed`` inherits ``obsidian-only``'s ``memory_stack``);
    reading the raw TOML would otherwise advertise the wrong stack (#511 review).
    """
    payload: list[dict[str, Any]] = []
    for p in presets:
        name = p.get("name", "")
        try:
            resolved = load_preset(name) if name else p
        except ValueError:
            resolved = p
        payload.append(
            {
                "name": name,
                "description": resolved.get("description", p.get("description", "")),
                "memory_stack": resolved.get("vars", {}).get("memory_stack", "none"),
            }
        )
    return payload


def _scaffold_result_payload(
    target: Path, created: list[Path], preset_name: str, variables: dict[str, str]
) -> dict[str, Any]:
    """Machine-readable scaffold result for an orchestrator (#510).

    Carries the resolved memory descriptor (the same fields a root layer reads
    from `.agents/config.yaml`, #498) so the caller can register the new project
    without a second read. Path fields are present only at the tiers that ship
    them; `rag_endpoint` is null until a tool is wired (tier 3).
    """
    memory: dict[str, object] = {}
    if variables.get("memory"):
        memory = {
            "tier": variables.get("memory_tier", ""),
            "stack": variables.get("memory_stack", "none"),
            "memory_path": ".agents/memory",
        }
        if variables.get("obsidian"):
            memory["vault_path"] = ".agents/vault"
        if variables.get("graphify"):
            memory["graph_path"] = "graphify-out/graph.json"
        if variables.get("rag"):
            memory["rag_endpoint"] = None  # tier 3: present, unset until wired (#495)
    return {
        "target": str(target.resolve()),
        "preset": preset_name,
        "contract_version": variables.get("project_init_contract_version", ""),
        "memory": memory,
        "config": ".agents/config.yaml",
        "files_created": len(created),
    }


def _emit_scaffold_output(  # noqa: PLR0913 — one arg per piece of the result
    args: argparse.Namespace,
    target: Path,
    created: list[Path],
    preset: dict[str, Any],
    variables: dict[str, str],
    inputs: ScaffoldInputs,
    conflicts: list[tuple[Path, Path]],
) -> None:
    """Emit the post-scaffold result.

    A single JSON line (``--json``, #510) for an orchestrator, or the human rich
    panel + conflict/MCP notices otherwise.
    """
    if args.json:
        # Machine-readable result — sole stdout line, no rich panels. Conflicts
        # (unmerged `.new` siblings) are surfaced too.
        result = _scaffold_result_payload(target, created, preset["name"], variables)
        result["conflicts"] = [str(sibling) for _orig, sibling in conflicts]
        print(json.dumps(result))
        return
    # The advisory profile/egress notice is part of the success output: a
    # failing run must emit nothing but its error on stderr (2026-07 QA).
    # Interactive runs skip it as before — the wizard's prompts covered it.
    if args.non_interactive:
        _print_profile_notice(
            inputs.profile, no_plugin=inputs.no_plugin, no_egress=inputs.no_egress
        )
    _print_summary(target, created, preset["name"], variables.get("memory_stack", "none"))
    if conflicts:
        _print_conflicts(conflicts)
    _print_mcp_commands(inputs.selected_mcps)


def _emit_preset_list(presets: list[dict[str, Any]], *, as_json: bool) -> None:
    """Print the preset list for `--list-presets` (#510): JSON array or a human line each."""
    if as_json:
        print(json.dumps(_presets_payload(presets)))
        return
    for p in _presets_payload(presets):
        print(f"{p['name']:<20} {p['description']}  [memory: {p['memory_stack']}]")


def _print_summary(
    target: Path, created: list[Path], preset_name: str, memory_stack: str = "none"
) -> None:
    dirs = sorted({str(p.parent) for p in created if str(p.parent) != "."})
    files_count = len(created)
    next_step = _MEMORY_NEXT_STEPS.get(memory_stack, "")
    # The emitted git hooks, lifecycle scripts, and CI workflows all assume a
    # git repo; say so instead of scaffolding into a bare dir silently
    # (2026-07 QA). Checked structurally (.git up the tree — a valid dir, or a
    # file for worktrees/submodules) — the scaffolder never shells out to git.
    git_missing = not any(_is_git_marker(p / ".git") for p in (target, *target.resolve().parents))

    # Off a TTY (piped/captured/CI) render plain, unwrapped text — no borders to
    # word-wrap mid-phrase, and nothing decorative to bloat a transcript.
    if not is_interactive():
        _print_summary_plain(
            target, dirs, files_count, preset_name, next_step, git_missing=git_missing
        )
        return

    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table

    facts = Table.grid(padding=(0, 2))
    facts.add_column(style="key", justify="right")
    facts.add_column()
    facts.add_row("Preset", preset_name)
    facts.add_row("Files", f"[success]{files_count}[/success] created/updated")
    facts.add_row("Target", str(target.resolve()))

    rows: list[Any] = [facts, Rule(style="muted"), _directory_tree(dirs)]
    if next_step:
        rows.append(f"[heading]Next[/heading]  {next_step}")
    if git_missing:
        rows.append(
            "[warning]⚠ Not a git repository[/warning] — the scaffolded git hooks and "
            "CI workflows assume one.\n"
            "  Run [heading]git init && git add -A && git commit -m 'scaffold'[/heading]"
        )
    rows.append(
        "[heading]Start[/heading]  cd into the project and run [key]claude[/key] — "
        "it picks up CLAUDE.md and .agents/ automatically."
    )

    body = Table.grid(padding=(1, 0))
    body.add_column()
    for row in rows:
        body.add_row(row)

    console.print()
    console.print(
        Panel(
            body,
            title="[success]✔ project-init — scaffold complete[/success]",
            border_style="success",
            padding=(1, 2),
        )
    )
    console.print()


def _print_summary_plain(  # noqa: PLR0913 — one arg per rendered summary field
    target: Path,
    dirs: list[str],
    files_count: int,
    preset_name: str,
    next_step: str,
    *,
    git_missing: bool,
    limit: int = 24,
) -> None:
    """Colourless, unwrapped summary for non-TTY runs (uses builtin print)."""
    print()
    print("project-init — scaffold complete")
    print(f"  Preset: {preset_name}")
    print(f"  Files:  {files_count} created/updated")
    print(f"  Target: {target.resolve()}")
    for d in dirs[:limit]:
        print(f"    {d}/")
    if len(dirs) > limit:
        print(f"    ... and {len(dirs) - limit} more")
    if next_step:
        print(f"  Next: {next_step}")
    if git_missing:
        print(
            "  Note: this directory is not a git repository — the scaffolded git "
            "hooks and CI workflows assume one."
        )
        print("    Run: git init && git add -A && git commit -m 'scaffold'")
    print(
        "  Start: cd into the project and run claude — it picks up CLAUDE.md and "
        ".agents/ automatically."
    )
    print()


def _directory_tree(dirs: list[str], *, limit: int = 24) -> Tree:
    """A nested rich Tree of the created directories (flat list was fragile)."""
    from rich.tree import Tree

    root = Tree("[heading].[/heading]", guide_style="muted")
    nodes: dict[str, Tree] = {"": root}
    for d in dirs[:limit]:
        path = ""
        parent = root
        for part in d.split("/"):
            path = f"{path}/{part}" if path else part
            if path not in nodes:
                nodes[path] = parent.add(f"[info]{part}/[/info]")
            parent = nodes[path]
    if len(dirs) > limit:
        root.add(f"[muted]… and {len(dirs) - limit} more[/muted]")
    return root


def _is_git_marker(path: Path) -> bool:
    """Return whether *path* is a real .git marker, not a stray empty dir."""
    if path.is_file():
        return True
    if not path.is_dir():
        return False
    return (path / "HEAD").exists() or (path / "commondir").exists()


def _print_profile_notice(profile: str, *, no_plugin: bool, no_egress: bool) -> None:
    """Surface the resolved profile and its egress posture (#247/#258).

    Called on the non-interactive path so a default is never applied silently:
    it states the profile, the delivery, the egress posture, and enforcement.
    """
    delivery = "project-init copied in locally" if no_plugin else "plugin-first"
    # --no-plugin only copies project-init's own payload; the external official
    # marketplace stays enabled until no-egress mode (#258) omits it.
    egress = (
        "external official marketplace disabled (no egress)"
        if no_egress
        else "external official marketplace enabled (network egress)"
    )
    console.print(
        f"[cyan]Profile:[/cyan] {profile} — {_PROFILE_SUMMARY[profile]}\n"
        f"[cyan]Delivery:[/cyan] {delivery}; {egress}; "
        f"[cyan]enforcement:[/cyan] {_profile_enforcement(profile)}"
    )


def _print_conflicts(conflicts: list[tuple[Path, Path]]) -> None:
    """Warn that user-owned files were kept; renders landed as .new siblings."""
    from rich.panel import Panel

    body = (
        "Your existing files were [bold]not overwritten[/bold]. The new "
        "project-init version of each was written alongside as a sibling — "
        "review and merge what you want, then delete the sibling:\n\n"
    )
    body += "\n".join(f"  {original}  →  {sibling}" for original, sibling in sorted(conflicts))
    console.print(Panel(body, title="Existing files preserved", border_style="yellow"))
    console.print()


def _print_mcp_commands(selected: list[dict[str, Any]]) -> None:
    """Print the bare claude mcp add commands for the chosen MCPs."""
    if not selected:
        return

    from rich.panel import Panel

    body = "\n".join(m["command"] for m in selected)
    console.print(
        Panel(
            body,
            title="Next step — add MCPs (run in your project)",
            border_style="cyan",
        )
    )
    console.print()
