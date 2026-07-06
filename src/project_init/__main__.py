"""CLI entry point for `project-init` and `uvx project-init`."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from project_init import __plugin_version__, __repo_url__, __version__
from project_init.mcps import (
    MCP_CATALOG,
    PLAYWRIGHT_MCP,
    format_installed_mcps,
    format_installed_mcps_yaml,
)
from project_init.scaffold import (
    CONTRACT_VERSION,
    TemplateRenderError,
    list_presets,
    load_preset,
    marketplace_source_vars,
    memory_tier,
    overlay_layers,
    scaffold,
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


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="project-init",
        description="Scaffold agentic-development infrastructure into a project.",
        epilog=(
            "Subcommands:\n"
            "  project-init upgrade [target] [--apply]        re-render from the "
            "recorded config and report drift (PI-142)\n"
            "  project-init add|remove <concern> [--target DIR]  toggle an overlay "
            "on an existing scaffold (#528)\n"
            "  project-init preset new <name> --extends <base>  author a company "
            "preset (#252)\n"
            "To scaffold INTO a directory whose name matches a subcommand, pass a "
            "path (e.g. ./upgrade), not the bare name."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        choices=["python", "node", "go", "rust", "none"],
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
        "--governance",
        action="store_true",
        help=(
            "Scaffold the opt-in AI-governance overlay (ADR-018): governance-as-"
            "code. Ships an AI usage policy, approved-tools / data-handling / "
            "code-provenance docs, a NIST RMF crosswalk, a system-card template + "
            "example, a generated AIBOM, and a presence-triggered CI gate "
            "(governance_gate.py, wired into the merge gate) — adopting NIST AI "
            "RMF / EU AI Act conventions. Off by default."
        ),
    )
    p.add_argument(
        "--observability",
        action="store_true",
        help=(
            "Scaffold the opt-in observability overlay (ADR-019): a file-based "
            "usage report. Parses Claude Code transcript JSONL plus a guarded "
            "hook self-log into a stdlib HTML report — no Docker, no OTEL, no "
            "egress. Off by default."
        ),
    )
    p.add_argument(
        "--memory",
        choices=[
            "none",
            "auto",
            "obsidian",
            "obsidian-only",
            "obsidian-graphify",
            "obsidian-graphify-rag",
        ],
        default=None,
        help=(
            "Memory backend (#466, #497, ADR-024) — a superset ladder: none (no memory — "
            "the vault-free `core` preset), auto (flat agent-fact files in .agents/memory/, "
            "no vault — pure files, installs nothing), obsidian (auto PLUS a human "
            "Obsidian vault; alias for obsidian-only), obsidian-graphify (obsidian "
            "PLUS a derived code knowledge graph for agents), or obsidian-graphify-rag "
            "(tier 3 — graphify PLUS a keyless on-device semantic/vector recall surface; "
            "run .agents/scripts/setup_rag.sh to install cocoindex-code — no API key, no "
            "container; worth it only at multi-project / monorepo scale). Overrides the "
            "preset's default."
        ),
    )
    p.add_argument(
        "--lifecycle",
        choices=["github", "none"],
        default=None,
        help=(
            "GitHub lifecycle tier (#476, ADR-021): github (default — ship the "
            "issue→branch→PR→review→merge automation: DAG guard hooks, lifecycle "
            "scripts, board/wiki/validation workflows, issue/PR templates, "
            "lifecycle skills) or none (decline it for a forge-agnostic or "
            "minimalist scaffold). Forge-portable quality hooks (commit-msg, "
            "gitleaks, lint/format gate, prod-safety) stay either way. Overrides "
            "the preset's default."
        ),
    )
    p.add_argument(
        "--mcps",
        default="",
        help="Comma-separated MCP IDs from the core catalog (e.g. context7)",
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
            "Comma-separated agents/surfaces the project supports: claude "
            "(always included), codex, ollama, cursor, antigravity, vscode, amp, "
            "junie. Codex gets a native overlay; antigravity gets an .agents/ "
            "skills layer + generated hooks/MCP; cursor gets generated hooks+MCP; "
            "amp/junie get a skills layer + generated MCP config; vscode gets MCP "
            "config; ollama is instructions-level only (PI-137, PI-366, PI-386, "
            "PI-397; antigravity hooks experimental)"
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
        "--no-docs",
        action="store_true",
        help=(
            "Skip the local docs-preview tooling config (#477, ADR-022): mkdocs.yml "
            "for a python project, typedoc.json for a node project. On by default; "
            "the per-language gate still applies (no docs config for go/none)"
        ),
    )
    p.add_argument(
        "--no-renovate",
        action="store_true",
        help=(
            "Skip renovate.json (#477, ADR-022): the Renovate dependency-update "
            "bot config. On by default — decline it if you use a different "
            "update mechanism or none"
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
    p.add_argument(
        "--list-presets",
        action="store_true",
        help="Print available presets and exit (machine-readable with --json) — for "
        "orchestrator-driven scaffolding (#510)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON result to stdout instead of the human "
        "summary (scaffold result, or the preset list with --list-presets); for a "
        "root orchestrator driving project-init (#510)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _prompt(label: str, default: str = "") -> str:
    from rich.prompt import Prompt

    return Prompt.ask(label, default=default) or default


def _prompt_choice(label: str, valid: tuple[str, ...], *, default: str) -> str:
    """Prompt for one of *valid*, case-insensitively, re-asking on a bad answer.

    Interactive counterpart to argparse ``choices``: typing ``Python`` or ``MIT``
    must not silently coerce to ``none`` — normalize case and re-prompt with the
    valid set instead (PI review 2026-07).
    """
    from rich.console import Console

    while True:
        value = _prompt(label, default=default).strip().lower()
        if value in valid:
            return value
        Console().print(f"[red]Invalid choice {value!r}. Valid: {', '.join(valid)}[/red]")


def _prompt_menu_index(question: str, count: int, *, default: int) -> int:
    """IntPrompt that re-asks until the answer is inside the 1..count menu.

    Interactive counterpart to _prompt_choice for numbered menus: a typo'd
    number must not silently become the default selection (2026-07 QA) —
    re-prompt with the valid range instead.
    """
    from rich.console import Console
    from rich.prompt import IntPrompt

    while True:
        choice = IntPrompt.ask(question, default=default)
        if 1 <= choice <= count:
            return choice
        Console().print(f"[red]Invalid choice {choice}. Enter a number between 1 and {count}.[/red]")


def _prompt_validated(label: str, *, default: str, flag: str, allow_empty: bool = False) -> str:
    """Prompt, re-asking until the value would not corrupt config.yaml.

    Interactive counterpart to _validate_text_inputs: a bad character is caught
    at the field so the user fixes it in place instead of completing the whole
    wizard only to hit ``parser.error`` and lose every answer (PI review).
    """
    from rich.console import Console

    console = Console()
    while True:
        value = _prompt(label, default=default)
        err = _text_field_error(flag, value, allow_empty=allow_empty)
        if err is None:
            return value
        console.print(f"[red]{err}[/red]")


def _default_preset_index(presets: list[dict]) -> int:
    """1-based index of the preset to default to at the interactive prompt.

    Presets are listed sorted by filename, so an opt-in overlay preset like
    `governed` (which sorts before `obsidian-*`) must NOT become the Enter
    default — that would silently enable a strictly-opt-in, off-by-default
    overlay for a user who just presses Enter (Codex review #415 P2). Prefer the
    documented default `obsidian-only`; otherwise the first preset that does not
    enable an opt-in overlay; otherwise position 1.
    """
    for i, p in enumerate(presets, 1):
        if p.get("name") == "obsidian-only":
            return i
    for i, p in enumerate(presets, 1):
        if not p.get("vars", {}).get("governance"):
            return i
    return 1


def _choose_preset_interactive(presets: list[dict]) -> dict:
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    # Value framing (#472, ADR-023): say what a preset *is* and that it's only a
    # starting point, so the choice is informed rather than blind.
    console.print(
        Panel(
            "A [bold]preset[/bold] is your starting bundle — it sets the default "
            "overlays (memory, lifecycle, toolchain).\n\n"
            "[cyan]Helps:[/cyan] pick the closest fit, then the prompts below let "
            "you still decline or add individual pieces.\n"
            "[dim]Default: the recommended obsidian-only preset. \"core\" is the "
            "leanest (no memory backend).[/dim]",
            title="Preset",
            border_style="cyan",
        )
    )
    console.print("[bold]Available presets:[/bold]")
    default_idx = _default_preset_index(presets)
    for i, p in enumerate(presets, 1):
        marker = "  [green](recommended)[/green]" if i == default_idx else ""
        console.print(f"  [cyan]{i}[/cyan]. {p['name']} — {p['description']}{marker}")
    console.print()

    choice = _prompt_menu_index("Choose a preset", len(presets), default=default_idx)
    return presets[choice - 1]


def _choose_mcps_interactive(catalog: list[dict]) -> list[dict]:
    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    console.print(
        "\n[bold]MCP servers[/bold] — optional plug-in tool servers your agent "
        "can call (Model Context Protocol):"
    )
    for i, m in enumerate(catalog, 1):
        console.print(f"  [cyan]{i}[/cyan]. {m['name']} — {m['description']}")
    console.print()

    while True:
        raw = Prompt.ask(
            "Choose MCPs (comma-separated numbers, or Enter to skip)",
            default="",
        )
        if not raw.strip():
            return []

        selected = []
        seen: set[str] = set()
        invalid: list[str] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            idx = int(part) - 1 if part.isdigit() else -1
            if 0 <= idx < len(catalog):
                if catalog[idx]["id"] not in seen:
                    selected.append(catalog[idx])
                    seen.add(catalog[idx]["id"])
            else:
                invalid.append(part)
        if invalid:
            # Mirror the non-interactive --mcps behavior: never silently drop
            # part of the user's selection (2026-07 QA) — re-ask instead.
            console.print(
                f"[red]Invalid selection(s): {', '.join(invalid)}. "
                f"Enter numbers 1-{len(catalog)}.[/red]"
            )
            continue
        return selected


def _choose_browser_interactive() -> bool:
    # A genuine selectable add-on, so it explains its value too (#472/ADR-023,
    # Codex review) — not a bare yes/no. _explain_and_confirm is defined below;
    # this runs at wizard time, after the module is fully loaded.
    return _explain_and_confirm(
        "Browser automation (Playwright MCP)",
        "Adds the [bold]Playwright MCP[/bold] so the agent can drive a real "
        "browser — navigate, click, fill forms, and screenshot.\n\n"
        "[cyan]Helps:[/cyan] end-to-end web testing, scraping, and visual checks "
        "from the agent.\n"
        "[dim]Cost: installs Playwright + a browser engine. Off by default.[/dim]",
        "Add Playwright (browser automation)?",
        default=False,
    )


def _choose_profile_interactive() -> str:
    """Present the three distribution profiles and what each bundles (#247, ADR-023)."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    console.print(
        Panel(
            "A [bold]profile[/bold] sets how this project receives project-init "
            "updates and how strictly its rules are enforced.\n\n"
            "[cyan]Helps:[/cyan] match the scaffold to who maintains it — a "
            "personal project, a self-contained repo, or an org fleet.\n"
            "[dim]Default: individual — right for a personal project.[/dim]",
            title="Distribution profile",
            border_style="cyan",
        )
    )
    for i, name in enumerate(_PROFILES, 1):
        console.print(f"  [cyan]{i}[/cyan]. {name} — {_PROFILE_SUMMARY[name]}")
    console.print()
    choice = _prompt_menu_index("Choose a profile", len(_PROFILES), default=1)
    return _PROFILES[choice - 1]


def _resolve_mcps_non_interactive(
    mcps_arg: str,
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

    if browser_arg:
        selected.append(PLAYWRIGHT_MCP)

    return selected


# Per-tier "you run later" next-step for the chosen memory backend (#497). Only
# obsidian-graphify needs a one-time install; the rest are pure files.
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


def _presets_payload(presets: list[dict]) -> list[dict]:
    """Machine-readable preset list for an orchestrator (#510).

    Name, description, and the default memory stack each preset scaffolds — enough
    for a root layer to choose a preset before driving a non-interactive scaffold.
    Each preset is re-resolved through ``load_preset`` so ``extends`` inheritance
    is applied (e.g. ``governed`` inherits ``obsidian-only``'s ``memory_stack``);
    reading the raw TOML would otherwise advertise the wrong stack (#511 review).
    """
    payload = []
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
) -> dict:
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
    args, target: Path, created: list[Path], preset: dict, variables: dict, inputs, conflicts
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


def _emit_preset_list(presets: list[dict], *, as_json: bool) -> None:
    """Print the preset list for `--list-presets` (#510): JSON array or a human line each."""
    if as_json:
        print(json.dumps(_presets_payload(presets)))
        return
    for p in _presets_payload(presets):
        print(f"{p['name']:<20} {p['description']}  [memory: {p['memory_stack']}]")


def _print_summary(
    target: Path, created: list[Path], preset_name: str, memory_stack: str = "none"
) -> None:
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

    next_step = _MEMORY_NEXT_STEPS.get(memory_stack, "")
    if next_step:
        body += f"\n[bold]Next:[/bold] {next_step}\n"

    # The emitted git hooks, lifecycle scripts, and CI workflows all assume a
    # git repo; say so instead of scaffolding into a bare dir silently
    # (2026-07 QA). Checked structurally (.git up the tree — a dir, or a file
    # for worktrees/submodules) — the scaffolder never shells out to git.
    if not any((p / ".git").exists() for p in (target, *target.resolve().parents)):
        body += (
            "\n[yellow]Note:[/yellow] this directory is not a git repository — "
            "the scaffolded git hooks and CI workflows assume one.\n"
            "  Run: [bold]git init && git add -A && git commit -m 'scaffold'[/bold]\n"
        )

    body += (
        "\n[bold]Start:[/bold] cd into the project and run [bold]claude[/bold] — "
        "it picks up CLAUDE.md and .agents/ automatically.\n"
    )

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


def _choose_multi_model_interactive() -> bool:
    """Explain multi-model switching + the alternatives, then ask (ADR-016, #352).

    States plainly what the overlay does, how it helps, and the honest
    alternatives (OpenAI/Codex is better in its native --agents harness;
    Ollama runs locally), so the user makes an informed choice or declines —
    declining leaves a clean project. Passing --multi-model (in either mode)
    pre-accepts via the flag and skips this; only an interactive run without the
    flag reaches here.
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm

    console = Console()
    body = (
        "Run other models [bold]through the Claude Code harness[/bold] via "
        "claude-code-router (CCR) — one terminal, live switching, and automatic "
        "[bold]cost-routing[/bold] (background work goes to a cheap model). Your "
        "hooks, CI gates, and standards stay identical — they run below the "
        "model.\n\n"
        "  [dim]claude[/dim]                            [dim]# opens as usual[/dim]\n"
        "  [dim]/model deepseek,deepseek-v4-flash[/dim] [dim]# switch mid-session, context kept[/dim]\n"
        "  [dim]/model ollama,qwen3-coder:30b[/dim]     [dim]# local model[/dim]\n\n"
        "[cyan]Helps:[/cyan] control cost / test models without leaving the terminal.\n"
        "[cyan]Alternatives:[/cyan] [bold]skip this if you only use Claude.[/bold]\n"
        "  • [bold]OpenAI/Codex[/bold] has a native harness "
        "([dim]--agents codex[/dim]) — better quality there; route it through CCR "
        "only for one-terminal convenience.\n"
        "  • [bold]Ollama[/bold] models also run natively/locally.\n"
        "  • Say yes and the scaffolded [dim]setup_models.sh[/dim] installs CCR "
        "(pinned), seeds the config, and can pull local models for you.\n"
        "[dim]Default: off — decline and nothing is added.[/dim]"
    )
    console.print(
        Panel(body, title="Multi-model switching (claude-code-router)", border_style="cyan")
    )
    return Confirm.ask("Set up multi-model switching via claude-code-router?", default=False)


def _choose_governance_interactive() -> bool:
    """Explain the AI-governance overlay, then ask (ADR-018, #410).

    States what the overlay ships — governance-as-code (AUP + approved-tools/
    data-handling docs, a system card + AIBOM, a presence-triggered CI gate that
    adopts NIST AI RMF / EU AI Act conventions) — so the user makes an informed
    choice or declines; declining leaves a clean project. Passing --governance
    pre-accepts via the flag and skips this. Most projects are not AI products,
    so it is strictly opt-in and off by default.
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm

    console = Console()
    body = (
        "Ship [bold]governance-as-code[/bold] — versioned, reviewed policy that "
        "travels with the repo — for projects that build or operate an AI "
        "system.\n\n"
        "[bold]Scaffolds today:[/bold]\n"
        "  [dim]AI_USAGE_POLICY.md[/dim]      [dim]# 1-page acceptable-use policy "
        "(NIST-aligned)[/dim]\n"
        "  [dim]approved-tools.md[/dim]       [dim]# allow/deny models, endpoints, data[/dim]\n"
        "  [dim]data-handling.md[/dim]        [dim]# what data may reach AI tools[/dim]\n"
        "  [dim]ai-code-provenance.md[/dim]   [dim]# attribution + licence checks[/dim]\n"
        "  [dim]NIST_RMF_CROSSWALK.md[/dim]   [dim]# maps to Govern/Map/Measure/Manage[/dim]\n"
        "  [dim]examples/SYSTEM_CARD[/dim]    [dim]# system-card template + filled example[/dim]\n"
        "  [dim]ai-bom.generated.md[/dim]     [dim]# AI bill of materials (AIBOM), "
        "regenerated each run[/dim]\n"
        "  [dim]governance_gate.py[/dim]      [dim]# presence-triggered CI gate (in the merge gate)[/dim]\n\n"
        "[cyan]Helps:[/cyan] answer \"what AI runs here, on what data, under whose "
        "sign-off\" for reviewers, customers, and regulators.\n"
        "[cyan]Adopts:[/cyan] NIST AI RMF, ISO/IEC 42001, EU AI Act, OWASP LLM/Agentic "
        "Top 10 — referenced, not re-authored.\n"
        "[cyan]Gate:[/cyan] validates every real SYSTEM_CARD.md and fails on missing/"
        "placeholder fields — inert until you write a card.\n"
        "[cyan]Note:[/cyan] most projects are not AI products — keep this off unless "
        "yours calls an LLM API over data.\n"
        "[dim]Default: off — decline and nothing is added.[/dim]"
    )
    console.print(Panel(body, title="AI governance (governance-as-code)", border_style="cyan"))
    return Confirm.ask("Set up the AI-governance overlay?", default=False)


def _choose_observability_interactive() -> bool:
    """Explain the observability overlay, then ask (ADR-019, #404).

    States what the overlay ships — a file-based usage report built from the
    Claude Code transcript JSONL and a guarded hook self-log, rendered to a
    stdlib HTML report (no Docker, no OTEL, no egress) — so the user makes an
    informed choice or declines; declining leaves a clean project. Passing
    --observability pre-accepts via the flag and skips this. Off by default.
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm

    console = Console()
    body = (
        "Get a [bold]file-based usage report[/bold] for your agent sessions — "
        "tokens, tool calls, and activity — with [bold]no Docker, no OTEL, and "
        "no egress[/bold]. Everything stays on disk.\n\n"
        "[bold]Scaffolds:[/bold]\n"
        "  [dim]usage_report.py[/dim]    [dim]# stdlib parser over transcript JSONL[/dim]\n"
        "  [dim]observability.sh[/dim]   [dim]# one command → an HTML report[/dim]\n"
        "  [dim]hook self-log[/dim]      [dim]# guarded, stdin-safe activity log[/dim]\n\n"
        "[cyan]Helps:[/cyan] see what your agents actually do without a backend.\n"
        "[dim]Default: off — decline and nothing is added.[/dim]"
    )
    console.print(Panel(body, title="Observability (file-based usage report)", border_style="cyan"))
    return Confirm.ask("Set up the observability overlay?", default=False)


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


def _choose_memory_interactive(default: str = "obsidian-only") -> str:
    """Explain the memory backends, then ask which to scaffold (#466).

    States what each backend ships and what it brings, so the user makes an
    informed choice or declines memory entirely (``none`` → the vault-free
    project). Passing --memory pre-selects and skips this. The default follows
    the chosen preset's memory stack.
    """
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    default_idx = _MEMORY_STACKS.index(default) + 1 if default in _MEMORY_STACKS else 3
    body = (
        "A [bold]memory backend[/bold] gives your agents a place to persist "
        "decisions, conventions, and session notes [bold]across conversations[/bold] "
        "— so context survives beyond a single chat. Everything stays on disk. "
        "Each rung is a [bold]superset[/bold] of the one above.\n\n"
        "[bold]1. none[/bold]      [dim]no memory — leanest; bring your own docs[/dim]\n"
        "            [dim]Installs now: nothing · You run later: nothing[/dim]\n"
        "[bold]2. auto[/bold]      [dim].agents/memory (flat agent facts) — no vault[/dim]\n"
        "            [dim]Installs now: files only · You run later: nothing[/dim]\n"
        "[bold]3. obsidian[/bold]  [dim]auto PLUS .agents/vault (markdown notes,[/dim]\n"
        "            [dim]browsable in Obsidian)[/dim]\n"
        "            [dim]Installs now: files only · You run later: nothing[/dim]\n"
        "[bold]4. obsidian-graphify[/bold]  [dim]obsidian PLUS a derived knowledge[/dim]\n"
        "            [dim]graph agents can query (Graphify)[/dim]\n"
        "            [dim]Installs now: files only · You run later:[/dim]\n"
        "            [dim]uv tool install graphifyy && .agents/scripts/setup_graphify.sh[/dim]\n"
        "            [dim](the package name really has two y's)[/dim]\n"
        "[bold]5. obsidian-graphify-rag[/bold]  [dim]graphify PLUS search-by-meaning[/dim]\n"
        "            [dim]over all notes+code, not just exact words (RAG)[/dim]\n"
        "            [dim]Installs now: files only · You run later:[/dim]\n"
        "            [dim].agents/scripts/setup_rag.sh (cocoindex-code —[/dim]\n"
        "            [dim]keyless, on-device; no container, no API key)[/dim]\n\n"
        "[cyan]Helps:[/cyan] agents recall why a decision was made weeks later;\n"
        "the RAG rung (option 5) is worth it only at [bold]multi-project /\n"
        "monorepo[/bold] scale — for one small/medium repo, vault + the graph +\n"
        "grep already win, so [bold]skip it[/bold].\n"
        f"[dim]Default: option {default_idx} ({default}) — your preset's stack. "
        "Choose 1 (none) and no memory is added at all.[/dim]"
    )
    console.print(Panel(body, title="Memory backend", border_style="cyan"))
    choice = _prompt_menu_index("Choose a memory backend", len(_MEMORY_STACKS), default=default_idx)
    return _MEMORY_STACKS[choice - 1]


_LIFECYCLE_TIERS = ("github", "none")


def _normalize_lifecycle(value: str | None) -> str | None:
    """Normalize a --lifecycle value to a canonical tier, or None if unset (#476)."""
    return value or None


def _choose_lifecycle_interactive(default: str = "github") -> str:
    """Explain the GitHub lifecycle tier, then ask whether to ship it (#476).

    States what the lifecycle automation ships and what it brings, so the user
    keeps it or declines for a forge-agnostic / minimalist scaffold. Passing
    --lifecycle pre-selects and skips this. The default follows the chosen
    preset's lifecycle tier.
    """
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    body = (
        "The [bold]GitHub lifecycle[/bold] tier ships project-init's flagship "
        "workflow — [bold]issue → branch → PR → review → merge[/bold], enforced "
        "by deterministic guard hooks so the steps can't be skipped or "
        "mis-ordered.\n\n"
        "[bold]1. github[/bold]  [dim]guard hooks that enforce the step order, "
        "lifecycle scripts[/dim]\n"
        "          [dim](start_issue/finish_pr/…), board+wiki+PR-validation "
        "workflows,[/dim]\n"
        "          [dim]issue/PR templates, and the matching skills[/dim]\n"
        "[bold]2. none[/bold]    [dim]not tied to GitHub, or you prefer your own "
        "flow — minimal[/dim]\n\n"
        "[cyan]Helps:[/cyan] every change is traceable to an issue and a "
        "reviewed PR; no accidental pushes to main.\n"
        "[dim]Default: github. Quality hooks (commit-msg, gitleaks secret scan, "
        "lint/format gate, prod-safety) stay either way.[/dim]"
    )
    console.print(Panel(body, title="GitHub lifecycle (issue → PR → merge)", border_style="cyan"))
    default_idx = _LIFECYCLE_TIERS.index(default) + 1 if default in _LIFECYCLE_TIERS else 1
    choice = _prompt_menu_index("Choose a lifecycle tier", len(_LIFECYCLE_TIERS), default=default_idx)
    return _LIFECYCLE_TIERS[choice - 1]


# Wizard-explanation standard (#472, ADR-023): every selectable concern explains
# its value before asking — what it ships · a "Helps:" line · the honest cost ·
# the safe default. Heavyweight concerns (memory, lifecycle, overlays) render a
# full rich.Panel; lightweight toolchain toggles use this shared helper so the
# wizard stays scannable while still explaining each one. The coverage test in
# test_wizard_explanations.py enumerates the concerns against the CLI flags so a
# new concern can't ship without an explanation.
def _explain_and_confirm(title: str, body: str, question: str, *, default: bool) -> bool:
    """Render a concise explanation Panel for a toolchain toggle, then ask."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm

    Console().print(Panel(body, title=title, border_style="cyan"))
    return Confirm.ask(question, default=default)


def _choose_devcontainer_interactive() -> bool:
    return _explain_and_confirm(
        "Devcontainer",
        "A [bold].devcontainer/[/bold] (base image + toolchain bootstrap) gives "
        "Codespaces, fresh clones, and remote agent sessions an identical, "
        "ready-to-run environment.\n\n"
        "[cyan]Helps:[/cyan] zero-setup onboarding; agents run in a known image.\n"
        "[dim]Cost: a container build on first open. Off by default.[/dim]",
        "Add a devcontainer (Codespaces / remote agent sessions)?",
        default=False,
    )


def _choose_mise_interactive() -> bool:
    return _explain_and_confirm(
        "Toolchain pinning (mise)",
        "A [bold]mise.toml[/bold] pins runtime/tool versions so every machine and "
        "CI run uses the same toolchain.\n\n"
        '[cyan]Helps:[/cyan] reproducible builds; no "works on my machine".\n'
        "[dim]Ownership: mise owns versions only (uv/bun own deps, just owns "
        "commands). Off by default.[/dim]",
        "Pin toolchain versions with mise (mise.toml)?",
        default=False,
    )


def _choose_vscode_interactive() -> bool:
    return _explain_and_confirm(
        "VS Code config",
        "Shared [bold].vscode/[/bold] config: recommended extensions + a minimal "
        "settings.json (format-on-save wired to the preset formatter).\n\n"
        "[cyan]Helps:[/cyan] consistent editor behavior across the team.\n"
        "[dim]Nothing personal is committed — only these two files. Off by default.[/dim]",
        "Add shared VS Code config (extensions + format-on-save)?",
        default=False,
    )


def _choose_docs_interactive(language: str) -> bool:
    tool = "mkdocs.yml" if language == "python" else "typedoc.json"
    return _explain_and_confirm(
        "Docs-preview config",
        f"A [bold]{tool}[/bold] config for a local documentation preview "
        f"({'mkdocs serve' if language == 'python' else 'typedoc'}).\n\n"
        "[cyan]Helps:[/cyan] browsable docs from your markdown/docstrings.\n"
        "[dim]Local-only — no publish workflow is included. Default: on.[/dim]",
        f"Include the local docs-preview config ({tool})?",
        default=True,
    )


def _choose_renovate_interactive() -> bool:
    return _explain_and_confirm(
        "Renovate",
        "A [bold]renovate.json[/bold] config for the Renovate bot — automated, "
        "grouped, scheduled dependency-update PRs (digests pinned).\n\n"
        "[cyan]Helps:[/cyan] dependencies stay current without manual bumps.\n"
        "[dim]Cost: needs the Renovate app/GitHub action enabled. On by default; "
        "decline with --no-renovate.[/dim]",
        "Include renovate.json (Renovate dependency-update bot)?",
        default=True,
    )


# (#472, ADR-023) The selectable concerns the wizard must explain before asking,
# mapped to the CLI flag `dest` that toggles each (docs/renovate are the opt-out
# flags --no-docs/--no-renovate). The coverage test cross-checks this against the
# argparse parser so a new concern can't ship without an explanation, and renders
# each concern's chooser to assert it actually states its value.
WIZARD_CONCERN_FLAGS: dict[str, str] = {
    "preset": "preset",
    "profile": "profile",
    "memory": "memory",
    "lifecycle": "lifecycle",
    "delivery": "delivery",
    "deploy": "deploy",
    "iac": "iac",
    "multi_model": "multi_model",
    "governance": "governance",
    "observability": "observability",
    "devcontainer": "devcontainer",
    "mise": "mise",
    "vscode": "vscode",
    "docs": "no_docs",
    "renovate": "no_renovate",
    "browser": "browser",
}

# Flags that are mechanical inputs (basic identity / distribution mechanics /
# catalog selections that self-describe in their own annotated lists), not
# value-laden concerns needing a "why you'd want it" panel. The coverage test
# asserts every parser flag is either a concern above or listed here, so adding a
# flag forces an explicit classification — the enumeration can't go stale.
WIZARD_MECHANICAL_FLAGS: frozenset[str] = frozenset(
    {
        "help",
        "target",
        "name",
        "description",
        "language",
        "owner",
        "license",
        "agents",
        "mcps",
        "no_plugin",
        "no_egress",
        "non_interactive",
        "strict",
        "list_presets",
        "json",
        "version",
    }
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
    empty = []
    for value, flag in ((args.preset, "--preset"), (args.name, "--name"), (args.description, "--description")):
        if value is None:
            missing.append(flag)
        elif not value.strip():
            # An explicit --name "" is a different mistake than a missing flag;
            # don't tell the user to pass a flag they already passed (2026-07 QA).
            empty.append(flag)
    problems = []
    if missing:
        problems.append(f"--non-interactive requires: {', '.join(missing)}")
    if empty:
        problems.append(f"must not be empty: {', '.join(empty)}")
    if problems:
        parser.error("; ".join(problems))


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


def _gather_mcps_interactive(cli_mcps: str, cli_browser: bool) -> list[dict]:
    """Resolve MCPs for the wizard: honor --mcps/--browser, else prompt (PI review).

    A bad ``--mcps`` id warns and falls back to the catalog rather than crashing
    the wizard mid-run.
    """
    if cli_mcps.strip():
        try:
            selected = _resolve_mcps_non_interactive(cli_mcps, cli_browser)
        except ValueError as e:
            from rich.console import Console

            Console().print(f"[red]{e}[/red] — choose from the catalog instead.")
        else:
            # --mcps pins the catalog picks, but browser automation is its own
            # concern (ADR-023) — still offer it when --browser was not given,
            # matching how devcontainer/mise/vscode still prompt in the same run.
            if not cli_browser and _choose_browser_interactive():
                selected = selected + [PLAYWRIGHT_MCP]
            return selected
    selected = _choose_mcps_interactive(MCP_CATALOG)
    if cli_browser or _choose_browser_interactive():
        selected = selected + [PLAYWRIGHT_MCP]
    return selected


def _gather_inputs_interactive(  # noqa: PLR0913 — wizard gatherer; args map to prompts
    default_name: str,
    *,
    no_plugin: bool,
    profile: str | None,
    no_egress: bool = False,
    cli_overlays: tuple[str | None, str | None, str | None, bool, bool, bool] = (
        None,
        None,
        None,
        False,
        False,
        False,
    ),
    memory_flag: str | None = None,
    preset_memory: str = "obsidian-only",
    lifecycle_flag: str | None = None,
    preset_lifecycle: str = "github",
    no_docs: bool = False,
    no_renovate: bool = False,
    cli_name: str | None = None,
    cli_description: str | None = None,
    cli_language: str | None = None,
    cli_owner: str = "",
    cli_license: str = "none",
    cli_mcps: str = "",
    cli_browser: bool = False,
    cli_devcontainer: bool = False,
    cli_mise: bool = False,
    cli_vscode: bool = False,
    cli_agents: str = "claude",
) -> ScaffoldInputs:
    """Prompt for the profile, project basics, MCPs, governance, and overlays.

    ``cli_overlays`` pre-seeds the overlay flags (delivery, deploy, iac,
    multi_model, governance, observability) from the CLI; the string slots may
    be None to prompt, and multi_model/governance/observability=True skip their
    prompts (ADR-016/ADR-018/ADR-019).

    The ``cli_*`` params pre-seed the basic-field prompts from the CLI so a mixed
    invocation like ``project-init --name x --mcps context7 --browser`` (without
    ``--non-interactive``) honors those flags instead of silently dropping them
    (PI review 2026-07): the string values become prompt defaults; ``--mcps``
    resolves non-interactively (falling back to the catalog on a bad id); and the
    store_true toggles (browser/devcontainer/mise/vscode) skip their prompt when
    set.
    """
    resolved_profile = profile or _choose_profile_interactive()
    no_plugin = _profile_delivery_no_plugin(resolved_profile, no_plugin)
    project_name = _prompt_validated("Project name", default=cli_name or default_name, flag="name")
    # No usable default exists for the description, so say it's required up
    # front — otherwise an accept-all-defaults user loops on a bare "Description"
    # prompt with no hint why Enter doesn't advance (2026-07 QA).
    project_description = _prompt_validated(
        "Description" if cli_description else "Description (required)",
        default=cli_description or "",
        flag="description",
    )
    language = _prompt_choice(
        "Language (python/node/go/rust/none)",
        ("python", "node", "go", "rust", "none"),
        default=cli_language or "none",
    )
    (
        delivery_flag,
        deploy_flag,
        iac_flag,
        multi_model_flag,
        governance_flag,
        observability_flag,
    ) = cli_overlays
    resolved_delivery, resolved_deploy, resolved_iac = _resolve_overlays_interactive(
        language, delivery_flag, deploy_flag, iac_flag
    )

    # MCP selection — honor --mcps/--browser if given, else catalog multi-select.
    selected_mcps = _gather_mcps_interactive(cli_mcps, cli_browser)

    # Governance (PI-145).
    owner = _prompt_validated(
        "Owner/team for CODEOWNERS + LICENSE (e.g. @org/team)",
        default=cli_owner or "",
        flag="owner",
        allow_empty=True,
    )
    license_choice = _prompt_choice(
        "License (mit/apache-2.0/proprietary/none)",
        ("mit", "apache-2.0", "proprietary", "none"),
        default=cli_license or "none",
    )

    # Toolchain toggles — each explains its value before asking (#472, ADR-023).
    # A store_true CLI flag pre-accepts the toggle and skips its prompt.
    devcontainer = cli_devcontainer or _choose_devcontainer_interactive()
    mise = cli_mise or _choose_mise_interactive()
    vscode = cli_vscode or _choose_vscode_interactive()
    # Docs tooling axis (#477, ADR-022). The --no-docs flag wins (skip the
    # prompt); otherwise default ON and only ask for the languages whose docs
    # config ships (mkdocs→python, typedoc→node) — other languages get no docs
    # file from the gate, so the question is skipped there.
    if no_docs:
        want_docs = False
    elif language in ("python", "node"):
        want_docs = _choose_docs_interactive(language)
    else:
        want_docs = True
    # Renovate dependency-update config (#477, ADR-022). --no-renovate wins.
    want_renovate = False if no_renovate else _choose_renovate_interactive()
    # Multi-model switching overlay (ADR-016, #351/#352). The flag pre-accepts it;
    # otherwise the wizard explains what it does + the alternatives, then asks.
    resolved_multi_model = multi_model_flag or _choose_multi_model_interactive()
    # AI-governance overlay (ADR-018, #410). The flag pre-accepts it; otherwise
    # the wizard explains what it ships, then asks (strictly opt-in).
    resolved_governance = governance_flag or _choose_governance_interactive()
    # Observability overlay (ADR-019, #404). The flag pre-accepts it; otherwise
    # the wizard explains what it ships, then asks (strictly opt-in).
    resolved_observability = observability_flag or _choose_observability_interactive()
    # Memory backend (#466). The --memory flag wins; otherwise the wizard explains
    # the backends and asks, defaulting to the chosen preset's memory stack.
    resolved_memory = memory_flag or _choose_memory_interactive(default=preset_memory)
    # GitHub lifecycle tier (#476). The --lifecycle flag wins; otherwise the
    # wizard explains it and asks, defaulting to the chosen preset's tier.
    resolved_lifecycle = lifecycle_flag or _choose_lifecycle_interactive(default=preset_lifecycle)
    if cli_agents and cli_agents != "claude":
        try:
            agents = resolve_agents(cli_agents)
        except ValueError as e:
            from rich.console import Console

            Console().print(f"[red]{e}[/red]")
            agents = _choose_agents_interactive()
    else:
        agents = _choose_agents_interactive()

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
        governance=resolved_governance,
        observability=resolved_observability,
        memory=resolved_memory,
        lifecycle=resolved_lifecycle,
        want_docs=want_docs,
        renovate=want_renovate,
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


def _choose_delivery_interactive(language: str) -> str:
    """Present the delivery options (ADR-015); default prototype.

    Re-prompts if the choice is invalid for the chosen language (a service needs
    a language toolchain).
    """
    from rich.console import Console

    console = Console()
    console.print("\n[bold]How is this delivered?[/bold]")
    for i, name in enumerate(_DELIVERY, 1):
        console.print(f"  {i}. [cyan]{name}[/cyan] — {_DELIVERY_SUMMARY[name]}")
    while True:
        choice = _prompt_menu_index("Choose a delivery model", len(_DELIVERY), default=3)
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
    "cloud-run": "Google Cloud Run (build one image, ship that exact image to prod)",
    "fly": "Fly.io (build one image, ship that exact image to prod)",
    "k8s": "Kubernetes (kubectl/helm set image to the built image)",
    "registry": (
        "publish the image to GitHub Container Registry (GHCR) only — not a deployment"
    ),
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

    console = Console()
    console.print("\n[bold]How is this service deployed?[/bold]")
    for i, name in enumerate(_DEPLOY_TARGETS, 1):
        console.print(f"  {i}. [cyan]{name}[/cyan] — {_DEPLOY_SUMMARY[name]}")
    choice = _prompt_menu_index("Choose a deploy target", len(_DEPLOY_TARGETS), default=1)
    return _DEPLOY_TARGETS[choice - 1]


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


def _choose_iac_interactive() -> str:
    """Present the IaC options (ADR-015); default none."""
    from rich.console import Console

    console = Console()
    console.print("\n[bold]Infrastructure-as-Code overlay?[/bold]")
    for i, name in enumerate(_IAC_OPTIONS, 1):
        console.print(f"  {i}. [cyan]{name}[/cyan] — {_IAC_SUMMARY[name]}")
    choice = _prompt_menu_index("Choose an IaC overlay", len(_IAC_OPTIONS), default=1)
    return _IAC_OPTIONS[choice - 1]


# claude/codex/ollama are CLI harnesses; cursor/antigravity/vscode/amp/junie get
# generated per-surface config (ADR-017 / PI-366). Antigravity/Amp/Junie also ship
# a skills layer (PI-386/397). Gemini CLI was removed (PI-386): its free/Pro/Ultra
# tiers were sunset 2026-06-18; Antigravity (agy) is the Google target.
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
    ("ollama", "Ollama (instructions-level only)"),
)

def _choose_agents_interactive() -> list[str]:
    """Present the agent/editor surfaces to scaffold for (ADR-017, #616)."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt

    console = Console()
    body = (
        "Project-init configures [bold]agent and editor surfaces[/bold] so they "
        "know your rules and hooks. [bold]Claude[/bold] is always supported.\n\n"
        "[cyan]Helps:[/cyan] pick only the tools you actually use to keep the "
        "generated config clean and focused.\n"
        "[dim]Default: vscode only (plus claude).[/dim]\n\n"
    )
    for i, (name, desc) in enumerate(_AGENT_SURFACES, 1):
        body += f"  [cyan]{i}[/cyan]. {name:<11} — [dim]{desc}[/dim]\n"

    console.print(Panel(body.rstrip(), title="Agent and Editor Surfaces", border_style="cyan"))

    while True:
        raw = Prompt.ask(
            "Choose surfaces (comma-separated numbers, or Enter for default)",
            default="1",
        )
        if not raw.strip():
            return ["claude", "vscode"]

        selected = ["claude"]
        invalid = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            idx = int(part) - 1 if part.isdigit() else -1
            if 0 <= idx < len(_AGENT_SURFACES):
                selected.append(_AGENT_SURFACES[idx][0])
            else:
                invalid.append(part)

        if invalid:
            console.print(
                f"[red]Invalid selection(s): {', '.join(invalid)}. "
                f"Enter numbers 1-{len(_AGENT_SURFACES)}.[/red]"
            )
            continue
        
        # Keep list unique but stable
        return list(dict.fromkeys(selected))


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


# Per-language tooling commands (PI-16): (lint, format, test). Empty strings
# when no convention applies — templates should wrap usages in
# {{#if python}}/{{#if node}}/etc.
_LANGUAGE_COMMANDS: dict[str, tuple[str, str, str]] = {
    "python": ("uv run ruff check .", "uv run ruff format .", "uv run pytest"),
    # node recipes call the tools directly (PI-180): a freshly scaffolded
    # project has no package.json scripts to back `bun run lint`/`format`.
    "node": ("bunx eslint .", "bunx @biomejs/biome format --write .", "bun test"),
    "go": ("golangci-lint run", "golangci-lint fmt", "go test ./..."),
    "rust": (
        "cargo clippy -- -D warnings -D clippy::pedantic "
        "-D clippy::cognitive_complexity -D missing_docs",
        "cargo fmt",
        "cargo test",
    ),
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

    # -i/--interactive is meaningless without --apply (the per-file chooser only
    # runs while applying). Silently ignoring it left users thinking they were
    # driving an interactive apply when they got a read-only report — say so.
    if args.interactive and not args.apply:
        sys.stderr.write(
            "note: -i/--interactive only takes effect with --apply; this is a "
            "read-only drift report. Re-run with --apply -i to choose per file.\n"
        )

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


def _concern_main(argv: list[str], *, enable: bool) -> int:
    """Parse and run `project-init add|remove <concern>` (#528)."""
    import argparse

    from project_init.concerns import CONCERNS, MEMORY_STACKS, apply_concern
    from project_init.upgrade import (
        _enforce_clean_tree,
        _git_worktree_status,
        _print_undo_hint,
    )

    verb = "add" if enable else "remove"
    tail = "" if enable else " and deletes its files (byte-unmodified only)"
    p = argparse.ArgumentParser(
        prog=f"project-init {verb}",
        description=(
            f"{verb.capitalize()} a concern on an already-scaffolded project, without "
            f"re-running the wizard. Re-renders the shared wiring with the concern "
            f"flipped {'on' if enable else 'off'}{tail}."
        ),
    )
    p.add_argument("concern", help="one of: " + ", ".join(CONCERNS))
    if enable:
        stacks = ", ".join(s for s in MEMORY_STACKS if s != "none")
        p.add_argument("value", nargs="?", help=f"for `add memory`: a stack ({stacks})")
    p.add_argument("--target", default=".", help="scaffolded project dir (default: .)")
    p.add_argument("--apply", action="store_true", help="apply changes (default: dry-run report)")
    p.add_argument(
        "--allow-dirty",
        "--force",
        dest="allow_dirty",
        action="store_true",
        help="permit --apply on a dirty git work tree (default: refuse; --force is an alias)",
    )
    if not enable:
        src = p.add_mutually_exclusive_group()
        src.add_argument(
            "--purge",
            action="store_true",
            help="also DELETE orphaned source data (memory/vault notes) — destructive",
        )
        src.add_argument(
            "--export",
            metavar="DIR",
            help="move orphaned source data (memory/vault notes) to DIR before removing",
        )
    args = p.parse_args(argv)
    target = Path(args.target).resolve()
    value = getattr(args, "value", None)
    if value is not None and args.concern != "memory":
        # Only `add memory` takes a value; anything else here is almost always
        # a target path passed positionally (the old, wrong --help synopsis).
        p.error(
            f"concern '{args.concern}' takes no value — "
            f"did you mean --target {value}?"
        )
    if value is not None and args.concern == "memory" and value not in MEMORY_STACKS:
        # Same mistake for `add memory`: a path-looking non-stack value is a
        # mis-placed target, not a typo'd stack (Codex review, PR #601).
        stacks = ", ".join(s for s in MEMORY_STACKS if s != "none")
        hint = (
            f" — did you mean --target {value}?"
            if ("/" in value or value.startswith(".") or Path(value).is_dir())
            else ""
        )
        p.error(f"'{value}' is not a memory stack (valid: {stacks}){hint}")
    export_dir = Path(args.export).resolve() if getattr(args, "export", None) else None

    git_status = None
    if args.apply:
        git_status = _git_worktree_status(target)
        blocked = _enforce_clean_tree(
            git_status,
            allow_dirty=args.allow_dirty,
            target=target,
            reinvoke=f"project-init {verb} {args.concern} --apply",
            override_flag="--allow-dirty",
        )
        if blocked is not None:
            return blocked

    rc = apply_concern(
        target,
        args.concern,
        enable=enable,
        value=value,
        apply=args.apply,
        purge=getattr(args, "purge", False),
        export_dir=export_dir,
    )
    if args.apply and rc == 0:
        _print_undo_hint(git_status, target)
    return rc


def _build_variables(preset: dict, inputs: ScaffoldInputs, target: Path | None = None) -> dict[str, str]:
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
    lint_command, format_command, test_command = _LANGUAGE_COMMANDS.get(language, ("", "", ""))

    python_floor = "3.11"
    if target and (target / "pyproject.toml").exists():
        try:
            import tomllib
            with (target / "pyproject.toml").open("rb") as f:
                data = tomllib.load(f)
                req = data.get("project", {}).get("requires-python", "")
                if req:
                    import re
                    m = re.search(r'>=?\s*(\d+\.\d+)', req)
                    if m:
                        python_floor = m.group(1)
        except Exception:
            pass

    return {
        "python_floor": python_floor,
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
    args,
    parser,
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
        governance=args.governance,
        observability=args.observability,
        memory=_normalize_memory(args.memory) or preset_memory,
        lifecycle=_normalize_lifecycle(args.lifecycle) or preset_lifecycle,
        want_docs=not args.no_docs,
        renovate=not args.no_renovate,
    )


def _preset_main(argv: list[str]) -> int:
    """Parse and run `project-init preset new` — author a company preset (#252)."""
    from project_init.scaffold import generate_preset

    p = argparse.ArgumentParser(
        prog="project-init preset",
        description="Author company presets (inheritance, compat markers) — #252.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    new = sub.add_parser(
        "new",
        help="Generate a starter company preset that extends a base preset",
        description=(
            "Generate a starter company preset. The file is written into THIS "
            "project-init installation's templates/presets/ directory — the "
            "fork-source-of-truth model (#252): presets live with the scaffolder "
            "(commit them to your fork), not with the scaffolded projects, and "
            "a project scaffolded from one needs that same installation for "
            "later `upgrade`/`add`/`remove` runs."
        ),
    )
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
        # 0x85 (NEL), 0x2028 (LINE SEPARATOR), 0x2029 (PARAGRAPH SEPARATOR) are
        # > 0x20 so they slip past the C0 check, but Python's str.splitlines()
        # treats them as line breaks — they'd split a single-line YAML value
        # mid-parse on a later upgrade (PI-535).
        or any(ord(ch) < 0x20 or ord(ch) in (0x7F, 0x85, 0x2028, 0x2029) for ch in value)
    ):
        return (
            f"{flag} must not contain double-quotes, backslashes, newlines, or "
            "control/line-separator characters (they corrupt the generated config.yaml)"
        )
    return None


def _validate_text_inputs(inputs: ScaffoldInputs, parser: argparse.ArgumentParser) -> None:
    """Reject text fields that would corrupt the rendered config.yaml.

    name/description/owner are embedded into a double-quoted YAML string in
    config.yaml; a literal double-quote, backslash (an invalid/lossy YAML escape,
    as in a Windows-style path), newline, or control character there produces
    invalid YAML (which then breaks ``upgrade`` and descriptor reads). These are
    short single-line fields, so a clean rejection beats silent corruption
    (e2e sweep; Codex/Copilot review).
    """
    for flag, value, allow_empty in (
        ("name", inputs.project_name, False),
        ("description", inputs.project_description, False),
        ("owner", inputs.owner, True),
    ):
        err = _text_field_error(flag, value, allow_empty=allow_empty)
        if err:
            parser.error(f"--{err}")


def _validate_existing_config(target: Path, parser: argparse.ArgumentParser) -> None:
    """Reject a pre-existing, undecodable ``.agents/config.yaml`` before any writes.

    The scaffold/upgrade readers tolerate non-UTF-8 bytes (errors="ignore") so
    they don't crash mid-run, but ``write_scaffold_record`` rewrites the config
    with strict UTF-8 afterwards. Letting the scaffold proceed would fail *late*,
    after files are written — a partial-write state. Decode-check up front so the
    run aborts cleanly with nothing changed (PI-535, Codex review).
    """
    config = target / ".agents" / "config.yaml"
    if not config.is_file():
        return
    try:
        config.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        parser.error(
            f"existing {config} is not valid UTF-8 — fix or remove it before scaffolding "
            "(project-init reads and rewrites this file as UTF-8)"
        )


def _ensure_target_dir(target: Path, parser: argparse.ArgumentParser) -> None:
    """Create the target directory, rejecting a non-directory target.

    ``mkdir(exist_ok=True)`` would otherwise raise an uncaught FileExistsError
    when the target already exists as a file/symlink (e2e sweep).
    """
    if target.exists() and not target.is_dir():
        parser.error(f"target {target} exists and is not a directory")
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # e.g. PermissionError on a read-only parent
        parser.error(f"cannot create target {target}: {exc.strerror or exc}")


def main(argv: list[str] | None = None) -> int:
    """Run the scaffolding CLI; return the process exit code.

    A single top-level handler turns an EOF (non-TTY / piped stdin) or Ctrl-C at
    any interactive prompt — in the wizard or in `upgrade --apply -i` — into a
    clean exit 130 instead of a raw traceback (2026-07 review).
    """
    try:
        return _cli(list(sys.argv[1:]) if argv is None else list(argv))
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\naborted\n")
        return 130


def _resolve_preset_memory(preset: dict, parser: argparse.ArgumentParser) -> str:
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


def _resolve_preset_lifecycle(preset: dict, parser: argparse.ArgumentParser) -> str:
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
    return raw


# Subcommand names, single-sourced for _cli dispatch AND the bare-target
# rejection below — adding a subcommand must update both behaviors together.
_SUBCOMMANDS = ("upgrade", "add", "remove", "preset")


def _record_scaffold(target: Path, preset: dict, variables: dict, created: list[Path]) -> None:
    """Write the scaffold record and keep the created-list honest.

    The record lets a later `project-init upgrade` re-render faithfully and
    detect drift. Writing it can create .agents/config.yaml itself; count that
    so the summary matches what is actually on disk (2026-07 QA).
    """
    from project_init.upgrade import write_scaffold_record

    write_scaffold_record(target, preset["name"], variables, created)
    config_rel = Path(".agents/config.yaml")
    if config_rel not in created and (target / config_rel).exists():
        created.append(config_rel)


def _reject_bare_subcommand_target(raw_target: str, parser: argparse.ArgumentParser) -> None:
    """Refuse a bare subcommand word as the scaffold target.

    "project-init --flags upgrade" is far more likely a mis-ordered subcommand
    than a wish to scaffold into ./upgrade — the epilog promises the ./upgrade
    path form for the latter (2026-07 QA). Only the undecorated name is rejected.
    """
    if raw_target in _SUBCOMMANDS:
        parser.error(
            f"'{raw_target}' looks like the {raw_target!r} subcommand, which must "
            f"come first (project-init {raw_target} ...). To scaffold into a "
            f"directory named {raw_target!r}, pass the path form: ./{raw_target}"
        )


def _cli(argv: list[str]) -> int:
    """Dispatch a fully-formed argv to the scaffold CLI or a subcommand."""
    _dispatch = {
        "upgrade": lambda a: _upgrade_main(a),
        "add": lambda a: _concern_main(a, enable=True),
        "remove": lambda a: _concern_main(a, enable=False),
        "preset": lambda a: _preset_main(a),
    }
    assert set(_dispatch) == set(_SUBCOMMANDS)  # keep bare-target rejection in sync
    if argv[:1] and argv[0] in _dispatch:
        return _dispatch[argv[0]](argv[1:])
    parser = _build_parser()
    args = parser.parse_args(argv)

    presets = list_presets()
    if not presets:
        sys.stderr.write("error: no presets found in templates/presets/\n")
        return 1

    # Discovery for an orchestrator (#510): list presets and exit, before any
    # target/preset resolution (no --name/--target needed).
    if args.list_presets:
        _emit_preset_list(presets, as_json=args.json)
        return 0

    # --json promises a single clean JSON stdout line; interactive prompts/panels
    # would pollute it, so a scaffold --json run must be non-interactive (#511).
    if args.json and not args.non_interactive:
        parser.error(
            "--json requires --non-interactive (interactive prompts would corrupt JSON stdout)"
        )

    if args.non_interactive:
        _require_non_interactive_args(args, parser)

    _reject_bare_subcommand_target(args.target, parser)
    target = Path(args.target).resolve()

    # Select preset BEFORE creating the target directory — a typo'd --preset
    # should fail without leaving an empty dir behind.
    preset = _select_preset(args, parser, presets)
    # Memory backend fallback when --memory is absent (#466): the preset's stack
    # (obsidian-only/obsidian-graphify/core's "none"), default obsidian-only.
    preset_memory = _resolve_preset_memory(preset, parser)
    # Lifecycle-tier fallback when --lifecycle is absent (#476): the preset's
    # tier (a preset may set lifecycle = "none" to be minimal), default "github".
    preset_lifecycle = _resolve_preset_lifecycle(preset, parser)

    # Validate non-interactive args / gather interactive input BEFORE creating
    # the target directory (PI-20, PI-199: a bad flag OR a Ctrl-C at an
    # interactive prompt must not leave an empty dir behind).
    inputs = _resolve_inputs(args, parser, target, preset_memory, preset_lifecycle)
    if inputs is None:
        inputs = _gather_inputs_interactive(
            default_name=target.name,
            no_plugin=args.no_plugin,
            profile=args.profile,
            no_egress=args.no_egress,
            cli_overlays=(
                args.delivery,
                args.deploy,
                args.iac,
                args.multi_model,
                # Pre-seed governance from the CLI flag OR the chosen preset's
                # [vars] so a `governed`-preset run skips the prompt instead of
                # asking and then silently overriding the answer (the preset var
                # enables the layer regardless). Keeps the prompt honest and the
                # recorded variable aligned with the effective layer set.
                args.governance or bool(preset.get("vars", {}).get("governance")),
                args.observability,
            ),
            memory_flag=_normalize_memory(args.memory),
            preset_memory=preset_memory,
            lifecycle_flag=_normalize_lifecycle(args.lifecycle),
            preset_lifecycle=preset_lifecycle,
            no_docs=args.no_docs,
            no_renovate=args.no_renovate,
            # Pre-seed the basic-field prompts from the CLI so flags passed
            # without --non-interactive are honored, not dropped (PI review).
            cli_name=args.name,
            cli_description=args.description,
            cli_language=args.language,
            cli_owner=args.owner,
            cli_license=args.license,
            cli_mcps=args.mcps,
            cli_browser=args.browser,
            cli_devcontainer=args.devcontainer,
            cli_mise=args.mise,
            cli_vscode=args.vscode,
            cli_agents=args.agents,
        )
    _validate_text_inputs(inputs, parser)
    _validate_existing_config(target, parser)
    _ensure_target_dir(target, parser)

    # Agent overlays append to the preset's layers (PI-137); --no-plugin
    # restores the shared hooks/skills copies via the fallback layer
    # (PI-165, ADR-010 cutover). The preset dict is copied so the loaded
    # definition stays pristine.
    # Governance can be turned on by the CLI flag OR by the `governed` preset's
    # [vars] (ADR-018, #410). The flag wins; otherwise fall back to the preset
    # var. Resolve it here so the appended layer matches the recorded variable
    # that _build_variables() computes with the same precedence.
    governance_on = inputs.governance or bool(preset.get("vars", {}).get("governance"))
    extra_layers = overlay_layers(
        inputs.agents,
        no_plugin=inputs.no_plugin,
        memory_stack=inputs.memory,
        lifecycle=inputs.lifecycle != "none",
        multi_model=inputs.multi_model,
        governance=governance_on,
        observability=inputs.observability,
    )
    if extra_layers:
        preset = {**preset, "layers": list(preset["layers"]) + extra_layers}

    variables = _build_variables(preset, inputs, target)

    # Overwrite protection (PI-179): scaffold() decides per file whether it is
    # user-owned (first scaffold, an unresolved `.new` sibling still pending, or
    # a manifest-hash mismatch showing the user edited it since the last run —
    # 2026-07 review, C1) and writes a `.new` sibling rather than clobbering it.
    # Always pass the list so a re-run stays protected too.
    conflicts: list[tuple[Path, Path]] = []

    try:
        created = scaffold(target, preset, variables, strict=args.strict, conflicts=conflicts)
        _record_scaffold(target, preset, variables, created)
    except TemplateRenderError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2
    except OSError as e:
        # Any I/O failure during scaffolding (a read-only/full target, or a
        # missing/unreadable template) must surface a clean error, not a raw
        # traceback. Name the actual failing path + OS reason so a permission
        # problem reads differently from a missing template (Copilot review).
        where = f" ({e.filename})" if getattr(e, "filename", None) else ""
        sys.stderr.write(f"error: scaffolding into {target} failed: {e.strerror or e}{where}\n")
        return 1

    _emit_scaffold_output(args, target, created, preset, variables, inputs, conflicts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
