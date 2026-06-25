"""Self-explaining wizard standard (#472, ADR-023).

Every selectable concern must explain its value before asking — what it ships, a
"Helps:" line (or an annotated option list), the cost, and the safe default. This
enforces that as a standard, not a per-feature habit:

- the enumeration source is the concrete CLI flag registry (`_build_parser`), so
  the coverage can't go vacuous — every flag must be classified as a concern
  with an explainer or as a mechanical/input flag;
- every registered concern's chooser is rendered and asserted to actually state
  its value, so a concern can't be registered with an empty explanation.
"""

from __future__ import annotations

import pytest

import project_init.__main__ as cli
from project_init.scaffold import list_presets


def test_every_flag_is_concern_or_mechanical():
    """Non-vacuity guard: a new CLI flag forces an explicit classification —
    either a value-explained concern or a documented mechanical/input flag."""
    dests = {a.dest for a in cli._build_parser()._actions}
    concern = set(cli.WIZARD_CONCERN_FLAGS.values())
    unaccounted = dests - concern - cli.WIZARD_MECHANICAL_FLAGS
    assert not unaccounted, (
        f"CLI flag(s) {sorted(unaccounted)} are neither a registered wizard "
        "concern (add an explainer + WIZARD_CONCERN_FLAGS entry) nor a mechanical "
        "flag (add to WIZARD_MECHANICAL_FLAGS) — see ADR-023."
    )


def test_concern_and_mechanical_are_disjoint_and_real():
    concern = set(cli.WIZARD_CONCERN_FLAGS.values())
    assert not (concern & cli.WIZARD_MECHANICAL_FLAGS), "a flag is both concern and mechanical"
    dests = {a.dest for a in cli._build_parser()._actions}
    assert concern <= dests, f"concern flags not in the parser: {concern - dests}"


def _explainer_calls() -> dict:
    """Map each concern → a thunk that renders its chooser (prompts mocked).

    Kept beside WIZARD_CONCERN_FLAGS by test_calls_cover_every_concern so a new
    concern can't be added without a render check.
    """
    presets = list_presets()
    return {
        "preset": lambda: cli._choose_preset_interactive(presets),
        "profile": cli._choose_profile_interactive,
        "memory": cli._choose_memory_interactive,
        "lifecycle": cli._choose_lifecycle_interactive,
        "delivery": lambda: cli._choose_delivery_interactive("python"),
        "deploy": cli._choose_deploy_interactive,
        "iac": cli._choose_iac_interactive,
        "multi_model": cli._choose_multi_model_interactive,
        "governance": cli._choose_governance_interactive,
        "observability": cli._choose_observability_interactive,
        "devcontainer": cli._choose_devcontainer_interactive,
        "mise": cli._choose_mise_interactive,
        "vscode": cli._choose_vscode_interactive,
        "docs": lambda: cli._choose_docs_interactive("python"),
        "renovate": cli._choose_renovate_interactive,
    }


def test_calls_cover_every_concern():
    assert set(_explainer_calls()) == set(cli.WIZARD_CONCERN_FLAGS), (
        "the render-check call map must cover exactly the registered concerns"
    )


@pytest.mark.parametrize("concern", sorted(cli.WIZARD_CONCERN_FLAGS))
def test_concern_renders_value_explanation(concern, monkeypatch, capsys):
    """Each concern's chooser must print a non-trivial explanation that states
    its value before the question — a `Helps:` line (panel concerns / toggles) or
    an annotated `name — what it brings` option list (pickers)."""
    # Mock every prompt so the chooser returns immediately without reading stdin.
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)
    monkeypatch.setattr("rich.prompt.IntPrompt.ask", lambda *a, **k: 1)
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: "")

    _explainer_calls()[concern]()
    out = capsys.readouterr().out

    assert out.strip(), f"{concern}: chooser printed no explanation"
    assert "\n" in out.strip(), f"{concern}: explanation is a single line, not a real description"
    assert "Helps:" in out or " — " in out, (
        f"{concern}: explanation states no value — needs a 'Helps:' line or an "
        "annotated option list (ADR-023)"
    )
