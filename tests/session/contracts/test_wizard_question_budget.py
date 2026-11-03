"""The wizard's question budget: a default run asks six questions or fewer (#988).

ADR-029 collapsed the wizard behind one Customize gateway, but nothing counted
the questions a run actually asks: the ticket measured the 22 chooser FUNCTIONS
(seams that ADR-029 kept on purpose), and a greenfield Python run still asked a
seventh question (Target Python). These tests count real prompt calls through
`main()` itself, so a new unconditional ask fails here rather than quietly
re-growing the wizard.

Every dropped question keeps its default (README + ADR-029) and its CLI flag; the
contract fields (tier, deploy block, SYSTEM_CARD fields, the Python pin) must
survive, the security surface must be echoed, and the record must round-trip
through `upgrade`.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

import project_init.__main__ as cli
from project_init.scaffold import memory_tier
from project_init.schema import load_descriptor_schema
from project_init.variables import SUPPORTED_PYTHON_VERSIONS

REPO = Path(__file__).resolve().parents[3]

BUDGET = 6

# The six asks that remain, in order. Labels are matched by prefix.
KEPT = (
    "Choose a preset",
    "Project name",
    "Description",
    "Language",
    "Customize groups",
    "Initialize everything now",
)


def _flat(text: str) -> str:
    """Drop table borders and whitespace so a wrapped cell still matches."""
    return re.sub(r"[│\s]+", "", text)


class _StopError(Exception):
    """Raised right after the wizard returns, before anything is scaffolded."""


def _install_prompts(monkeypatch, *, language: str, opened: str = "") -> list[str]:
    """Answer every rich prompt with its default (Enter), recording each label."""
    from rich.prompt import PromptBase

    labels: list[str] = []

    def ask(cls, prompt: Any = "", **kwargs: Any) -> Any:
        label = str(prompt)
        labels.append(label)
        if label.startswith("Language"):
            return language
        if label.startswith("Customize groups"):
            return opened
        return kwargs["default"]

    monkeypatch.setattr(PromptBase, "ask", classmethod(ask))
    # A prompt that bypasses rich would dodge the count; make it loud instead.
    monkeypatch.setattr(
        "builtins.input", lambda *a: (_ for _ in ()).throw(AssertionError("raw input()"))
    )
    return labels


def _ask_count(
    monkeypatch, tmp_path: Path, *, language: str, argv: tuple[str, ...] = ()
) -> list[str]:
    """Labels of every question `main()` asks before it would scaffold."""
    labels = _install_prompts(monkeypatch, language=language)

    def stop(inputs, parser):
        raise _StopError

    monkeypatch.setattr(cli, "_validate_text_inputs", stop)
    with pytest.raises(_StopError):
        cli.main([str(tmp_path), *argv])
    return labels


@pytest.mark.parametrize("language", ["python", "node", "go", "rust", "none"])
def test_a_default_run_asks_at_most_six_questions(monkeypatch, tmp_path: Path, language: str):
    labels = _ask_count(monkeypatch, tmp_path, language=language)
    assert len(labels) <= BUDGET, f"{len(labels)} questions asked: {labels}"


@pytest.mark.parametrize("language", ["python", "none"])
def test_the_six_questions_are_the_documented_six(monkeypatch, tmp_path: Path, language: str):
    """Pins WHICH questions remain, not just how many (the kept table in the PR)."""
    labels = _ask_count(monkeypatch, tmp_path, language=language)
    assert len(labels) == len(KEPT), labels
    for label, expected in zip(labels, KEPT, strict=True):
        assert label.startswith(expected), (label, expected)


def test_target_python_is_asked_only_inside_the_opened_extras_group(monkeypatch, tmp_path: Path):
    labels = _install_prompts(monkeypatch, language="python", opened="3")  # 3 = Dev extras

    def stop(inputs, parser):
        raise _StopError

    monkeypatch.setattr(cli, "_validate_text_inputs", stop)
    with pytest.raises(_StopError):
        cli.main([str(tmp_path)])
    asked = [label for label in labels if label.startswith("Target Python")]
    assert len(asked) == 1, labels


def test_dropped_target_python_keeps_its_flag_and_default(monkeypatch, tmp_path: Path):
    captured: dict[str, Any] = {}

    def stop(inputs, parser):
        captured["inputs"] = inputs
        raise _StopError

    _install_prompts(monkeypatch, language="python")
    monkeypatch.setattr(cli, "_validate_text_inputs", stop)
    with pytest.raises(_StopError):
        cli.main([str(tmp_path)])
    # Unset on the default path: the render derives the supported floor.
    assert captured["inputs"].python_version == ""

    flagged = tmp_path / "flagged"
    flagged.mkdir()
    with pytest.raises(_StopError):
        cli.main([str(flagged), "--python-version", SUPPORTED_PYTHON_VERSIONS[-1]])
    assert captured["inputs"].python_version == SUPPORTED_PYTHON_VERSIONS[-1]


def test_the_default_path_echoes_the_python_floor_it_chose(monkeypatch, tmp_path: Path, capsys):
    _ask_count(monkeypatch, tmp_path, language="python")
    assert f"(floor{SUPPORTED_PYTHON_VERSIONS[0]})" in _flat(capsys.readouterr().out)


# --- the contract survives the reduction (end to end, real scaffold) ---------


def _run_to_scaffold(monkeypatch, target: Path, *argv: str) -> list[str]:
    labels = _install_prompts(monkeypatch, language="python")
    # The bootstrap answer defaults to yes; running git/uv here is not under test.
    monkeypatch.setattr(cli, "_maybe_bootstrap", lambda *a, **k: None)
    assert cli.main([str(target), *argv]) == 0
    return labels


def _config(target: Path) -> dict[str, Any]:
    return yaml.safe_load((target / ".agents" / "config.yaml").read_text())


def test_default_scaffold_keeps_the_tier_pin_and_round_trips_upgrade(
    monkeypatch, tmp_path: Path, capsys
):
    labels = _run_to_scaffold(monkeypatch, tmp_path)
    assert len(labels) <= BUDGET

    config = _config(tmp_path)
    jsonschema.validate(config, load_descriptor_schema())
    memory = config["memory"]
    assert isinstance(memory["tier"], int)
    assert memory["tier"] == int(memory_tier(memory["stack"]))
    # The dropped Target Python question still pins exactly one floor.
    floor = SUPPORTED_PYTHON_VERSIONS[0]
    assert f"python_version = {floor}" in (tmp_path / "mypy.ini").read_text()
    assert (tmp_path / ".python-version").read_text().strip() == floor

    capsys.readouterr()
    assert cli.main(["upgrade", str(tmp_path)]) == 0
    assert "No drift" in capsys.readouterr().out


def _governance_required_fields() -> tuple[str, ...]:
    gate = REPO / "templates/governance/dot_agents/scripts/governance_gate.py"
    spec = importlib.util.spec_from_file_location("_governance_gate", gate)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.REQUIRED)


def test_governed_service_run_keeps_system_card_and_deploy_fields(
    monkeypatch, tmp_path: Path, capsys
):
    labels = _run_to_scaffold(
        monkeypatch,
        tmp_path,
        "--preset",
        "governed",
        "--delivery",
        "service",
        "--deploy",
        "cloud-run",
        "--deploy-app",
        "demo-app",
        "--deploy-region",
        "europe-west1",
        "--deploy-health-url",
        "https://demo.example/healthz",
    )
    assert len(labels) <= BUDGET

    config = _config(tmp_path)
    jsonschema.validate(config, load_descriptor_schema())
    assert config["deploy"] == {
        "target": "cloud-run",
        "app": "demo-app",
        "region": "europe-west1",
        "health_url": "https://demo.example/healthz",
    }

    required = _governance_required_fields()
    assert len(required) == 12
    template = (tmp_path / ".agents/governance/examples/system-card-template.md").read_text()
    for name in required:
        assert re.search(rf"^{name}:", template, re.M), f"SYSTEM_CARD field lost: {name}"

    capsys.readouterr()
    assert cli.main(["upgrade", str(tmp_path)]) == 0
    assert "No drift" in capsys.readouterr().out


def test_the_security_surface_is_echoed_before_the_gateway(monkeypatch, tmp_path: Path, capsys):
    _ask_count(monkeypatch, tmp_path, language="none")
    out = _flat(capsys.readouterr().out)
    gateway = out.index("Customize?")
    for row in (
        # The first line of each security-surface row (long cells wrap).
        "profile /",
        "lifecycle /",
        "MCP servers",
        "agent surfaces",
        "governance /",
        "marketplace egress",
    ):
        assert _flat(row) in out[:gateway], f"{row!r} not echoed before the gateway"


# --- #988 item 4: dormant sheds are a flag, off by default, one command back --

_DORMANT = {
    "multi-model": "--multi-model",
    "observability": "--observability",
    "memory obsidian-graphify-rag": "--memory obsidian-graphify-rag",
}


@pytest.mark.parametrize("restore,flag", _DORMANT.items())
def test_each_dormant_shed_documents_its_flag_and_one_restore_command(restore: str, flag: str):
    from project_init.concerns import CONCERNS

    assert restore.split()[0] in CONCERNS  # the command the README names exists
    readme = (REPO / "README.md").read_text()
    section = readme[readme.index("**Dormant by default.**") :]
    section = section[: section.index("Concerns:")]
    assert f"`{flag}`" in section
    assert f"`project-init add {restore} --apply`" in section
