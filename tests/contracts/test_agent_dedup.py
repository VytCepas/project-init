"""PI-848: don't emit local agents a built-in or an enabled plugin provides.

`explore.md` duplicated Claude Code's built-in Explore agent; `code-reviewer.md`
duplicated pr-review-toolkit's reviewer (pre-enabled whenever egress is
allowed). Both registered twice in the agent index every session. code-reviewer
survives only on --no-egress scaffolds, where marketplace plugins can't load
and the local copy is the only reviewer.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


def _agents_dir(tmp_path: Path, **overrides: str) -> Path:
    scaffold(tmp_path, fallback_preset(), fallback_variables(**overrides))
    return tmp_path / ".agents" / "agents"


def test_default_scaffold_ships_no_duplicate_agents(tmp_path: Path):
    agents = _agents_dir(tmp_path)
    assert not (agents / "explore.md").exists()
    assert not (agents / "code-reviewer.md").exists()
    # The how-to README still explains creating custom agents.
    assert (agents / "README.md").is_file()


def test_no_egress_scaffold_keeps_the_fallback_reviewer(tmp_path: Path):
    agents = _agents_dir(tmp_path, no_egress="true", egress_ok="")
    assert (agents / "code-reviewer.md").is_file()
    assert "name: code-reviewer" in (agents / "code-reviewer.md").read_text()
    # explore stays gone — the built-in exists regardless of egress.
    assert not (agents / "explore.md").exists()
