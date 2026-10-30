"""#1026: the scaffolder's closing instruction states how Claude Code picks the scaffold up.

It used to say `cd into the project and run claude — it picks up CLAUDE.md and
.agents/ automatically`. Both halves were wrong: Claude Code reads the `.claude/`
projection, never `.agents/` (ADR-027 measured a hook wired only in `.agents/`
not firing), and "cd into the project" is the whole condition — project
settings, hooks and plugins load only in a session started there.

The closing line therefore names three facts, and these tests pin each one to
what the scaffold actually rendered rather than to a copy of the wording:

* the CONDITION — the exact `cd <target> && claude` command, and that a session
  started elsewhere loads none of it;
* the DIRECTORY — `.claude/` is named, and every mention of `.agents/` says
  Claude Code does not read it;
* the SCOPE — the plugins it names are exactly the `@project-init` entries the
  rendered `.claude/settings.json` enables, so a change to the plugin split
  cannot leave the sentence behind.
"""

from __future__ import annotations

import io
import json
import re
import shlex
from pathlib import Path

import pytest
from rich.console import Console

import project_init.cli_output as cli_output
from project_init.console import WIZARD_THEME
from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_MODES = {
    "plugin": [],
    "plugin-no-lifecycle": ["--lifecycle", "none"],
    "no-plugin": ["--no-plugin"],
}


def _enabled_project_init_plugins(target: Path) -> set[str]:
    """The project-init plugins the rendered `.claude/settings.json` enables."""
    settings = json.loads((target / ".claude" / "settings.json").read_text())
    return {
        key.removesuffix("@project-init")
        for key, on in settings.get("enabledPlugins", {}).items()
        if key.endswith("@project-init") and on is True
    }


def _start_block(stdout: str) -> list[str]:
    """The `Start:` line and its continuation lines, stripped."""
    lines = stdout.splitlines()
    first = next(i for i, line in enumerate(lines) if line.strip().startswith("Start:"))
    block = [lines[first].strip()]
    for line in lines[first + 1 :]:
        if not line.strip():
            break
        block.append(line.strip())
    return block


def _scaffold_and_capture(target: Path, extra: list[str], capsys) -> list[str]:
    from project_init.__main__ import main

    rc = main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            "core",
            "--name",
            "p",
            "--description",
            "d",
            "--language",
            "none",
            *extra,
        ]
    )
    assert rc == 0
    return _start_block(capsys.readouterr().out)


@pytest.mark.parametrize("mode", list(_MODES))
class TestClosingLine:
    def test_names_the_condition(self, mode: str, tmp_target: Path, capsys):
        block = _scaffold_and_capture(tmp_target, _MODES[mode], capsys)
        assert block[0] == f"Start: cd {shlex.quote(str(tmp_target.resolve()))} && claude"
        text = " ".join(block)
        assert "Only a session started in this project" in text
        assert "anywhere else" in text

    def test_names_claude_dir_and_never_claims_agents_is_read(
        self, mode: str, tmp_target: Path, capsys
    ):
        block = _scaffold_and_capture(tmp_target, _MODES[mode], capsys)
        text = " ".join(block)
        assert ".claude/" in text
        assert "picks up" not in text
        agents_lines = [line for line in block if ".agents/" in line]
        assert agents_lines, "the line must say what .agents/ is, not drop it"
        for line in agents_lines:
            assert "does not read" in line, f"claims .agents/ is read: {line!r}"

    def test_names_exactly_the_plugins_the_scaffold_enables(
        self, mode: str, tmp_target: Path, capsys
    ):
        block = _scaffold_and_capture(tmp_target, _MODES[mode], capsys)
        text = " ".join(block)
        enabled = _enabled_project_init_plugins(tmp_target)
        named = set(re.findall(r"project-init-(?:workflow|lifecycle)", text))
        assert named == enabled
        if enabled:
            assert f"{len(enabled)} project-scoped plugin" in text
            assert "user scope" in text
        else:
            assert "--no-plugin" in text


