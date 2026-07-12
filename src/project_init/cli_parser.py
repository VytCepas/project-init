"""project-init CLI argument parser and pre-scaffold input validators.

`_build_parser()` defines the full argparse surface; the validators reject bad
flag combinations (a `--python-version` with no Python, a target that is a file,
an undecodable existing config) before any files are written. Extracted from
__main__.py so the spine stays orchestration-only (PI-794). Imports constants
from variables; the WIZARD_*_FLAGS enumerations pair with the parser so
test_wizard_explanations.py can partition every flag into concern-or-mechanical.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from project_init import __version__
from project_init.variables import (
    SUPPORTED_PYTHON_VERSIONS,
    ScaffoldInputs,
    _python_floor_from_pyproject,
    _text_field_error,
)


def _reject_python_version_without_python(
    flag: str | None, language: str | None, parser: argparse.ArgumentParser
) -> None:
    """Refuse --python-version on a non-Python scaffold.

    Every python_floor consumer is gated on the `python` flag, so the value
    would render nowhere and a typo or wrapper bug would pass unnoticed
    (PR #713 review). Only checkable when --language is explicit; the wizard
    drops the flag with a warning instead, since language is chosen later.
    """
    if flag and language and language != "python":
        parser.error(
            f"--python-version {flag} requires --language python "
            f"(got --language {language}); nothing would consume the value."
        )


def _reject_conflicting_python_version(
    flag: str | None, target: Path | None, parser: argparse.ArgumentParser
) -> None:
    """Refuse a --python-version that contradicts a declared requires-python.

    project-init does not own pyproject.toml, and the scaffolded CI matrix
    derives from requires-python whenever it exists. Honoring the flag anyway
    would pin mise.toml/mypy.ini to one version while CI tested another — mypy
    would green-light syntax the oldest tested CPython cannot run (PR #713
    review). One value or none: make the user reconcile the declaration.
    """
    if not flag:
        return
    declared = _python_floor_from_pyproject(target)
    if declared and declared != flag:
        parser.error(
            f"--python-version {flag} conflicts with the requires-python floor "
            f"({declared}) declared in pyproject.toml. CI derives its matrix from "
            f"requires-python, so mise.toml and mypy.ini would pin {flag} while CI "
            f"tested {declared}. Set requires-python to >={flag}, or drop "
            f"--python-version to adopt the declared {declared}."
        )


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
        "--python-version",
        metavar="X.Y",
        choices=list(SUPPORTED_PYTHON_VERSIONS),
        help=(
            "Target CPython for a Python project — pins mise.toml, mypy.ini, and "
            "the CI matrix floor to one version "
            f"(choices: {', '.join(SUPPORTED_PYTHON_VERSIONS)}; "
            "default: pyproject.toml's requires-python floor, else "
            f"{SUPPORTED_PYTHON_VERSIONS[0]}). Rejected if it contradicts a "
            "declared requires-python."
        ),
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
        "--review-cycles",
        metavar="N",
        type=int,
        default=None,
        help=(
            "Review-fix passes the merge gate runs before it stops asking for "
            "another (#714): 0 disables review control and merges on green CI, "
            "1 comments once then merges, 2 (default) re-reviews the resolved "
            "comments. Requires the GitHub lifecycle."
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
        # Default None (not "claude") so an explicit `--agents claude` is
        # distinguishable from an absent flag: in interactive mode the former
        # honors the claude-only request, the latter opens the surface chooser.
        # Non-interactive resolution falls back to "claude" (claude is always
        # included regardless).
        default=None,
        help=(
            "Comma-separated agents/surfaces the project supports: claude "
            "(always included), codex, ollama, cursor, antigravity, vscode, amp, "
            "junie. Codex gets a native overlay; antigravity gets an .agents/ "
            "skills layer + generated hooks/MCP; cursor gets generated hooks+MCP; "
            "amp/junie get a skills layer + generated MCP config; vscode gets MCP "
            "config; ollama gets the portable AGENTS.md contract as a standalone "
            "surface (to run models with the full hooks/skills/MCP harness — "
            "local ones via Ollama, or cloud ones like DeepSeek/Kimi — route them "
            "through Claude Code with --multi-model) (PI-137, PI-366, PI-386, "
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


WIZARD_CONCERN_FLAGS: dict[str, str] = {
    "preset": "preset",
    "profile": "profile",
    "memory": "memory",
    "lifecycle": "lifecycle",
    "review_cycles": "review_cycles",
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


WIZARD_MECHANICAL_FLAGS: frozenset[str] = frozenset(
    {
        "help",
        "target",
        "name",
        "description",
        "language",
        "python_version",
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


def _require_non_interactive_args(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
    """Fail fast when --non-interactive is missing one of its required flags."""
    missing = []
    empty = []
    for value, flag in (
        (args.preset, "--preset"),
        (args.name, "--name"),
        (args.description, "--description"),
    ):
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
