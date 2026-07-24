"""project-init interactive wizard — prompt primitives and per-concern choosers.

Every `_prompt*`/`_choose_*_interactive` and the `_gather_inputs_interactive`
orchestrator live here (PI-794). The choosers call each other and the pure
resolvers in `variables`; tests monkeypatch these on THIS module. Imports only
console/mcps/scaffold/variables — never subcommands or the CLI spine.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_init.box_profile import BoxProfile
from project_init.cli_output import _presets_payload
from project_init.console import (
    console,
    option_line,
    render_presets,
)
from project_init.mcps import MCP_CATALOG, PLAYWRIGHT_MCP
from project_init.scaffold import load_preset, memory_tier
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
    _profile_enforcement,
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


def _choose_mcps_interactive(
    catalog: list[dict[str, Any]], default_ids: tuple[str, ...] | None = None
) -> list[dict[str, Any]]:
    from rich.prompt import Prompt

    console.print(
        "\n[bold]MCP servers[/bold] — optional plug-in tool servers your agent "
        "can call (Model Context Protocol):"
    )
    for i, m in enumerate(catalog, 1):
        console.print(option_line(i, m["name"], m["description"]))
    console.print()
    # Box-profile seed (BOX-1): Enter keeps the seeded selection instead of
    # skipping — the seed is the DEFAULT here, still fully changeable.
    enter_selection = [m for m in catalog if m["id"] in (default_ids or ())]
    label = "Choose MCPs (comma-separated numbers, or Enter to skip)"
    if default_ids:
        console.print(f"[dim]Enter keeps the box-profile default: {', '.join(default_ids)}[/dim]")
        label = "Choose MCPs (comma-separated numbers, or Enter for the default)"

    while True:
        raw = Prompt.ask(label, default="")
        if not raw.strip():
            return enter_selection

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


def _choose_profile_interactive(default: str | None = None) -> str:
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
    default_idx = _PROFILES.index(default) + 1 if default in _PROFILES else 1
    choice = _prompt_menu_index("Choose a profile", len(_PROFILES), default=default_idx)
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


def _choose_bootstrap_interactive() -> bool:
    return _explain_and_confirm(
        "Initialize everything now",
        "Run the setup a fresh scaffold otherwise leaves to you:\n"
        "  [bold]git init[/bold] → install lifecycle hooks → "
        "[bold]uv init[/bold] + [bold]just setup[/bold] (python) → initial commit.\n\n"
        "[cyan]Helps:[/cyan] the project is usable and committed the moment the "
        "wizard exits — no manual bootstrap checklist.\n"
        "[dim]Each step is idempotent (skips what is already done) and "
        "best-effort (a failure is reported, the scaffold stays intact). "
        "Non-interactive runs opt in with --bootstrap.[/dim]",
        "Initialize everything now (git, hooks, deps, initial commit)?",
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


def _gather_mcps_interactive(
    cli_mcps: str, cli_browser: bool, default_ids: tuple[str, ...] | None = None
) -> list[dict[str, Any]]:
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
    selected = (
        _choose_mcps_interactive(MCP_CATALOG)
        if default_ids is None
        else _choose_mcps_interactive(MCP_CATALOG, default_ids=default_ids)
    )
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


# The gateway groups (ADR-029): the collapsed wizard's default path asks six
# questions; every other concern lives in one of these groups, opened on demand.
# Each entry: (key, title, one-line contents-with-defaults). Order is the order
# the opened groups' choosers run, which preserves the pre-collapse sequence.
_GATEWAY_GROUPS: tuple[tuple[str, str, str], ...] = (
    (
        "delivery",
        "Delivery & deploy",
        "library/service/prototype, deploy target, IaC — defaults: prototype, none, none",
    ),
    (
        "integrations",
        "Integrations",
        "MCP servers, browser automation, agent surfaces — defaults: none, off, claude+vscode",
    ),
    (
        "extras",
        "Dev extras",
        "devcontainer, mise, VS Code workspace — defaults: all off",
    ),
    (
        "quality",
        "Docs & updates",
        "docs tooling, Renovate — defaults: both on",
    ),
    (
        "overlays",
        "Profile & overlays",
        "distribution profile, multi-model, governance, observability — "
        "defaults: individual, off, off, off",
    ),
    (
        "memory",
        "Memory & lifecycle",
        "memory tier ladder (auto/obsidian/graphify/rag), GitHub lifecycle, "
        "review cycles — defaults from the preset; rag pays off only at "
        "multi-project scale",
    ),
    (
        "details",
        "Project details",
        "owner/CODEOWNERS, license, Co-Authored-By trailer — defaults: none, none, on",
    ),
)


@dataclass(frozen=True)
class _CliSeeds:
    """The CLI/preset seeds the gateway resolution consults (ADR-029).

    One immutable bundle so the default-state and group-applier helpers stay
    under the complexity gates without threading twenty parameters each.
    """

    language: str
    delivery: str | None
    deploy: str | None
    iac: str | None
    multi_model: bool
    governance: bool
    observability: bool
    memory: str | None
    preset_memory: str
    lifecycle: str | None
    preset_lifecycle: str
    no_docs: bool
    no_renovate: bool
    no_coauthor: bool
    mcps: str
    browser: bool
    agents: str | None
    owner: str
    license_choice: str
    devcontainer: bool
    mise: bool
    vscode: bool
    review_cycles: int | None
    profile: str | None
    deploy_app: str = ""
    deploy_region: str = ""
    deploy_health_url: str = ""


@dataclass
class _GatewayState:
    """The mutable concern resolution the gateway groups refine (ADR-029).

    Constructed by ``_default_gateway_state`` with every concern at the value
    its chooser's Enter default produced pre-collapse (flags winning), then
    selectively overwritten by ``_apply_opened_groups``.
    """

    profile: str
    delivery: str
    deploy: str
    iac: str
    agents: list[str]
    agents_pinned: bool
    owner: str
    license_choice: str
    devcontainer: bool
    mise: bool
    vscode: bool
    want_docs: bool
    renovate: bool
    multi_model: bool
    governance: bool
    observability: bool
    memory: str
    lifecycle: str
    review_cycles: int
    coauthor: bool
    memory_from_preset: bool
    mcps: list[dict[str, Any]] = field(default_factory=list)
    # Box-profile seeds (BOX-1): recorded so an OPENED group presents the seed
    # as its chooser default instead of resetting to factory (PR #898 review).
    seeded_agents: tuple[str, ...] | None = None
    seeded_mcp_ids: tuple[str, ...] | None = None
    seeded_profile: str | None = None
    # Deploy identity (PI-899): empty = derive at render (slug/us-central1/none).
    deploy_app: str = ""
    deploy_region: str = ""
    deploy_health_url: str = ""


def _resolve_review_cycles(flag: int | None, lifecycle: str, *, ask: bool) -> int:
    """#714 / PR #717 semantics, shared by the default path and the opened group.

    Lifecycle none forces 0 and loudly drops a flag; otherwise the flag wins;
    else the chooser (opened group) or its Enter default (standard path).
    """
    if lifecycle == "none":
        if flag is not None:
            console.print(
                f"[yellow]--review-cycles {flag} ignored: no merge gate is "
                "scaffolded with lifecycle 'none'.[/yellow]"
            )
        return 0
    if flag is not None:
        return flag
    return _choose_review_cycles_interactive() if ask else 2


def _validated_overlay_flags(seeds: _CliSeeds) -> tuple[str, str, str, bool]:
    """Validate --delivery/--deploy/--iac without prompting (ADR-029 default path).

    Returns (delivery, deploy, iac, needs_prompt): an invalid flag warns and
    flips ``needs_prompt`` so the delivery group re-opens interactively — the
    same never-crash, never-silently-drop fall-through the pre-collapse flow
    had. A --deploy on a non-service delivery is dropped loudly, as before.
    """
    if not (seeds.delivery or seeds.deploy or seeds.iac):
        return "prototype", "none", "none", False
    try:
        delivery = (
            resolve_delivery(seeds.delivery, seeds.language) if seeds.delivery else "prototype"
        )
        iac = resolve_iac(seeds.iac) if seeds.iac else "none"
        deploy = "none"
        if delivery == "service":
            deploy = resolve_deploy(seeds.deploy, delivery) if seeds.deploy else "none"
        elif seeds.deploy and seeds.deploy.strip().lower() not in ("", "none"):
            console.print(
                f"[yellow]--deploy {seeds.deploy} ignored: deploy targets apply only "
                f"to delivery=service (this is {delivery}).[/yellow]"
            )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return "prototype", "none", "none", True
    return delivery, deploy, iac, False


def _default_gateway_state(seeds: _CliSeeds) -> tuple[_GatewayState, set[str]]:
    """Resolve every concern to its standard-path value; flags always win.

    Returns the state plus the groups that MUST open anyway (an invalid flag
    fell through to its chooser, pre-collapse behavior).
    """
    force_open: set[str] = set()
    delivery, deploy, iac, overlays_need_prompt = _validated_overlay_flags(seeds)
    if overlays_need_prompt:
        force_open.add("delivery")

    mcps: list[dict[str, Any]] = []
    if seeds.mcps.strip():
        try:
            mcps = _resolve_mcps_non_interactive(seeds.mcps, seeds.browser)
        except ValueError as e:
            console.print(f"[red]{e}[/red] — choose from the catalog instead.")
            force_open.add("integrations")
    elif seeds.browser:
        mcps = [PLAYWRIGHT_MCP]

    # The chooser's Enter default is vscode-plus-claude (its option 1 is the
    # vscode surface; panel says "Default: vscode only (plus claude)") — NOT
    # the non-interactive path's claude-only default. Equivalence (ADR-029)
    # binds the standard path to the CHOOSER's default (PR #896 review).
    agents = ["claude", "vscode"]
    agents_pinned = False
    if seeds.agents is not None:
        try:
            agents = resolve_agents(seeds.agents)
            agents_pinned = True
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            force_open.add("integrations")

    lifecycle = seeds.lifecycle or seeds.preset_lifecycle
    state = _GatewayState(
        profile=seeds.profile or "individual",
        delivery=delivery,
        deploy=deploy,
        iac=iac,
        mcps=mcps,
        agents=agents,
        agents_pinned=agents_pinned,
        owner=seeds.owner or "",
        license_choice=seeds.license_choice or "none",
        devcontainer=seeds.devcontainer,
        mise=seeds.mise,
        vscode=seeds.vscode,
        want_docs=not seeds.no_docs,
        renovate=not seeds.no_renovate,
        multi_model=seeds.multi_model,
        governance=seeds.governance,
        observability=seeds.observability,
        deploy_app=seeds.deploy_app,
        deploy_region=seeds.deploy_region,
        deploy_health_url=seeds.deploy_health_url,
        memory=seeds.memory or seeds.preset_memory,
        lifecycle=lifecycle,
        review_cycles=_resolve_review_cycles(seeds.review_cycles, lifecycle, ask=False),
        coauthor=not seeds.no_coauthor,
        memory_from_preset=seeds.memory is None,
    )
    return state, force_open


def _apply_box_profile(
    state: _GatewayState, seeds: _CliSeeds, box: BoxProfile | None
) -> str | None:
    """Seed unflagged DEFAULTS from the box profile (BOX-1, advisory-only).

    Returns the single advisory line to print, or None when no profile exists.
    Flags always beat the box; the box only moves defaults, so every seed
    remains changeable at the gateway. Unknown names are ignored and reported
    in the same line — never an error (harbor CONTRACTS/box-profile.md v1).
    """
    if box is None:
        return None
    seeded: list[str] = []
    ignored: list[str] = []
    if box.harnesses and seeds.agents is None:
        known_surfaces = {"claude"} | {name for name, _ in _AGENT_SURFACES}
        valid = [s for s in box.harnesses if s in known_surfaces]
        ignored += [s for s in box.harnesses if s not in known_surfaces]
        if valid:
            if "claude" not in valid:
                valid.insert(0, "claude")
            state.agents = list(dict.fromkeys(valid))
            state.seeded_agents = tuple(state.agents)
            seeded.append(f"agents={','.join(state.agents)}")
    if box.mcp_roster and not seeds.mcps.strip() and not seeds.browser:
        by_id = {m["id"]: m for m in MCP_CATALOG}
        valid_mcps = [by_id[i] for i in dict.fromkeys(box.mcp_roster) if i in by_id]
        ignored += [i for i in box.mcp_roster if i not in by_id]
        if valid_mcps:
            state.mcps = valid_mcps
            state.seeded_mcp_ids = tuple(m["id"] for m in valid_mcps)
            seeded.append(f"mcps={','.join(state.seeded_mcp_ids)}")
    if box.profile is not None and seeds.profile is None:
        state.profile = box.profile
        state.seeded_profile = box.profile
        seeded.append(f"profile={box.profile}")
    line = f"Box profile: {box.source} — seeded: {', '.join(seeded) or 'nothing (flags pinned)'}"
    if ignored:
        line += f"; ignored unknown: {', '.join(dict.fromkeys(ignored))}"
    return line


def _pinned_gateway_flags(seeds: _CliSeeds) -> dict[str, list[str]]:
    """Map each gateway group to the CLI flags already pinning part of it."""
    candidates: dict[str, tuple[tuple[str, object], ...]] = {
        "delivery": (
            ("--delivery", seeds.delivery),
            ("--deploy", seeds.deploy),
            ("--iac", seeds.iac),
            ("--deploy-app", seeds.deploy_app),
            ("--deploy-region", seeds.deploy_region),
            ("--deploy-health-url", seeds.deploy_health_url),
        ),
        "integrations": (
            ("--mcps", seeds.mcps.strip()),
            ("--browser", seeds.browser),
            ("--agents", seeds.agents),
        ),
        "extras": (
            ("--devcontainer", seeds.devcontainer),
            ("--mise", seeds.mise),
            ("--vscode", seeds.vscode),
        ),
        "quality": (("--no-docs", seeds.no_docs), ("--no-renovate", seeds.no_renovate)),
        "overlays": (
            ("--profile", seeds.profile),
            ("--multi-model", seeds.multi_model),
            ("governance (flag/preset)", seeds.governance),
            ("--observability", seeds.observability),
        ),
        "memory": (
            ("--memory", seeds.memory),
            ("--lifecycle", seeds.lifecycle),
            ("--review-cycles", seeds.review_cycles is not None),
        ),
        "details": (
            ("--owner", seeds.owner),
            ("--license", seeds.license_choice not in ("", "none")),
            ("--no-coauthor", seeds.no_coauthor),
        ),
    }
    return {
        group: [flag for flag, value in pairs if value]
        for group, pairs in candidates.items()
        if any(value for _, value in pairs)
    }


def _capture_deploy_identity_interactive(state: _GatewayState, seeds: _CliSeeds) -> None:
    """Capture app/region/health URL for a deploying service (PI-899).

    Runs only inside the OPENED delivery group when the resolved deploy target
    is real — the standard path never sees these prompts (defaults derive at
    render: slug / us-central1 / no probe). app/region re-ask until they meet
    the descriptor schema pattern; Enter keeps the derived default.
    """
    from project_init.variables import deploy_identity_error

    def _ask(field: str, label: str, default: str) -> str:
        while True:
            value = _prompt(label, default=default)
            err = deploy_identity_error(field, value)
            if err is None:
                return value
            console.print(f"[red]{err}[/red]")

    state.deploy_app = _ask(
        "app", "Deploy app name (Enter = the project slug)", seeds.deploy_app or ""
    )
    state.deploy_region = _ask(
        "region", "Deploy region (Enter = us-central1)", seeds.deploy_region or ""
    )
    state.deploy_health_url = _prompt(
        "Health-check URL the orchestrator probes (Enter = none)",
        default=seeds.deploy_health_url or "",
    )


def _apply_delivery_group(state: _GatewayState, seeds: _CliSeeds) -> None:
    state.delivery, state.deploy, state.iac = _resolve_overlays_interactive(
        seeds.language, seeds.delivery, seeds.deploy, seeds.iac
    )
    if state.deploy != "none":
        _capture_deploy_identity_interactive(state, seeds)


def _apply_integrations_group(state: _GatewayState, seeds: _CliSeeds) -> None:
    # Honor --mcps/--browser as before; --mcps still leaves the browser concern
    # independently decidable inside the group (ADR-023). An explicit --agents
    # (incl. `--agents claude`) stays pinned — flag beats prompt.
    if state.seeded_mcp_ids is None:
        state.mcps = _gather_mcps_interactive(seeds.mcps, seeds.browser)
    else:
        state.mcps = _gather_mcps_interactive(
            seeds.mcps, seeds.browser, default_ids=state.seeded_mcp_ids
        )
    if not state.agents_pinned:
        state.agents = (
            _choose_agents_interactive()
            if state.seeded_agents is None
            else _choose_agents_interactive(default=state.seeded_agents)
        )


def _apply_details_group(state: _GatewayState, seeds: _CliSeeds) -> None:
    state.owner = _prompt_validated(
        "Owner/team for CODEOWNERS + LICENSE (e.g. @org/team)",
        default=seeds.owner or "",
        flag="owner",
        allow_empty=True,
    )
    state.license_choice = _prompt_choice(
        "License (mit/apache-2.0/proprietary/none)",
        ("mit", "apache-2.0", "proprietary", "none"),
        default=seeds.license_choice or "none",
    )
    if not seeds.no_coauthor:
        # Co-Authored-By trailer (#888). --no-coauthor pre-declines and skips.
        state.coauthor = _choose_coauthor_interactive()


def _apply_extras_group(state: _GatewayState, seeds: _CliSeeds) -> None:
    # A store_true CLI flag pre-accepts the toggle and skips its prompt.
    state.devcontainer = seeds.devcontainer or _choose_devcontainer_interactive()
    state.mise = seeds.mise or _choose_mise_interactive()
    state.vscode = seeds.vscode or _choose_vscode_interactive()


def _apply_quality_group(state: _GatewayState, seeds: _CliSeeds) -> None:
    # Docs tooling axis (#477, ADR-022): --no-docs wins; only python/node have
    # docs config to decide; other languages keep docs ON silently.
    if not seeds.no_docs and seeds.language in ("python", "node"):
        state.want_docs = _choose_docs_interactive(seeds.language)
    if not seeds.no_renovate:
        state.renovate = _choose_renovate_interactive()


def _apply_memory_group(state: _GatewayState, seeds: _CliSeeds) -> None:
    state.memory = seeds.memory or _choose_memory_interactive(default=seeds.preset_memory)
    state.memory_from_preset = seeds.memory is None and state.memory == seeds.preset_memory
    state.lifecycle = seeds.lifecycle or _choose_lifecycle_interactive(
        default=seeds.preset_lifecycle
    )
    state.review_cycles = _resolve_review_cycles(seeds.review_cycles, state.lifecycle, ask=True)


def _apply_profile_choice(state: _GatewayState, seeds: _CliSeeds) -> None:
    # --profile pins; a box-profile seed becomes the chooser's menu default.
    if seeds.profile:
        state.profile = seeds.profile
    elif state.seeded_profile is None:
        state.profile = _choose_profile_interactive()
    else:
        state.profile = _choose_profile_interactive(default=state.seeded_profile)


def _apply_opened_groups(state: _GatewayState, opened: set[str], seeds: _CliSeeds) -> None:
    """Run the pre-collapse choosers for each opened group, in pre-collapse order."""
    if "overlays" in opened:
        _apply_profile_choice(state, seeds)
    if "delivery" in opened:
        _apply_delivery_group(state, seeds)
    if "integrations" in opened:
        _apply_integrations_group(state, seeds)
    if "details" in opened:
        _apply_details_group(state, seeds)
    if "extras" in opened:
        _apply_extras_group(state, seeds)
    if "quality" in opened:
        _apply_quality_group(state, seeds)
    if "overlays" in opened:
        # Profile already resolved above (it led the pre-collapse sequence);
        # the overlay toggles kept their pre-collapse position after quality.
        _apply_overlays_toggles(state, seeds)
    if "memory" in opened:
        _apply_memory_group(state, seeds)


def _apply_overlays_toggles(state: _GatewayState, seeds: _CliSeeds) -> None:
    state.multi_model = seeds.multi_model or _choose_multi_model_interactive()
    state.governance = seeds.governance or _choose_governance_interactive()
    state.observability = seeds.observability or _choose_observability_interactive()


def _choose_gateway_interactive(pinned: dict[str, list[str]]) -> set[str]:
    """Offer the concern groups once; Enter takes the standard setup (ADR-029).

    ``pinned`` maps a group key to the CLI flags already pinning part of it —
    surfaced so a flag user sees their choices are honored without opening the
    group. Deliberately NOT built on ``_prompt`` so pre-collapse ordered answer
    iterators in tests never feed it by accident.
    """
    from rich.panel import Panel
    from rich.prompt import Prompt

    console.print(
        Panel(
            "The standard setup is ready — press [bold]Enter[/bold] to accept "
            "it and every remaining concern takes its default (shown per group "
            "below, echoed before scaffolding).\n\n"
            "[cyan]Helps:[/cyan] open only the groups you want to shape; each "
            "concern inside still explains its value and cost before asking.\n"
            "[dim]Default: standard setup — no further questions.[/dim]",
            title="Customize?",
            border_style="cyan",
        )
    )
    for i, (key, title, contents) in enumerate(_GATEWAY_GROUPS, 1):
        note = f"  [yellow](pinned: {', '.join(pinned[key])})[/yellow]" if pinned.get(key) else ""
        console.print(option_line(i, title, contents) + note)
    console.print()

    while True:
        raw = Prompt.ask(
            "Customize groups (comma-separated numbers, or Enter for the standard setup)",
            default="",
        )
        if not raw.strip():
            return set()
        opened: set[str] = set()
        invalid: list[str] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            idx = int(part) - 1 if part.isdigit() else -1
            if 0 <= idx < len(_GATEWAY_GROUPS):
                opened.add(_GATEWAY_GROUPS[idx][0])
            else:
                invalid.append(part)
        if invalid:
            # Same contract as the MCP picker: never silently drop part of the
            # user's selection — re-ask instead.
            console.print(
                f"[red]Invalid selection(s): {', '.join(invalid)}. "
                f"Enter numbers 1-{len(_GATEWAY_GROUPS)}.[/red]"
            )
            continue
        return opened


def _print_resolution_summary(
    inputs: ScaffoldInputs, *, preset_name: str, memory_from_preset: bool, title: str
) -> None:
    """Echo every resolved concern with its why/cost (ADR-029, ADR-023).

    Rendered BEFORE the Customize gateway (so accepting the standard setup is
    an informed decision, not a silent shortcut — the ADR-023 guarantee on the
    collapsed path) and re-rendered before bootstrap when an opened group
    changed anything. Leads with the real security surface: enforcement,
    egress, lifecycle gate, MCP/agent capabilities, governance. The per-row
    notes are compressed digests of the choosers' own ADR-023 panels.
    """
    from rich.table import Table

    tier = memory_tier(inputs.memory)
    egress = "marketplace egress off" if inputs.no_egress else "marketplace egress on"
    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("Concern")
    table.add_column("Resolved")
    table.add_column("Why · cost", style="dim")
    rows: tuple[tuple[str, str, str], ...] = (
        (
            "profile / enforcement",
            f"{inputs.profile} / {_profile_enforcement(inputs.profile)} / {egress}",
            "who maintains it · advisory warns, hard blocks",
        ),
        (
            "lifecycle / review cycles",
            f"{inputs.lifecycle} / {inputs.review_cycles}",
            "issue→branch→PR gates + merge review depth · adds process",
        ),
        (
            "MCP servers",
            ", ".join(m["id"] for m in inputs.selected_mcps) or "(none)",
            "each server = a new tool/egress capability",
        ),
        (
            "agent surfaces",
            ", ".join(inputs.agents),
            "each surface gets scaffolded config = a trust surface",
        ),
        (
            "governance / observability / multi-model",
            f"{'on' if inputs.governance else 'off'} / "
            f"{'on' if inputs.observability else 'off'} / "
            f"{'on' if inputs.multi_model else 'off'}",
            "AUP+SYSTEM_CARD gate · transcript metrics · CCR routing",
        ),
        ("language", inputs.language, "sets toolchain, lint/test commands"),
        (
            "delivery / deploy / iac",
            f"{inputs.delivery} / {inputs.deploy} / {inputs.iac}",
            "shapes CI, deploy workflow, devcontainer",
        ),
        (
            "memory",
            f"{inputs.memory} (tier {tier or '-'})",
            "graph/RAG are opt-in rungs; pay off at multi-project scale",
        ),
        (
            "devcontainer / mise / vscode",
            f"{'on' if inputs.devcontainer else 'off'} / "
            f"{'on' if inputs.mise else 'off'} / "
            f"{'on' if inputs.vscode else 'off'}",
            "reproducible dev env extras · more files",
        ),
        (
            "docs / renovate",
            f"{'on' if inputs.want_docs else 'off'} / {'on' if inputs.renovate else 'off'}",
            "docs site config · automated dependency PRs",
        ),
        (
            "owner / license",
            f"{inputs.owner or '(none)'} / {inputs.license_choice}",
            "CODEOWNERS + LICENSE files",
        ),
        (
            "co-author trailer",
            "on" if inputs.coauthor else "off",
            "Co-Authored-By: Claude on commits",
        ),
    )
    for concern, resolved, why in rows:
        table.add_row(concern, resolved, why)
    console.print(table)
    console.print(
        "[dim]safety.allow starts [] (deny-by-default) — hand-edit "
        ".agents/config.yaml to extend; preserved on re-run.[/dim]"
    )
    if memory_from_preset:
        # ADR-024: the wizard guidance must position the rag tier even when the
        # preset pinned the stack and the ladder chooser never ran.
        console.print(
            f"[dim]Memory came from preset '{preset_name or 'the chosen preset'}' — "
            "the full ladder (auto / obsidian / graphify / rag) is under "
            "Customize; the rag tier pays off only at multi-project / monorepo "
            "scale.[/dim]"
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
    cli_bootstrap: bool = False,
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
    cli_deploy_app: str = "",
    cli_deploy_region: str = "",
    cli_deploy_health_url: str = "",
    target: Path | None = None,
    preset_name: str = "",
    box_profile: BoxProfile | None = None,
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

    ADR-029 (the gateway collapse): the default path asks six questions —
    preset (before this function), name, description, language, the Customize
    gateway, and bootstrap. Every other concern lives in a gateway group; a
    group left unopened resolves to exactly the value its chooser's Enter
    default produced pre-collapse (flags always win over everything), and the
    full resolution is echoed before the final question.
    """
    _print_wizard_guidance()
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
    seeds = _CliSeeds(
        language=language,
        delivery=delivery_flag,
        deploy=deploy_flag,
        iac=iac_flag,
        multi_model=multi_model_flag,
        governance=governance_flag,
        observability=observability_flag,
        memory=memory_flag,
        preset_memory=preset_memory,
        lifecycle=lifecycle_flag,
        preset_lifecycle=preset_lifecycle,
        no_docs=no_docs,
        no_renovate=no_renovate,
        no_coauthor=no_coauthor,
        mcps=cli_mcps,
        browser=cli_browser,
        agents=cli_agents,
        owner=cli_owner,
        license_choice=cli_license,
        devcontainer=cli_devcontainer,
        mise=cli_mise,
        vscode=cli_vscode,
        review_cycles=cli_review_cycles,
        profile=profile,
        deploy_app=cli_deploy_app,
        deploy_region=cli_deploy_region,
        deploy_health_url=cli_deploy_health_url,
    )
    # ── ADR-029: resolve every concern to its standard-path value first (each
    # the value its chooser's Enter default produced pre-collapse; flags win). ──
    state, force_open = _default_gateway_state(seeds)
    box_advisory = _apply_box_profile(state, seeds, box_profile)
    if box_advisory:
        console.print(f"[dim]{box_advisory}[/dim]")

    def _build_inputs(*, bootstrap: bool) -> ScaffoldInputs:
        return ScaffoldInputs(
            project_name=project_name,
            project_description=project_description,
            language=language,
            selected_mcps=state.mcps,
            owner=state.owner,
            license_choice=state.license_choice,
            devcontainer=state.devcontainer,
            mise=state.mise,
            vscode=state.vscode,
            agents=state.agents,
            no_plugin=_profile_delivery_no_plugin(state.profile, no_plugin),
            profile=state.profile,
            no_egress=no_egress,
            python_version=python_version,
            review_cycles=state.review_cycles,
            delivery=state.delivery,
            deploy=state.deploy,
            deploy_app=state.deploy_app,
            deploy_region=state.deploy_region,
            deploy_health_url=state.deploy_health_url,
            iac=state.iac,
            multi_model=state.multi_model,
            governance=state.governance,
            observability=state.observability,
            memory=state.memory,
            lifecycle=state.lifecycle,
            want_docs=state.want_docs,
            renovate=state.renovate,
            coauthor=state.coauthor,
            bootstrap=bootstrap,
        )

    # The informed-consent preview (ADR-023 on the collapsed path): show the
    # full annotated resolution BEFORE the gateway, so accepting the standard
    # setup is a decision made looking at it, not a silent shortcut.
    _print_resolution_summary(
        _build_inputs(bootstrap=False),
        preset_name=preset_name,
        memory_from_preset=state.memory_from_preset,
        title="Standard setup (accept, or customize any group)",
    )
    opened = _choose_gateway_interactive(_pinned_gateway_flags(seeds)) | force_open
    _apply_opened_groups(state, opened, seeds)
    if opened:
        # Something changed — re-echo the final resolution before the last
        # question so what scaffolds is never stale relative to what was shown.
        _print_resolution_summary(
            _build_inputs(bootstrap=False),
            preset_name=preset_name,
            memory_from_preset=state.memory_from_preset,
            title="Resolved configuration",
        )

    # Post-scaffold bootstrap (#887) — the FINAL question. --bootstrap
    # pre-accepts and skips the prompt.
    return _build_inputs(bootstrap=True if cli_bootstrap else _choose_bootstrap_interactive())


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


def _choose_agents_interactive(default: tuple[str, ...] | None = None) -> list[str]:
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

    if default is not None:
        console.print(f"[dim]Enter keeps the box-profile default: {', '.join(default)}[/dim]")
    while True:
        raw = Prompt.ask(
            "Choose surfaces (comma-separated numbers, or Enter for default)",
            # Pre-collapse behavior when unseeded: Enter -> "1" -> the vscode
            # surface. A box-profile seed (BOX-1) becomes the Enter default.
            default="1" if default is None else "",
        )
        if not raw.strip():
            return list(default) if default is not None else ["claude", "vscode"]

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
