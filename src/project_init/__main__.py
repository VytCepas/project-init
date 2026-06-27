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
        "--governance",
        action="store_true",
        help=(
            "Scaffold the opt-in AI-governance overlay (ADR-018): governance-as-"
            "code. Ships the policy layer today — an AI usage policy, approved-"
            "tools / data-handling / code-provenance docs, and a NIST RMF "
            "crosswalk — adopting NIST AI RMF / EU AI Act conventions. The system "
            "card, AIBOM, and CI gate land in follow-ups. Off by default."
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
            "the vault-free `core` preset), auto (flat agent-fact files in .claude/memory/, "
            "no vault — pure files, installs nothing), obsidian (auto PLUS a human "
            "Obsidian vault; alias for obsidian-only), obsidian-graphify (obsidian "
            "PLUS a derived code knowledge graph for agents), or obsidian-graphify-rag "
            "(tier 3 — graphify PLUS a keyless on-device semantic/vector recall surface; "
            "run .claude/scripts/setup_rag.sh to install cocoindex-code — no API key, no "
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
    from rich.prompt import IntPrompt

    console = Console()
    # Value framing (#472, ADR-023): say what a preset *is* and that it's only a
    # starting point, so the choice is informed rather than blind.
    console.print(
        Panel(
            "A [bold]preset[/bold] is your starting bundle — it sets the default "
            "overlays (memory, lifecycle, toolchain).\n\n"
            "[cyan]Helps:[/cyan] pick the closest fit, then the prompts below let "
            "you still decline or add individual pieces.\n"
            "[dim]Default: the recommended Obsidian-only preset. `core` is the "
            "leanest (no memory backend).[/dim]",
            title="Preset",
            border_style="cyan",
        )
    )
    console.print("[bold]Available presets:[/bold]")
    for i, p in enumerate(presets, 1):
        console.print(f"  [cyan]{i}[/cyan]. {p['name']} — {p['description']}")
    console.print()

    default_idx = _default_preset_index(presets)
    choice = IntPrompt.ask("Choose a preset", default=default_idx)
    if choice < 1 or choice > len(presets):
        console.print(f"[red]Invalid choice. Using preset {default_idx}.[/red]")
        choice = default_idx
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
    "auto": "Memory: flat agent facts in .claude/memory/ — nothing to install.",
    "obsidian-only": "Memory: .claude/memory/ + Obsidian vault — open .claude/vault/ in Obsidian (optional).",
    "obsidian-graphify": (
        "Memory: build the code graph — run "
        "[bold]uv tool install graphifyy && .claude/scripts/setup_graphify.sh[/bold]"
    ),
    "obsidian-graphify-rag": (
        "Memory: code graph + semantic RAG — run "
        "[bold]uv tool install graphifyy && .claude/scripts/setup_graphify.sh[/bold], "
        "then [bold].claude/scripts/setup_rag.sh[/bold] (installs cocoindex-code — "
        "keyless, on-device; see .claude/docs/guides/using-rag.md)"
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
    from `.claude/config.yaml`, #498) so the caller can register the new project
    without a second read. Path fields are present only at the tiers that ship
    them; `rag_endpoint` is null until a tool is wired (tier 3).
    """
    memory: dict[str, object] = {}
    if variables.get("memory"):
        memory = {
            "tier": variables.get("memory_tier", ""),
            "stack": variables.get("memory_stack", "none"),
            "memory_path": ".claude/memory",
        }
        if variables.get("obsidian"):
            memory["vault_path"] = ".claude/vault"
        if variables.get("graphify"):
            memory["graph_path"] = "graphify-out/graph.json"
        if variables.get("rag"):
            memory["rag_endpoint"] = None  # tier 3: present, unset until wired (#495)
    return {
        "target": str(target.resolve()),
        "preset": preset_name,
        "contract_version": variables.get("project_init_contract_version", ""),
        "memory": memory,
        "config": ".claude/config.yaml",
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
        "Run other models [bold]through the Claude Code harness[/bold] — one "
        "terminal, live switching, and automatic [bold]cost-routing[/bold] "
        "(background work goes to a cheap model). Your hooks, CI gates, and "
        "standards stay identical — they run below the model.\n\n"
        "  [dim]claude[/dim]                          [dim]# opens as usual[/dim]\n"
        "  [dim]/model deepseek,deepseek-v4-flash[/dim] [dim]# switch mid-session, context kept[/dim]\n"
        "  [dim]/model ollama,qwen3-coder:30b[/dim]      [dim]# or qwen3-coder-next (newer)[/dim]\n"
        "  [dim]/model anthropic,claude-opus-4-8[/dim] [dim]# back to Claude[/dim]\n\n"
        "[cyan]Helps:[/cyan] control cost / test models without leaving the terminal.\n"
        "[cyan]Alternatives:[/cyan]\n"
        "  • [bold]OpenAI/Codex[/bold] has a native harness "
        "([dim]--agents codex[/dim]) — better quality there; route it through CCR "
        "only for one-terminal convenience.\n"
        "  • [bold]Ollama[/bold] models also run natively/locally.\n"
        "  • Say yes and the scaffolded [dim]setup_models.sh[/dim] installs CCR "
        "(pinned), seeds the config, and can pull local models for you.\n\n"
        "[cyan]Updates:[/cyan] the pinned CCR version flows from project-init via "
        "upgrade-as-PR; set up another way and you update it yourself.\n"
        "Clean by default — decline and nothing is added."
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
        "  [dim]AI_USAGE_POLICY.md[/dim]      [dim]# 1-page AUP (NIST-aligned)[/dim]\n"
        "  [dim]approved-tools.md[/dim]       [dim]# allow/deny models, endpoints, data[/dim]\n"
        "  [dim]data-handling.md[/dim]        [dim]# what data may reach AI tools[/dim]\n"
        "  [dim]ai-code-provenance.md[/dim]   [dim]# attribution + licence checks[/dim]\n"
        "  [dim]NIST_RMF_CROSSWALK.md[/dim]   [dim]# maps to Govern/Map/Measure/Manage[/dim]\n\n"
        "[cyan]Adopts:[/cyan] NIST AI RMF, ISO/IEC 42001, EU AI Act, OWASP LLM/Agentic "
        "Top 10 — referenced, not re-authored.\n"
        "[cyan]Coming:[/cyan] a system card + AIBOM and a presence-triggered CI gate "
        "(failing check) in follow-up increments.\n"
        "[cyan]Note:[/cyan] most projects are not AI products — keep this off unless "
        "yours calls an LLM API over data.\n"
        "Clean by default — decline and nothing is added."
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
        "Clean by default — decline and nothing is added."
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
    from rich.prompt import IntPrompt

    console = Console()
    body = (
        "A [bold]memory backend[/bold] gives your agents a place to persist "
        "decisions, conventions, and session notes [bold]across conversations[/bold] "
        "— so context survives beyond a single chat. Everything stays on disk. "
        "Each rung is a [bold]superset[/bold] of the one above (ADR-024).\n\n"
        "[bold]1. none[/bold]      [dim]no memory — leanest; bring your own docs[/dim]\n"
        "            [dim]Installs now: nothing · You run later: nothing[/dim]\n"
        "[bold]2. auto[/bold]      [dim].claude/memory (flat agent facts) — no vault[/dim]\n"
        "            [dim]Installs now: files only · You run later: nothing[/dim]\n"
        "[bold]3. obsidian[/bold]  [dim]auto PLUS .claude/vault (markdown notes,[/dim]\n"
        "            [dim]browsable in Obsidian)[/dim]\n"
        "            [dim]Installs now: files only · You run later: nothing[/dim]\n"
        "[bold]4. obsidian-graphify[/bold]  [dim]obsidian PLUS a derived knowledge[/dim]\n"
        "            [dim]graph agents can query (Graphify)[/dim]\n"
        "            [dim]Installs now: files only · You run later:[/dim]\n"
        "            [dim]uv tool install graphifyy && .claude/scripts/setup_graphify.sh[/dim]\n"
        "[bold]5. obsidian-graphify-rag[/bold]  [dim]graphify PLUS a semantic /[/dim]\n"
        "            [dim]vector recall surface over the whole corpus (RAG)[/dim]\n"
        "            [dim]Installs now: files only · You run later:[/dim]\n"
        "            [dim].claude/scripts/setup_rag.sh (cocoindex-code —[/dim]\n"
        "            [dim]keyless, on-device; no container, no API key)[/dim]\n\n"
        "[cyan]Helps:[/cyan] agents recall why a decision was made weeks later;\n"
        "the RAG rung (option 5, tier 3) adds cross-corpus semantic search worth\n"
        "it only at [bold]multi-project / monorepo[/bold] scale — for one small/medium\n"
        "repo, vault + the graph + grep already win, so [bold]skip it[/bold] (default off).\n"
        "Clean by default — pick [bold]none[/bold] and no memory is added."
    )
    console.print(Panel(body, title="Memory backend", border_style="cyan"))
    default_idx = _MEMORY_STACKS.index(default) + 1 if default in _MEMORY_STACKS else 3
    choice = IntPrompt.ask("Choose a memory backend", default=default_idx)
    idx = choice - 1 if 1 <= choice <= len(_MEMORY_STACKS) else default_idx - 1
    return _MEMORY_STACKS[idx]


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
    from rich.prompt import IntPrompt

    console = Console()
    body = (
        "The [bold]GitHub lifecycle[/bold] tier ships project-init's flagship "
        "workflow — [bold]issue → branch → PR → review → merge[/bold], enforced "
        "by deterministic guard hooks so the steps can't be skipped or "
        "mis-ordered.\n\n"
        "[bold]1. github[/bold]  [dim]DAG guard hooks, lifecycle scripts "
        "(start_issue/finish_pr/…),[/dim]\n"
        "          [dim]board+wiki+PR-validation workflows, issue/PR templates,[/dim]\n"
        "          [dim]and the create_issue/start_task/github_workflow skills[/dim]\n"
        "[bold]2. none[/bold]    [dim]decline it — forge-agnostic / minimalist; "
        "bring your own flow[/dim]\n\n"
        "[cyan]Helps:[/cyan] every change is traceable to an issue and a "
        "reviewed PR; no accidental pushes to main.\n"
        "[dim]Forge-portable quality hooks (commit-msg, gitleaks secret scan, "
        "lint/format gate, prod-safety) stay either way.[/dim]"
    )
    console.print(Panel(body, title="GitHub lifecycle (issue → PR → merge)", border_style="cyan"))
    default_idx = _LIFECYCLE_TIERS.index(default) + 1 if default in _LIFECYCLE_TIERS else 1
    choice = IntPrompt.ask("Ship the GitHub lifecycle?", default=default_idx)
    idx = choice - 1 if 1 <= choice <= len(_LIFECYCLE_TIERS) else default_idx - 1
    return _LIFECYCLE_TIERS[idx]


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
        "[dim]Local-only — no publish workflow ships (PI-343). On by default; "
        "decline with --no-docs.[/dim]",
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
) -> ScaffoldInputs:
    """Prompt for the profile, project basics, MCPs, governance, and overlays.

    ``cli_overlays`` pre-seeds the overlay flags (delivery, deploy, iac,
    multi_model, governance, observability) from the CLI; the string slots may
    be None to prompt, and multi_model/governance/observability=True skip their
    prompts (ADR-016/ADR-018/ADR-019).
    """
    resolved_profile = profile or _choose_profile_interactive()
    no_plugin = _profile_delivery_no_plugin(resolved_profile, no_plugin)
    project_name = _prompt("Project name", default=default_name)
    project_description = _prompt("Description", default="")
    language = _prompt("Language (python/node/go/none)", default="none")
    if language not in {"python", "node", "go", "none"}:
        language = "none"
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

    # MCP selection — catalog multi-select + optional browser MCP.
    selected_mcps = _choose_mcps_interactive(MCP_CATALOG)
    if _choose_browser_interactive():
        selected_mcps = selected_mcps + [PLAYWRIGHT_MCP]

    # Governance (PI-145).
    owner = _prompt("Owner/team for CODEOWNERS + LICENSE (e.g. @org/team)", default="")
    license_choice = _prompt("License (mit/apache-2.0/proprietary/none)", default="none")
    if license_choice not in {"mit", "apache-2.0", "proprietary", "none"}:
        license_choice = "none"

    # Toolchain toggles — each explains its value before asking (#472, ADR-023).
    devcontainer = _choose_devcontainer_interactive()
    mise = _choose_mise_interactive()
    vscode = _choose_vscode_interactive()
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
    while True:
        agents_raw = _prompt(
            "Agents/surfaces (claude always; add codex/ollama/cursor/antigravity/vscode, comma-separated)",
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
    p.add_argument(
        "--apply", action="store_true", help="apply changes (default: dry-run report)"
    )
    p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="permit --apply on a dirty git work tree (default: refuse)",
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
    export_dir = Path(args.export).resolve() if getattr(args, "export", None) else None

    git_status = None
    if args.apply:
        git_status = _git_worktree_status(target)
        blocked = _enforce_clean_tree(git_status, allow_dirty=args.allow_dirty, target=target)
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
    return {
        "project_name": project_name,
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
        # support note, PI-386). No flags for cursor/vscode: their config is
        # generated from the `agents` list by surfaces.emit (PI-366), not by
        # templates. ("vscode" here would also collide with the VS Code var.)
        "antigravity": "true" if "antigravity" in agents else "",
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
    # In --json mode stdout must be the JSON result only (#510); skip the human
    # profile/egress notice. (It is advisory output, not a silent default — the
    # JSON result and the recorded config carry the resolved profile.)
    if not getattr(args, "json", False):
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


def _validate_text_inputs(inputs: ScaffoldInputs, parser: argparse.ArgumentParser) -> None:
    """Reject text fields that would corrupt the rendered config.yaml.

    name/description/owner are embedded into a double-quoted YAML string in
    config.yaml; a literal double-quote, backslash (an invalid/lossy YAML escape,
    as in a Windows-style path), newline, or control character there produces
    invalid YAML (which then breaks ``upgrade`` and descriptor reads). These are
    short single-line fields, so a clean rejection beats silent corruption
    (e2e sweep; Codex/Copilot review).
    """
    for flag, value in (
        ("name", inputs.project_name),
        ("description", inputs.project_description),
        ("owner", inputs.owner),
    ):
        if (
            '"' in value
            or "\\" in value
            or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)
        ):
            parser.error(
                f"--{flag} must not contain double-quotes, backslashes, newlines, "
                "or control characters (they corrupt the generated config.yaml)"
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
    """Run the scaffolding CLI; return the process exit code."""
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    _subcommands = {
        "upgrade": lambda a: _upgrade_main(a),
        "add": lambda a: _concern_main(a, enable=True),
        "remove": lambda a: _concern_main(a, enable=False),
        "preset": lambda a: _preset_main(a),
    }
    if argv[:1] and argv[0] in _subcommands:
        return _subcommands[argv[0]](argv[1:])
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
        parser.error("--json requires --non-interactive (interactive prompts would corrupt JSON stdout)")

    if args.non_interactive:
        _require_non_interactive_args(args, parser)

    target = Path(args.target).resolve()

    # Select preset BEFORE creating the target directory — a typo'd --preset
    # should fail without leaving an empty dir behind.
    preset = _select_preset(args, parser, presets)
    # Memory backend fallback when --memory is absent (#466): the preset's stack
    # (obsidian-only/obsidian-graphify/core's "none"), default obsidian-only.
    preset_memory = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    # Lifecycle-tier fallback when --lifecycle is absent (#476): the preset's
    # tier (a preset may set lifecycle = "none" to be minimal), default "github".
    preset_lifecycle = preset.get("vars", {}).get("lifecycle", "github")

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
        )
    _validate_text_inputs(inputs, parser)
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
    _emit_scaffold_output(args, target, created, preset, variables, inputs, conflicts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
