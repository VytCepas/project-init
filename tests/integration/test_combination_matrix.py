"""Combination-matrix smoke test for the à-la-carte decomposition (epic #470).

A green unit suite can hide a broken *corner* of the configuration space: the
overlays interact (memory × lifecycle × plugin-mode × language, plus the
toolchain toggles), and the per-feature tests each pin one axis. This drives the
real CLI (`main()` in `--strict` mode, which fails on any unrendered placeholder)
across the cross-product of the decomposition axes and asserts each combination
both renders cleanly AND gates the right files — so a future change that breaks
one corner can't pass on a green-elsewhere suite.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from project_init.__main__ import main

# The axes that genuinely interact (layer order, the plugin split, language
# gates). docs/renovate/overlay toggles are exercised at the extremes below.
_MEMORY = ["none", "obsidian", "obsidian-graphify"]
_LIFECYCLE = ["github", "none"]
_NO_PLUGIN = [False, True]
_LANGUAGE = ["python", "node", "go", "none"]

_MATRIX = list(itertools.product(_MEMORY, _LIFECYCLE, _NO_PLUGIN, _LANGUAGE))


def _run(target: Path, *extra: str) -> int:
    return main(
        [
            str(target),
            "--non-interactive",
            "--strict",
            "--preset",
            "core",
            "--name",
            "fx",
            "--description",
            "d",
            *extra,
        ]
    )


def _assert_well_formed(target: Path) -> dict:
    assert (target / "AGENTS.md").is_file(), "base layer missing"
    settings = json.loads((target / ".claude" / "settings.json").read_text())
    assert "enabledPlugins" in settings
    return settings


@pytest.mark.parametrize(
    "memory,lifecycle,no_plugin,language",
    _MATRIX,
    ids=lambda v: str(v),
)
def test_combination_renders_strict_clean(
    memory: str, lifecycle: str, no_plugin: bool, language: str, tmp_path: Path
):
    target = tmp_path / "p"
    flags = ["--language", language, "--memory", memory, "--lifecycle", lifecycle]
    if no_plugin:
        flags.append("--no-plugin")
    rc = _run(target, *flags)
    assert rc == 0, (
        f"strict render failed for memory={memory} lifecycle={lifecycle} "
        f"no_plugin={no_plugin} language={language}"
    )
    settings = _assert_well_formed(target)

    # The gating actually took effect for this combination — not just "renders".
    has_vault = (target / ".claude" / "vault").exists()
    assert has_vault == (memory != "none"), "memory gating wrong for this combo"

    has_lifecycle = (target / ".claude" / "scripts" / "start_issue.sh").exists()
    assert has_lifecycle == (lifecycle == "github"), "lifecycle gating wrong for this combo"

    # The two-plugin split (#476): the lifecycle plugin is enabled iff lifecycle
    # is on AND we are in plugin mode — enabled as `True`, and entirely ABSENT
    # (not present-as-false) otherwise, since the key is conditionally rendered.
    enabled = settings["enabledPlugins"]
    key = "project-init-lifecycle@project-init"
    if (lifecycle == "github") and not no_plugin:
        assert enabled.get(key) is True, "lifecycle plugin should be enabled for this combo"
    else:
        assert key not in enabled, "lifecycle plugin must be absent for this combo"

    # docs config follows language (python→mkdocs, node→typedoc) with want_docs on.
    assert (target / "mkdocs.yml").exists() == (language == "python")
    assert (target / "typedoc.json").exists() == (language == "node")


def test_minimal_extreme_renders_strict_clean(tmp_path: Path):
    """The leanest scaffold — everything declinable turned off."""
    target = tmp_path / "p"
    rc = _run(
        target,
        "--language",
        "none",
        "--memory",
        "none",
        "--lifecycle",
        "none",
        "--no-docs",
        "--no-renovate",
        "--no-plugin",
    )
    assert rc == 0
    _assert_well_formed(target)
    assert not (target / ".claude" / "vault").exists()
    assert not (target / ".claude" / "scripts" / "start_issue.sh").exists()
    assert not (target / "renovate.json").exists()


def test_maximal_extreme_renders_strict_clean(tmp_path: Path):
    """A loaded scaffold — opt-in overlays + toolchain all on."""
    target = tmp_path / "p"
    rc = _run(
        target,
        "--language",
        "python",
        "--memory",
        "obsidian-graphify",
        "--lifecycle",
        "github",
        "--multi-model",
        "--governance",
        "--observability",
        "--devcontainer",
        "--mise",
        "--vscode",
        "--agents",
        "claude,codex,antigravity",
    )
    assert rc == 0
    _assert_well_formed(target)
    assert (target / ".claude" / "vault").is_dir()
    assert (target / ".claude" / "scripts" / "start_issue.sh").is_file()
    assert (target / "mkdocs.yml").is_file()
    assert (target / "renovate.json").is_file()
