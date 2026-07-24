"""CLI entry point for `project-init` and `uvx project-init`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Re-exported for backward compat (importers of project_init.__main__).
from project_init.box_profile import load_box_profile
from project_init.cli_output import (
    _MEMORY_NEXT_STEPS as _MEMORY_NEXT_STEPS,
)
from project_init.cli_output import (
    _directory_tree as _directory_tree,
)
from project_init.cli_output import (
    _emit_preset_list as _emit_preset_list,
)
from project_init.cli_output import (
    _emit_scaffold_output as _emit_scaffold_output,
)
from project_init.cli_output import (
    _is_git_marker as _is_git_marker,
)
from project_init.cli_output import (
    _presets_payload as _presets_payload,
)
from project_init.cli_output import (
    _print_conflicts as _print_conflicts,
)
from project_init.cli_output import (
    _print_mcp_commands as _print_mcp_commands,
)
from project_init.cli_output import (
    _print_profile_notice as _print_profile_notice,
)
from project_init.cli_output import (
    _print_summary as _print_summary,
)
from project_init.cli_output import (
    _print_summary_plain as _print_summary_plain,
)
from project_init.cli_output import (
    _scaffold_result_payload as _scaffold_result_payload,
)

# Re-exported for backward compat (importers of project_init.__main__).
from project_init.cli_parser import (
    WIZARD_CONCERN_FLAGS as WIZARD_CONCERN_FLAGS,
)
from project_init.cli_parser import (
    WIZARD_MECHANICAL_FLAGS as WIZARD_MECHANICAL_FLAGS,
)
from project_init.cli_parser import (
    _build_parser as _build_parser,
)
from project_init.cli_parser import (
    _ensure_target_dir as _ensure_target_dir,
)
from project_init.cli_parser import (
    _reject_conflicting_python_version as _reject_conflicting_python_version,
)
from project_init.cli_parser import (
    _reject_python_version_without_python as _reject_python_version_without_python,
)
from project_init.cli_parser import (
    _require_non_interactive_args as _require_non_interactive_args,
)
from project_init.cli_parser import (
    _validate_existing_config as _validate_existing_config,
)
from project_init.cli_parser import (
    _validate_text_inputs as _validate_text_inputs,
)
from project_init.console import (
    scaffolding,
)
from project_init.scaffold import (
    TemplateRenderError,
    list_presets,
    overlay_layers,
    scaffold,
)

# Re-exported for backward compat (importers of project_init.__main__).
from project_init.subcommands import (
    _SUBCOMMANDS as _SUBCOMMANDS,
)
from project_init.subcommands import (
    _concern_main as _concern_main,
)
from project_init.subcommands import (
    _doctor_main as _doctor_main,
)
from project_init.subcommands import (
    _preset_main as _preset_main,
)
from project_init.subcommands import (
    _upgrade_main as _upgrade_main,
)
from project_init.variables import (
    _AGENT_SURFACES as _AGENT_SURFACES,
)
from project_init.variables import (
    _DELIVERY as _DELIVERY,
)
from project_init.variables import (
    _DELIVERY_ALIASES as _DELIVERY_ALIASES,
)
from project_init.variables import (
    _DELIVERY_SUMMARY as _DELIVERY_SUMMARY,
)
from project_init.variables import (
    _DEPLOY_CONTAINER as _DEPLOY_CONTAINER,
)
from project_init.variables import (
    _DEPLOY_OIDC as _DEPLOY_OIDC,
)
from project_init.variables import (
    _DEPLOY_SUMMARY as _DEPLOY_SUMMARY,
)
from project_init.variables import (
    _DEPLOY_TARGETS as _DEPLOY_TARGETS,
)
from project_init.variables import (
    _IAC_ALIASES as _IAC_ALIASES,
)
from project_init.variables import (
    _IAC_OPTIONS as _IAC_OPTIONS,
)
from project_init.variables import (
    _IAC_SUMMARY as _IAC_SUMMARY,
)
from project_init.variables import (
    _LANGUAGE_COMMANDS as _LANGUAGE_COMMANDS,
)
from project_init.variables import (
    _LIFECYCLE_TIERS as _LIFECYCLE_TIERS,
)
from project_init.variables import (
    _MEMORY_STACKS as _MEMORY_STACKS,
)
from project_init.variables import (
    _PROFILE_SUMMARY as _PROFILE_SUMMARY,
)
from project_init.variables import (
    _PROFILES as _PROFILES,
)
from project_init.variables import (
    _VALID_AGENTS as _VALID_AGENTS,
)

# Re-exported for backward compat (importers of project_init.__main__).
from project_init.variables import (
    SUPPORTED_PYTHON_VERSIONS as SUPPORTED_PYTHON_VERSIONS,
)
from project_init.variables import (
    ScaffoldInputs as ScaffoldInputs,
)
from project_init.variables import (
    _build_variables as _build_variables,
)
from project_init.variables import (
    _normalize_lifecycle as _normalize_lifecycle,
)
from project_init.variables import (
    _normalize_memory as _normalize_memory,
)
from project_init.variables import (
    _profile_delivery_no_plugin as _profile_delivery_no_plugin,
)
from project_init.variables import (
    _profile_enforcement as _profile_enforcement,
)
from project_init.variables import (
    _python_floor_from_pyproject as _python_floor_from_pyproject,
)
from project_init.variables import (
    _resolve_inputs as _resolve_inputs,
)
from project_init.variables import (
    _resolve_mcps_non_interactive as _resolve_mcps_non_interactive,
)
from project_init.variables import (
    _resolve_preset_lifecycle as _resolve_preset_lifecycle,
)
from project_init.variables import (
    _resolve_preset_memory as _resolve_preset_memory,
)
from project_init.variables import (
    _resolve_review_cycles as _resolve_review_cycles,
)
from project_init.variables import (
    _text_field_error as _text_field_error,
)
from project_init.variables import (
    _validate_review_cycles as _validate_review_cycles,
)
from project_init.variables import (
    agent_layers as agent_layers,
)
from project_init.variables import (
    render_run_command as render_run_command,
)
from project_init.variables import (
    resolve_agents as resolve_agents,
)
from project_init.variables import (
    resolve_delivery as resolve_delivery,
)
from project_init.variables import (
    resolve_deploy as resolve_deploy,
)
from project_init.variables import (
    resolve_iac as resolve_iac,
)

# Re-exported for backward compat (importers of project_init.__main__).
from project_init.wizard_prompts import (
    _choose_agents_interactive as _choose_agents_interactive,
)
from project_init.wizard_prompts import (
    _choose_bootstrap_interactive as _choose_bootstrap_interactive,
)
from project_init.wizard_prompts import (
    _choose_browser_interactive as _choose_browser_interactive,
)
from project_init.wizard_prompts import (
    _choose_coauthor_interactive as _choose_coauthor_interactive,
)
from project_init.wizard_prompts import (
    _choose_delivery_interactive as _choose_delivery_interactive,
)
from project_init.wizard_prompts import (
    _choose_deploy_interactive as _choose_deploy_interactive,
)
from project_init.wizard_prompts import (
    _choose_devcontainer_interactive as _choose_devcontainer_interactive,
)
from project_init.wizard_prompts import (
    _choose_docs_interactive as _choose_docs_interactive,
)
from project_init.wizard_prompts import (
    _choose_governance_interactive as _choose_governance_interactive,
)
from project_init.wizard_prompts import (
    _choose_iac_interactive as _choose_iac_interactive,
)
from project_init.wizard_prompts import (
    _choose_lifecycle_interactive as _choose_lifecycle_interactive,
)
from project_init.wizard_prompts import (
    _choose_mcps_interactive as _choose_mcps_interactive,
)
from project_init.wizard_prompts import (
    _choose_memory_interactive as _choose_memory_interactive,
)
from project_init.wizard_prompts import (
    _choose_mise_interactive as _choose_mise_interactive,
)
from project_init.wizard_prompts import (
    _choose_multi_model_interactive as _choose_multi_model_interactive,
)
from project_init.wizard_prompts import (
    _choose_observability_interactive as _choose_observability_interactive,
)
from project_init.wizard_prompts import (
    _choose_preset_interactive as _choose_preset_interactive,
)
from project_init.wizard_prompts import (
    _choose_profile_interactive as _choose_profile_interactive,
)
from project_init.wizard_prompts import (
    _choose_renovate_interactive as _choose_renovate_interactive,
)
from project_init.wizard_prompts import (
    _choose_review_cycles_interactive as _choose_review_cycles_interactive,
)
from project_init.wizard_prompts import (
    _choose_vscode_interactive as _choose_vscode_interactive,
)
from project_init.wizard_prompts import (
    _default_preset_index as _default_preset_index,
)
from project_init.wizard_prompts import (
    _explain_and_confirm as _explain_and_confirm,
)
from project_init.wizard_prompts import (
    _gather_inputs_interactive as _gather_inputs_interactive,
)
from project_init.wizard_prompts import (
    _gather_mcps_interactive as _gather_mcps_interactive,
)
from project_init.wizard_prompts import (
    _print_wizard_guidance as _print_wizard_guidance,
)
from project_init.wizard_prompts import (
    _prompt as _prompt,
)
from project_init.wizard_prompts import (
    _prompt_choice as _prompt_choice,
)
from project_init.wizard_prompts import (
    _prompt_menu_index as _prompt_menu_index,
)
from project_init.wizard_prompts import (
    _prompt_validated as _prompt_validated,
)
from project_init.wizard_prompts import (
    _resolve_iac_interactive as _resolve_iac_interactive,
)
from project_init.wizard_prompts import (
    _resolve_overlays_interactive as _resolve_overlays_interactive,
)
from project_init.wizard_prompts import (
    _select_preset as _select_preset,
)

# Every CPython a Python scaffold is willing to target (#628). Kept byte-equal
# to the `KNOWN` list in templates/base/dot_github/workflows/ci.yml.tmpl, which
# derives the test matrix from it — test_python_version_pins.py fails on drift.
# The first entry is the default floor when nothing else declares one.


# Per-tier "you run later" next-step for the chosen memory backend (#497). Only
# obsidian-graphify needs a one-time install; the rest are pure files.


# Wizard-explanation standard (#472, ADR-023): every selectable concern explains
# its value before asking — what it ships · a "Helps:" line · the honest cost ·
# the safe default. Heavyweight concerns (memory, lifecycle, overlays) render a
# full rich.Panel; lightweight toolchain toggles use this shared helper so the
# wizard stays scannable while still explaining each one. The coverage test in
# test_wizard_explanations.py enumerates the concerns against the CLI flags so a
# new concern can't ship without an explanation.


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


def _record_scaffold(
    target: Path, preset: dict[str, Any], variables: dict[str, str], created: list[Path]
) -> None:
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


def _maybe_bootstrap(args: argparse.Namespace, inputs: ScaffoldInputs, target: Path) -> None:
    """Run the post-scaffold bootstrap when opted in (#887).

    The wizard's final question / --bootstrap. Runs before the summary so its git
    init clears the "not a git repo" hint (computed structurally in
    _print_summary). In --json mode the report goes to stderr so a machine caller
    still sees best-effort failures without the sole JSON line being disturbed
    (#887 review).
    """
    if not inputs.bootstrap:
        return
    from project_init.bootstrap import print_bootstrap_report, run_bootstrap

    steps = run_bootstrap(target, language=inputs.language, coauthor=inputs.coauthor)
    print_bootstrap_report(steps, stderr=args.json)


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
        "doctor": lambda a: _doctor_main(a),
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
    # Before the target directory is created (PI-20) and before any prompt.
    # --language is optional; a non-interactive run resolves an absent one to
    # "none" (see _resolve_inputs), so validate against that rather than letting
    # None read as "unknown" and slip the flag through (PR #713 review). In an
    # interactive run the language is still unknown here — the wizard warns.
    effective_language = args.language or ("none" if args.non_interactive else None)
    _reject_python_version_without_python(args.python_version, effective_language, parser)
    _reject_conflicting_python_version(args.python_version, target, parser)

    # Select preset BEFORE creating the target directory — a typo'd --preset
    # should fail without leaving an empty dir behind.
    preset = _select_preset(args, parser, presets)
    # Memory backend fallback when --memory is absent (#466): the preset's stack
    # (obsidian-only/obsidian-graphify/core's "none"), default obsidian-only.
    preset_memory = _resolve_preset_memory(preset, parser)
    # Lifecycle-tier fallback when --lifecycle is absent (#476): the preset's
    # tier (a preset may set lifecycle = "none" to be minimal), default "github".
    preset_lifecycle = _resolve_preset_lifecycle(preset, parser)

    # Interactive runs may still change the tier at the prompt, so only a
    # non-interactive run can be judged here; the wizard warns in that case.
    _validate_review_cycles(
        args,
        parser,
        (_normalize_lifecycle(args.lifecycle) or preset_lifecycle)
        if args.non_interactive
        else _normalize_lifecycle(args.lifecycle),
    )

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
            cli_python_version=args.python_version,
            cli_review_cycles=args.review_cycles,
            cli_deploy_app=args.deploy_app,
            cli_deploy_region=args.deploy_region,
            cli_deploy_health_url=args.deploy_health_url,
            target=target,
            preset_name=str(preset.get("name", "")),
            # BOX-1 (harbor CONTRACTS/box-profile.md): advisory defaults from
            # the box; every failure path is None and changes nothing.
            box_profile=load_box_profile(),
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
            no_coauthor=args.no_coauthor,
            cli_bootstrap=args.bootstrap,
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
        with scaffolding():
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

    _maybe_bootstrap(args, inputs, target)
    _emit_scaffold_output(args, target, created, preset, variables, inputs, conflicts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
