"""PI-843: plugin-mode scaffolds must not register every skill twice.

The scaffold both enables project-init-workflow/-lifecycle in settings.json
AND (when a non-Claude surface like Codex is selected) checks skill copies
into `.agents/skills/` for that surface. Projecting those copies into
`.claude/skills/` made Claude load 18 skills twice per session (~2.4k wasted
tokens, doubled picker entries). The projection now skips plugin-provided
skills in plugin mode; the on-disk `.agents/` copies stay for the surfaces
that cannot read Claude plugins. Skills the plugins DON'T provide (plan) keep
projecting, and --no-plugin scaffolds keep the full projection.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from project_init.scaffold import PLUGIN_PROVIDED_SKILLS

_REPO = Path(__file__).resolve().parents[2]


def _scaffold(target: Path, *extra: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "project_init",
            str(target),
            "--non-interactive",
            "--preset",
            "core",
            "--name",
            "t",
            "--description",
            "t",
            "--language",
            "python",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_constant_matches_the_actual_plugin_payloads():
    plugins = _REPO / "plugins"
    if not plugins.is_dir():  # installed wheel — plugins/ is repo-only
        return
    actual = {
        d.name
        for plugin in ("project-init-workflow", "project-init-lifecycle")
        for d in (plugins / plugin / "skills").iterdir()
        if d.is_dir()
    }
    assert actual == PLUGIN_PROVIDED_SKILLS


def test_plugin_mode_projection_skips_plugin_provided_skills(tmp_path: Path):
    _scaffold(tmp_path, "--agents", "claude,codex")
    on_disk = {d.name for d in (tmp_path / ".agents" / "skills").iterdir() if d.is_dir()}
    projected = {d.name for d in (tmp_path / ".claude" / "skills").iterdir() if d.is_dir()}
    # Codex still gets its full on-disk set...
    assert on_disk >= PLUGIN_PROVIDED_SKILLS
    # ...but Claude's projection carries none of the plugin twins...
    assert not (projected & PLUGIN_PROVIDED_SKILLS)
    # ...while non-plugin skills still project.
    assert "plan" in projected


def test_no_plugin_scaffold_keeps_the_full_projection(tmp_path: Path):
    _scaffold(tmp_path, "--no-plugin")
    projected = {d.name for d in (tmp_path / ".claude" / "skills").iterdir() if d.is_dir()}
    # Without plugins the copies are Claude's only delivery mechanism.
    assert "github_workflow" in projected
    assert "save_memory" in projected
