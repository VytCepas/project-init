"""PI-688: deterministic staleness guards for hand-maintained "territory".

Two mechanically-verifiable facts that used to live in multiple hand-kept copies
with nothing tying them together (map-not-territory, ADR-024):

1. The lifecycle DAG: authoritative in ``GRAPH`` (dag_workflow.py), redrawn as
   ASCII in workflow_state_reminder.sh. A node added to GRAPH without updating
   the reminder is silent drift.
2. Committed Mermaid diagrams: nodes carry repo-relative paths (the diagram
   skill's labels-carry-paths rule, PI-684) so a diagram that still points at a
   moved/deleted file is a lie. This makes diagrams safe as navigational memory.

SCOPE NOTE (decided, PI-688): the dangling-path check runs on ``.mmd`` diagrams
only, NOT on docs/**/*.md or skills. Those corpora describe the *scaffolded
output* (e.g. ``.agents/memory/MEMORY.md``) and template-relative names (e.g.
``dot_agents/hooks/...``), so a repo-root existence check false-positives on ~49
legitimate files — a noise machine, not a guard. Diagrams reference real repo
paths, so the check is precise there.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_HOOKS = _ROOT / ".agents" / "hooks"


def _graph_nodes() -> set[str]:
    spec = importlib.util.spec_from_file_location("dag_workflow", _HOOKS / "dag_workflow.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    graph: dict[str, list[str]] = mod.GRAPH
    return set(graph) | {dep for deps in graph.values() for dep in deps}


def test_reminder_ascii_dag_matches_graph():
    """The reminder's ASCII arrow diagram must name exactly the GRAPH nodes.

    Break it: add a node to GRAPH (or drop one from the ASCII) and this fails —
    which is the point, since nothing else ties the hand-drawn diagram to the
    authoritative dict.
    """
    reminder = (_HOOKS / "workflow_state_reminder.sh").read_text(encoding="utf-8")
    arrow_lines = [ln for ln in reminder.splitlines() if "->" in ln]
    ascii_nodes = set(re.findall(r"[a-z]+\.[a-z]+", " ".join(arrow_lines)))
    assert ascii_nodes == _graph_nodes(), (
        "lifecycle DAG drift: the reminder's ASCII diagram and dag_workflow.py's "
        f"GRAPH name different node sets (ascii={sorted(ascii_nodes)})"
    )


# A repo-relative path token: has a slash and ends in a .ext. Excludes URLs. The
# optional leading dot keeps dotdirs like `.agents/...` intact (else the dot is
# dropped and a real path reads as missing).
_PATH_TOKEN = re.compile(r"\.?[A-Za-z0-9_][A-Za-z0-9_./-]*/[A-Za-z0-9_.-]+\.[A-Za-z0-9]+")


def test_committed_diagrams_reference_only_real_paths():
    """Every repo-relative path a committed .mmd names must resolve — else the
    diagram points at a file that moved or was deleted (stale map).
    """
    bad: dict[str, list[str]] = {}
    for mmd in sorted(_ROOT.glob("docs/diagrams/**/*.mmd")):
        # Mermaid separates label lines with a literal `\n`; turn it into a space
        # so a path after it isn't glued onto the previous token (n.agents/...).
        text = mmd.read_text(encoding="utf-8").replace("\\n", " ")
        for tok in sorted(set(_PATH_TOKEN.findall(text))):
            if tok.startswith(("http://", "https://")):
                continue
            if not (_ROOT / tok).exists():
                bad.setdefault(mmd.relative_to(_ROOT).as_posix(), []).append(tok)
    assert not bad, f"committed diagram(s) reference missing repo paths: {bad}"
