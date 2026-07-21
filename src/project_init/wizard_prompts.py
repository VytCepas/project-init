"""project-init interactive wizard — prompt primitives and per-concern choosers.

Every `_prompt*`/`_choose_*_interactive` and the `_gather_inputs_interactive`
orchestrator live here (PI-794). The choosers call each other and the pure
resolvers in `variables`; tests monkeypatch these on THIS module. Imports only
console/mcps/scaffold/variables — never subcommands or the CLI spine.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from project_init.cli_output import _presets_payload
from project_init.console import (
    console,
    option_line,
    render_presets,
)
from project_init.mcps import MCP_CATALOG, PLAYWRIGHT_MCP
from project_init.scaffold import load_preset
from project_init.variables import (
    _AGENT_SURFACES,
    _DELIVERY,
    _DELIVERY_SUMMARY,
    _DEPLOY_SUMMARY,
    _DEPLOY_TARGETS,
    _IAC_OPTIONS,
    _IAC_SUMMARY,
    _LIFECYCLE_TIERS,
    _MEMORY_STACKS,
    _PROFILE_SUMMARY,
    _PROFILES,
    SUPPORTED_PYTHON_VERSIONS,
    ScaffoldInputs,
    _declared_python_floor,
    _profile_delivery_no_plugin,
    _resolve_mcps_non_interactive,
    _text_field_error,
    resolve_agents,
    resolve_delivery,
    resolve_deploy,
    resolve_iac,
)


def _prompt(label: str, default: str = "") -> str:
    from rich.prompt import Prompt

    return Prompt.ask(label, default=default) or default


def _prompt_choice(label: str, valid: tuple[str, ...], *, default: str) -> str:
    """Prompt for one of *valid*, case-insensitively, re-asking on a bad answer.

    Interactive counterpart to argparse ``choices``: typing ``Python`` or ``MIT``
    must not silently coerce to ``none`` — normalize case and re-prompt with the
    valid set instead (PI review 2026-07).
    """
    while True:
        value = _prompt(label, default=default).strip().lower()
        if value in valid:
            return value
        console.print(f"[red]Invalid choice {value!r}. Valid: {', '.join(valid)}[/red]")


def _prompt_menu_index(question: str, count: int, *, default: int) -> int:
    """IntPrompt that re-asks until the answer is inside the 1..count menu.

    Interactive counterpart to _prompt_choice for numbered menus: a typo'd
    number must not silently become the default selection (2026-07 QA) —
    re-prompt with the valid range instead.
    """
    from rich.prompt import IntPrompt

    while True:
        choice = IntPrompt.ask(question, default=default)
        if 1 <= choice <= count:
            return choice
        console.print(f"[red]Invalid choice {choice}. Enter a number between 1 and {count}.[/red]")


def _prompt_validated(label: str, *, default: str, flag: str, allow_empty: bool = False) -> str:
    """Prompt, re-asking until the value would not corrupt config.yaml.

    Interactive counterpart to _validate_text_inputs: a bad character is caught
    at the field so the user fixes it in place instead of completing the whole
    wizard only to hit ``parser.error`` and lose every answer (PI review).
    """
    while True:
        value = _prompt(label, default=default)
        err = _text_field_error(flag, value, allow_empty=allow_empty)
        if err is None:
            return value
        console.print(f"[red]{err}[/red]")


def _default_preset_index(presets: list[dict[str, Any]]) -> int:
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


def _choose_preset_interactive(presets: list[dict[str, Any]]) -> dict[str, Any]:
    from rich.panel import Panel

    # Value framing (#472, ADR-023): say what a preset *is* and that it's only a
    # starting point, so the choice is informed rather than blind.
    console.print(
        Panel(
            "A [bold]preset[/bold] is your starting bundle — it sets sensible "
            "defaults for the overlays (lifecycle, memory, toolchain) that the "
            "prompts below then let you confirm or change one at a time.\n\n"
            "[cyan]Helps:[/cyan] pick the closest fit; nothing here is locked in "
            "— each overlay gets its own prompt, so you can still decline or add "
            "individual pieces.\n"
            '[dim]Default: the recommended obsidian-only preset. "core" is the '
            "leanest.[/dim]",
            title="Preset",
            border_style="cyan",
        )
    )
    default_idx = _default_preset_index(presets)
    # Resolve each preset's memory stack through extends inheritance so the
    # table's Memory column is accurate for inheriting presets like `governed`
    # (raw vars would show "—"; PI-645 review, mirrors #511).
    memory_by_name = {row["name"]: row["memory_stack"] for row in _presets_payload(presets)}
    render_presets(presets, default_idx, memory_by_name)
    console.print()

    choice = _prompt_menu_index("Choose a preset", len(presets), default=default_idx)
    return presets[choice - 1]


def _choose_mcps_interactive(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from rich.prompt import Prompt

    console.print(
        "\n[bold]MCP servers[/bold] — optional plug-in tool servers your agent "
        "can call (Model Context Protocol):"
    )
    for i, m in enumerate(catalog, 1):
        console.print(option_line(i, m["name"], m["description"]))
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
    from rich.panel import Panel

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
        console.print(option_line(i, name, _PROFILE_SUMMARY[name]))
    console.print()
    choice = _prompt_menu_index("Choose a profile", len(_PROFILES), default=1)
    return _PROFILES[choice - 1]


def _choose_multi_model_interactive() -> bool:
    """Explain multi-model switching + the alternatives, then ask (ADR-016, #352).

    States plainly what the overlay does, how it helps, and the honest
    alternatives (OpenAI/Codex is better in its native --agents harness;
    Ollama runs locally), so the user makes an informed choice or declines —
    declining leaves a clean project. Passing --multi-model (in either mode)
    pre-accepts via the flag and skips this; only an interactive run without the
    flag reaches here.
    """
    from rich.panel import Panel
    from rich.prompt import Confirm

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
    from rich.panel import Panel
    from rich.prompt import Confirm

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
        '[cyan]Helps:[/cyan] answer "what AI runs here, on what data, under whose '
        'sign-off" for reviewers, customers, and regulators.\n'
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
    from rich.panel import Panel
    from rich.prompt import Confirm

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


def _choose_memory_interactive(default: str = "obsidian-only") -> str:
    """Explain the memory backends, then ask which to scaffold (#466).

    States what each backend ships and what it brings, so the user makes an
    informed choice or declines memory entirely (``none`` → the vault-free
    project). Passing --memory pre-selects and skips this. The default follows
    the chosen preset's memory stack.
    """
    from rich.panel import Panel

    default_idx = _MEMORY_STACKS.index(default) + 1 if default in _MEMORY_STACKS else 3
    body = (
        "[dim]Confirm or change the memory backend your preset set up front — "
        "the default below is that preset's stack, not a fresh choice.[/dim]\n\n"
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


def _choose_lifecycle_interactive(default: str = "github") -> str:
    """Explain the GitHub lifecycle tier, then ask whether to ship it (#476).

    States what the lifecycle automation ships and what it brings, so the user
    keeps it or declines for a forge-agnostic / minimalist scaffold. Passing
    --lifecycle pre-selects and skips this. The default follows the chosen
    preset's lifecycle tier.
    """
    from rich.panel import Panel

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
    choice = _prompt_menu_index(
        "Choose a lifecycle tier", len(_LIFECYCLE_TIERS), default=default_idx
    )
    return _LIFECYCLE_TIERS[choice - 1]


def _choose_review_cycles_interactive(default: int = 2) -> int:
    """Explain review cycles, then ask how many the merge gate should run (#714).

    Only reached when the GitHub lifecycle is selected — a `--lifecycle none`
    project ships no monitor_pr.sh, so there is no cycle count to configure.
    """
    from rich.panel import Panel

    body = (
        "A [bold]review cycle[/bold] is one pass of the merge gate: "
        "[bold]push → the review agents comment → you resolve → they re-review[/bold]. "
        "monitor_pr.sh runs up to this many before it stops asking for another.\n\n"
        "[bold]0[/bold]  [dim]no review control — merge as soon as CI is green[/dim]\n"
        "[bold]1[/bold]  [dim]comment once, resolve, merge[/dim]\n"
        "[bold]2[/bold]  [dim]the resolved comments are reviewed too, then merge[/dim]\n"
        "[bold]3+[/bold] [dim]additional re-review rounds[/dim]\n\n"
        "Whatever the count, the merge rule is the same: once the review agents' "
        "comments are resolved — or none arise — the PR is free to merge.\n\n"
        "[cyan]Helps:[/cyan] the second pass is where a fix's own bugs surface; "
        "review agents routinely find a flaw in the patch that answered them.\n"
        "[dim]Cost: each cycle is another round-trip before a merge. Default: 2. "
        "Change later in .agents/config.yaml, or per-run with PI_REVIEW_CYCLES.[/dim]"
    )
    console.print(Panel(body, title="Review cycles (before merge)", border_style="cyan"))
    while True:
        raw = _prompt("Review cycles", default=str(default)).strip()
        if raw.isdigit():
            return int(raw)
        console.print("[red]Enter a non-negative integer (0 disables review control).[/red]")


def _explain_and_confirm(title: str, body: str, question: str, *, default: bool) -> bool:
    """Render a concise explanation Panel for a toolchain toggle, then ask."""
    from rich.panel import Panel
    from rich.prompt import Confirm

    console.print(Panel(body, title=title, border_style="cyan"))
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


def _choose_coauthor_interactive() -> bool:
    return _explain_and_confirm(
        "Co-Authored-By trailer",
        "Append a [bold]Co-Authored-By: Claude <noreply@anthropic.com>[/bold] "
        "trailer to agent-generated commits — the scaffolded commit guidance and "
        "the optional bootstrap commit honor this choice.\n\n"
        "[cyan]Helps:[/cyan] commit provenance shows which work an AI agent "
        "co-authored.\n"
        "[dim]Decline for a clean history or an org policy that forbids AI "
        "co-author trailers. On by default; decline with --no-coauthor.[/dim]",
        "Add a Co-Authored-By: Claude trailer to agent commits?",
        default=True,
    )


def _select_preset(
    args: argparse.Namespace, parser: argparse.ArgumentParser, presets: list[dict[str, Any]]
) -> dict[str, Any]:
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
            console.print(f"[red]{e}[/red]")
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
    resolved_delivery = None
    if delivery:
        try:
            resolved_delivery = resolve_delivery(delivery, language)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
    if resolved_delivery is None:
        resolved_delivery = _choose_delivery_interactive(language)

    resolved_iac = _resolve_iac_interactive(iac)

    if resolved_delivery != "service":
        if deploy and deploy.strip().lower() not in ("", "none"):
            console.print(
                f"[yellow]--deploy {deploy} ignored: deploy targets apply only to "
                f"delivery=service (this is {resolved_delivery}).[/yellow]"
            )
        return resolved_delivery, "none", resolved_iac
    resolved_deploy = None
    if deploy:
        try:
            resolved_deploy = resolve_deploy(deploy, resolved_delivery)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
    if resolved_deploy is None:
        resolved_deploy = _choose_deploy_interactive()
    return resolved_delivery, resolved_deploy, resolved_iac


def _gather_mcps_interactive(cli_mcps: str, cli_browser: bool) -> list[dict[str, Any]]:
    """Resolve MCPs for the wizard: honor --mcps/--browser, else prompt (PI review).

    A bad ``--mcps`` id warns and falls back to the catalog rather than crashing
    the wizard mid-run.
    """
    if cli_mcps.strip():
        try:
            selected = _resolve_mcps_non_interactive(cli_mcps, cli_browser)
        except ValueError as e:
            console.print(f"[red]{e}[/red] — choose from the catalog instead.")
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


def _print_wizard_guidance() -> None:
    """Frame the interactive path so defaults feel intentional, not mysterious."""
    from rich.panel import Panel

    console.print(
        Panel(
            "[bold]Recommended path:[/bold] answer the identity questions, then "
            "press [bold]Enter[/bold] to accept each default unless you already "
            "know you need the extra capability.\n\n"
            "Each optional concern explains what it ships, how it helps, and its "
            "cost before asking.",
            title="Project-init wizard",
            border_style="cyan",
        )
    )


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
    no_coauthor: bool = False,
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
    cli_agents: str | None = None,
    cli_python_version: str | None = None,
    cli_review_cycles: int | None = None,
    target: Path | None = None,
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
    _print_wizard_guidance()
    resolved_profile = profile or _choose_profile_interactive()
    no_plugin = _profile_delivery_no_plugin(resolved_profile, no_plugin)
    project_name = _prompt_validated("Project name", default=cli_name or default_name, flag="name")
    # Interactive accept-default flows need a usable description. The
    # non-interactive path still requires --description; here we derive a plain
    # day-one default from the accepted project name so Enter can complete the
    # wizard without producing an empty config field.
    default_description = cli_description or f"{project_name} project"
    project_description = _prompt_validated(
        "Description",
        default=default_description,
        flag="description",
    )
    language = _prompt_choice(
        "Language (python/node/go/rust/none)",
        ("python", "node", "go", "rust", "none"),
        default=cli_language or "none",
    )
    # #628: only a Python scaffold has a version to pin, and only a greenfield
    # one has an unanswered question — when pyproject.toml already declares
    # requires-python, that file is the source of truth and asking would invite
    # a contradiction. An explicit --python-version still wins over both.
    python_version = cli_python_version or ""
    if python_version and language != "python":
        # --language wasn't passed, so main() couldn't reject this pairing; the
        # value would render nowhere. Drop it loudly rather than silently.
        console.print(
            f"[yellow]--python-version {python_version} ignored: it applies only to "
            f"a python project (this is {language}).[/yellow]"
        )
        python_version = ""
    if not python_version and language == "python" and not _declared_python_floor(target):
        python_version = _prompt_choice(
            "Target Python (pins mise.toml, mypy.ini, and the CI matrix floor)",
            SUPPORTED_PYTHON_VERSIONS,
            default=SUPPORTED_PYTHON_VERSIONS[0],
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
    # #714: cycles configure the scaffolded monitor_pr.sh, which only ships with
    # the lifecycle. Asking a `--lifecycle none` user to size a review gate they
    # will never run is noise, so the prompt is gated on the resolved tier.
    #
    # PR #717 review: a CLI value reaching the wizard used to be copied raw —
    # `--review-cycles -1` wrote an invalid config that later crashed
    # monitor_pr.sh, and a flag paired with an interactively-chosen
    # `lifecycle none` was dropped in silence. main() rejects a negative value
    # and an explicit `--lifecycle none` up front; what it cannot know is a tier
    # the user picks at the prompt, so that case warns and drops here rather
    # than aborting a wizard the user has already half-answered.
    if resolved_lifecycle == "none":
        if cli_review_cycles is not None:
            console.print(
                f"[yellow]--review-cycles {cli_review_cycles} ignored: no merge gate is "
                "scaffolded with lifecycle 'none'.[/yellow]"
            )
        review_cycles = 0
    elif cli_review_cycles is not None:
        review_cycles = cli_review_cycles
    else:
        review_cycles = _choose_review_cycles_interactive()
    # An explicit --agents (including `--agents claude` for a claude-only
    # project) is honored; an absent flag (None) opens the surface chooser —
    # mirroring how every other concern flag wins over its interactive prompt.
    if cli_agents is not None:
        try:
            agents = resolve_agents(cli_agents)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
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
        python_version=python_version,
        review_cycles=review_cycles,
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
        # Co-Authored-By: Claude commit trailer (#888). --no-coauthor pre-declines
        # and skips the prompt, mirroring --no-docs / --no-renovate.
        coauthor=False if no_coauthor else _choose_coauthor_interactive(),
    )


def _choose_delivery_interactive(language: str) -> str:
    """Present the delivery options (ADR-015); default prototype.

    Re-prompts if the choice is invalid for the chosen language (a service needs
    a language toolchain).
    """
    console.print("\n[bold]How is this delivered?[/bold]")
    for i, name in enumerate(_DELIVERY, 1):
        console.print(option_line(i, name, _DELIVERY_SUMMARY[name]))
    while True:
        choice = _prompt_menu_index("Choose a delivery model", len(_DELIVERY), default=3)
        try:
            return resolve_delivery(_DELIVERY[choice - 1], language)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")


def _choose_deploy_interactive() -> str:
    """Present the deploy options (ADR-015); default none. Shown only for services."""
    console.print("\n[bold]How is this service deployed?[/bold]")
    for i, name in enumerate(_DEPLOY_TARGETS, 1):
        console.print(option_line(i, name, _DEPLOY_SUMMARY[name]))
    choice = _prompt_menu_index("Choose a deploy target", len(_DEPLOY_TARGETS), default=1)
    return _DEPLOY_TARGETS[choice - 1]


def _choose_iac_interactive() -> str:
    """Present the IaC options (ADR-015); default none."""
    console.print("\n[bold]Infrastructure-as-Code overlay?[/bold]")
    for i, name in enumerate(_IAC_OPTIONS, 1):
        console.print(option_line(i, name, _IAC_SUMMARY[name]))
    choice = _prompt_menu_index("Choose an IaC overlay", len(_IAC_OPTIONS), default=1)
    return _IAC_OPTIONS[choice - 1]


def _choose_agents_interactive() -> list[str]:
    """Present the agent/editor surfaces to scaffold for (ADR-017, #616)."""
    from rich.panel import Panel
    from rich.prompt import Prompt

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