def test_rich_panel_prints_the_same_lines(tmp_target: Path, monkeypatch):
    """The TTY panel and the plain summary render one list of lines, so they
    cannot disagree; a long target path folds instead of being cut to `…`."""
    buf = io.StringIO()
    monkeypatch.setattr(cli_output, "is_interactive", lambda: True)
    monkeypatch.setattr(
        cli_output, "console", Console(file=buf, width=400, theme=WIZARD_THEME, color_system=None)
    )
    plugins = ["project-init-workflow", "project-init-lifecycle"]
    cli_output._print_summary(tmp_target, [tmp_target / "x"], "core", plugins=plugins)
    rendered = " ".join(buf.getvalue().split())
    for line in cli_output._start_lines(tmp_target, plugins):
        assert " ".join(line.split()) in rendered
    assert "picks up" not in rendered


class TestScaffoldedClaudeMd:
    """The operator who needs the three facts a week later reads CLAUDE.md, not
    terminal output. They live there rather than in AGENTS.md because they are
    Claude-only and AGENTS.md is read by every agent under a word budget."""

    @staticmethod
    def _claude_md(target: Path) -> str:
        return (target / "CLAUDE.md").read_text()

    @pytest.mark.parametrize(
        "overrides",
        [{}, {"lifecycle": "", "lifecycle_off": "true"}, {"plugin_mode": "", "no_plugin": "true"}],
        ids=["plugin", "plugin-no-lifecycle", "no-plugin"],
    )
    def test_states_condition_directory_and_scope(self, tmp_path: Path, overrides: dict[str, str]):
        t = tmp_path / "p"
        scaffold(t, load_preset("core"), make_variables(**overrides))
        text = self._claude_md(t)
        # The import that delivers AGENTS.md must survive, bare, on its own line.
        assert "@AGENTS.md" in text.splitlines()
        assert "Only in a session started here." in text
        assert "reads its config from `.claude/`" in text
        assert "does not read `.agents/` itself" in text
        enabled = _enabled_project_init_plugins(t)
        named = set(re.findall(r"`(project-init-(?:workflow|lifecycle))`", text))
        assert named == enabled
        install = "`claude plugin install project-init-workflow@project-init --scope user`"
        assert (install in text) == bool(enabled)
        assert ("`project-init-lifecycle@project-init`" in text) == (
            "project-init-lifecycle" in enabled
        )
        if not enabled:
            assert "`--no-plugin`" in text

    @pytest.mark.parametrize(
        "overrides",
        [
            {},
            {
                "project_init_github": "",
                "project_init_enterprise": "true",
                "project_init_repo_url": "https://ghe.example.com/org/project-init.git",
            },
        ],
        ids=["github", "enterprise"],
    )
    def test_marketplace_add_names_the_rendered_source(
        self, tmp_path: Path, overrides: dict[str, str]
    ):
        t = tmp_path / "p"
        scaffold(t, load_preset("core"), make_variables(**overrides))
        settings = json.loads((t / ".claude" / "settings.json").read_text())
        source = settings["extraKnownMarketplaces"]["project-init"]["source"]
        expected = source.get("repo") or source.get("url")
        assert expected
        assert f"`claude plugin marketplace add {expected}`" in self._claude_md(t)


class TestNoScaffoldedClaimThatAgentsDirIsRead:
    def test_rules_line_names_the_projection(self, tmp_path: Path):
        t = tmp_path / "p"
        scaffold(t, load_preset("core"), make_variables())
        text = (t / ".agents" / "project-init.md").read_text()
        rules = next(line for line in text.splitlines() if line.startswith("**Rules**"))
        assert "`.claude/rules/`" in rules
        assert "loaded automatically by Claude Code" not in rules

    def test_no_plugin_hook_wiring_names_the_projection(self, tmp_path: Path):
        t = tmp_path / "p"
        scaffold(t, load_preset("core"), make_variables(plugin_mode="", no_plugin="true"))
        section = (t / "AGENTS.md").read_text().partition("## Claude Code specifics")[2]
        hooks = next(line for line in section.splitlines() if "fire automatically" in line)
        assert "`.claude/settings.json` projection" in hooks
        pinit = (t / ".agents" / "project-init.md").read_text()
        hooks = next(line for line in pinit.splitlines() if line.startswith("Hooks run"))
        assert "`.claude/settings.json` projection" in hooks
