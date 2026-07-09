"""PI-659 (epic #641): project-init.md defers to single sources, no duplication.

The Commit-and-PR format table (canonical: AGENTS.md quick-ref + the
github_workflow skill) and the compaction preserve-list (canonical: CLAUDE.md)
were duplicated verbatim in project-init.md — three drifting copies of the
same rules. The file now points at the single source; the rest of the
GitHub-tracking section stays (it is the lifecycle doc for skill-less
surfaces).
"""

from __future__ import annotations

import re
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


class TestProjectInitMdDedupe:
    def test_format_table_replaced_by_pointer(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        content = (tmp_target / ".agents" / "project-init.md").read_text()
        # Pointer to the single source, types list retained inline.
        assert "quick-ref" in content
        assert "feat` · `fix` · `chore` · `docs` · `test" in content
        # The duplicated table rows are gone.
        assert "| Commit message |" not in content
        # nojira flow (not duplicated elsewhere at this detail) stays.
        assert "create_nojira_pr.sh" in content

    def test_compact_preserve_list_lives_only_in_claude_md(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        project_init = (tmp_target / ".agents" / "project-init.md").read_text()
        claude_md = (tmp_target / "CLAUDE.md").read_text()
        marker = "Unresolved errors or lint failures"
        assert marker in claude_md  # canonical copy intact
        assert marker not in project_init  # duplicate removed
        assert "CLAUDE.md" in project_init  # pointer present

    def test_pointer_links_resolve(self, tmp_target: Path):
        """project-init.md lives in .agents/, so the ACTUAL hrefs in the
        rendered file must resolve from there (a link to plain `AGENTS.md`
        instead of `../AGENTS.md` would be broken)."""
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        source = tmp_target / ".agents" / "project-init.md"
        content = source.read_text()
        hrefs = re.findall(r"\]\(([^)#]+)\)", content)
        pointer_hrefs = [h for h in hrefs if h.endswith(("AGENTS.md", "CLAUDE.md"))]
        # Both dedup pointers are present as real links...
        assert any(h.endswith("AGENTS.md") for h in pointer_hrefs)
        assert any(h.endswith("CLAUDE.md") for h in pointer_hrefs)
        # ...and every one of them resolves relative to the file's location.
        for href in pointer_hrefs:
            assert (source.parent / href).resolve().exists(), f"broken href {href!r}"
