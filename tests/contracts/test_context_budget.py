"""PI-694 (epic #641 WS12): token-budget lint gate for always-loaded context files.

Every line of CLAUDE.md/AGENTS.md is re-sent each turn and every line of a
SKILL.md is paid on each skill load, so growth there is a per-turn token tax.
WS7/WS11 trimmed the content; this gate keeps it trimmed: scaffolded projects
get `.agents/scripts/lint_context_budget.sh` wired into every language's
`just lint` recipe (which scaffolded CI runs), and `lint_memory.sh` gains a
per-file size cap. The repo-side tests here hold this repo's own always-loaded
files and every shipped SKILL.md to the same budgets.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_SCRIPT = Path(".agents") / "scripts" / "lint_context_budget.sh"


def _run_gate(target: Path, env_overrides: dict[str, str] | None = None):
    env = {**os.environ, **(env_overrides or {})}
    return subprocess.run(
        ["bash", str(target / _SCRIPT)],
        cwd=str(target),
        capture_output=True,
        text=True,
        env=env,
    )


class TestScaffoldedGate:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        scaffold(tmp_target, fallback_preset(), fallback_variables())

    def test_script_scaffolds_executable(self):
        script = self.target / _SCRIPT
        assert script.is_file()
        assert script.stat().st_mode & 0o111

    def test_fresh_scaffold_passes_its_own_gate(self):
        result = _run_gate(self.target)
        assert result.returncode == 0, f"gate failed on fresh scaffold: {result.stderr}"

    def test_gate_fails_on_oversized_agents_md(self):
        agents_md = self.target / "AGENTS.md"
        agents_md.write_text(agents_md.read_text() + "padding line\n" * 250)
        result = _run_gate(self.target)
        assert result.returncode == 1
        assert "AGENTS.md" in result.stderr
        assert "budget" in result.stderr

    def test_gate_fails_on_oversized_skill(self):
        bloated = self.target / ".agents" / "skills" / "bloat" / "SKILL.md"
        bloated.parent.mkdir(parents=True)
        bloated.write_text("skill line\n" * 600)
        result = _run_gate(self.target)
        assert result.returncode == 1
        assert "bloat/SKILL.md" in result.stderr

    def test_thresholds_are_env_overridable(self):
        agents_md = self.target / "AGENTS.md"
        agents_md.write_text(agents_md.read_text() + "padding line\n" * 250)
        result = _run_gate(self.target, {"CONTEXT_BUDGET_LINES": "10000"})
        assert result.returncode == 0, result.stderr


class TestJustfileWiring:
    def test_every_lint_recipe_runs_the_gate(self):
        """Each language block ships its own `lint` recipe; the gate must be a
        trailer of all of them so scaffolded CI (`just lint`) enforces it
        regardless of language choice."""
        template = (REPO_ROOT / "templates" / "base" / "justfile.tmpl").read_text()
        lint_recipes = sum(1 for line in template.splitlines() if line.startswith("lint:"))
        gate_calls = template.count("lint_context_budget.sh")
        assert lint_recipes > 0
        assert gate_calls == lint_recipes, (
            f"{gate_calls} gate call(s) for {lint_recipes} lint recipe(s) — "
            "wire lint_context_budget.sh into every language's lint recipe"
        )

    def test_rendered_justfile_carries_the_gate(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        assert "lint_context_budget.sh" in (tmp_target / "justfile").read_text()


class TestMemorySizeCap:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        self.lint = self.target / ".agents" / "scripts" / "lint_memory.sh"

    def _run(self, env_overrides: dict[str, str] | None = None):
        env = {**os.environ, **(env_overrides or {})}
        return subprocess.run(
            ["bash", str(self.lint)],
            cwd=str(self.target),
            capture_output=True,
            text=True,
            env=env,
        )

    def test_starters_pass(self):
        result = self._run()
        assert result.returncode == 0, result.stderr

    def test_oversized_memory_file_errors(self):
        fact = self.target / ".agents" / "memory" / "user_role.md"
        fact.write_text(fact.read_text() + "detail line\n" * 120)
        result = self._run()
        assert result.returncode == 1
        assert "user_role.md" in result.stderr
        assert "cap" in result.stderr

    def test_cap_is_env_overridable(self):
        fact = self.target / ".agents" / "memory" / "user_role.md"
        fact.write_text(fact.read_text() + "detail line\n" * 120)
        result = self._run({"LINT_MEMORY_MAX_LINES": "10000"})
        assert result.returncode == 0, result.stderr


class TestRepoOwnBudgets:
    """This repo eats its own cooking: its always-loaded files and every
    SKILL.md it ships (repo, templates, plugins) obey the same budgets the
    scaffolded gate enforces."""

    def test_repo_claude_md_within_budget(self):
        for name in ("CLAUDE.md", "AGENTS.md"):
            lines = len((REPO_ROOT / name).read_text().splitlines())
            assert lines <= 200, f"{name} is {lines} lines (budget: 200)"

    def test_every_shipped_skill_within_budget(self):
        skill_files = [
            p
            for root in ("templates", "plugins", ".agents")
            for p in (REPO_ROOT / root).rglob("SKILL.md")
        ]
        assert skill_files, "no SKILL.md files found — glob roots moved?"
        oversized = {
            str(p.relative_to(REPO_ROOT)): n
            for p in skill_files
            if (n := len(p.read_text().splitlines())) > 500
        }
        assert not oversized, f"SKILL.md over 500-line budget: {oversized}"
