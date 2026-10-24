"""Scaffolded AGENTS.md tells agents how tests and CI work (#1107).

Asserts parsed structure: the `## Tests and CI` heading, its bullets' bold
labels, and the commands inside the right bullet — not a bare substring that a
comment or another section could satisfy.
"""

from __future__ import annotations

import re
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import make_variables, memory_preset


def _section(agents_md: str) -> dict[str, str]:
    """Return {bold bullet label: bullet text} for the `## Tests and CI` section."""
    sections = re.split(r"^## ", agents_md, flags=re.M)
    body = next((s for s in sections if s.startswith("Tests and CI\n")), None)
    assert body is not None, "AGENTS.md has no '## Tests and CI' section"
    bullets = re.findall(r"^- \*\*(.+?)\*\* — (.+)$", body, flags=re.M)
    return dict(bullets)


def _render(tmp_path: Path, **overrides: str) -> dict[str, str]:
    target = tmp_path / "p"
    scaffold(target, memory_preset("obsidian-only"), make_variables(**overrides))
    return _section((target / "AGENTS.md").read_text())


class TestTestsAndCiSection:
    def test_default_preset_answers_every_question(self, tmp_path: Path):
        s = _render(tmp_path)
        assert set(s) == {
            "Iterate / before pushing",
            "Pre-push hook",
            "Where CI runs",
            "Not per-PR",
            "Workflow files need the `workflows` permission",
            "Flaky locally is the machine, not the code",
            "Heavy suites belong in CI",
        }
        iterate = s["Iterate / before pushing"]
        for cmd in ("just test-quick", "just test", "just ci"):
            assert f"`{cmd}`" in iterate
        where = s["Where CI runs"]
        assert "vars.CI_RUNS_ON" in where
        assert "runnerName" in where
        assert "(.agents/docs/guides/self-hosted-ci-runner.md)" in where
        assert "mutation tests" in s["Not per-PR"]
        assert "403" in s["Not per-PR"]
        assert "gh workflow run ci.yml --ref <branch> -f cadence=nightly" in s["Not per-PR"]
        assert "has no" not in s["Not per-PR"]
        assert (
            "refusing to allow a GitHub App" in s["Workflow files need the `workflows` permission"]
        )

    def test_lifecycle_off_drops_pre_push_bullet(self, tmp_path: Path):
        s = _render(tmp_path, lifecycle="", lifecycle_off="true")
        assert "Pre-push hook" not in s
        assert "Where CI runs" in s

    def test_no_lint_command_drops_recipe_bullet(self, tmp_path: Path):
        s = _render(tmp_path, lint_command="")
        assert "Iterate / before pushing" not in s
        assert "Heavy suites belong in CI" in s

    def test_non_python_drops_mutation_tests(self, tmp_path: Path):
        s = _render(tmp_path, language="node", python="", node="true")
        assert "mutation tests" not in s["Not per-PR"]
        assert "nightly fuzz" in s["Not per-PR"]

    def test_section_stays_small(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, memory_preset("obsidian-only"), make_variables())
        text = (target / "AGENTS.md").read_text()
        body = text.split("## Tests and CI\n", 1)[1].split("\n## ", 1)[0]
        assert len(body.strip().splitlines()) <= 15
