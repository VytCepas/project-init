"""The review gate's Codex-marker scan must read the WHOLE comment history.

A byte-identity re-pin proves the rendered bytes match a blessed snapshot; it
never executes the pipeline, so a broken implementation stays green the moment
its hash is re-pinned (Codex P1 on #986). This runs the scan.

The unit under test is the `CODEX_REVIEWS=$(...)` assignment as RENDERED into a
scaffold — extracted from the workflow rather than retyped, because a copy here
would pass while the shipped file was wrong, which is the defect this file
exists to rule out.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables

# Two pages. The marker is on the SECOND one, which is the whole point: a
# single-page reader returns 0 here and a paginating one returns 1.
#
# The review names the head it reviewed, because since PI-981 a comment review
# counts only for that commit (test_review_gate_current_head.py). Without the
# line, this would read 0 for the wrong reason and prove nothing about paging.
_HEAD = "c4c4817225" + "ab" * 15
_PAGE_ONE = """{"data":{"repository":{"pullRequest":{"comments":{
  "pageInfo":{"hasNextPage":true,"endCursor":"CUR"},
  "nodes":[{"author":{"login":"someone"},"body":"unrelated chatter"}]}}}}}"""
_PAGE_TWO = """{"data":{"repository":{"pullRequest":{"comments":{
  "pageInfo":{"hasNextPage":false,"endCursor":null},
  "nodes":[{"author":{"login":"chatgpt-codex-connector"},
            "body":"Codex Review: found nothing **Reviewed commit:** `c4c4817225`"}]}}}}}"""


def _scaffold_with_lifecycle(target: Path) -> Path:
    """Render a lifecycle-ON scaffold and return its review-status workflow.

    The workflows live in the `lifecycle` overlay, not in base, so a plain
    `scaffold(preset)` does not produce the file under test (#476).
    """
    preset = load_preset("obsidian-only")
    stack = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    extra = overlay_layers([], no_plugin=False, memory_stack=stack, lifecycle=True)
    preset = {**preset, "layers": [*preset["layers"], *extra]}
    scaffold(target, preset, make_variables(memory_stack=stack, plugin_mode="true"))
    return target / ".github" / "workflows" / "review-status.yml"


def _extract_codex_scan(workflow: Path) -> str:
    """The `CODEX_REVIEWS=$(...)` assignment, dedented out of the YAML block."""
    text = workflow.read_text()
    start = text.index("          CODEX_REVIEWS=$(")
    end = text.index("| length')", start) + len("| length')")
    return "\n".join(line[10:] for line in text[start:end].splitlines())


def _stub_gh(bin_dir: Path, *, paginate: bool) -> None:
    """A `gh` that serves two pages, or only the first when paginate is False."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "gh"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f"paginate={'1' if paginate else '0'}\n"
        'if [ "$paginate" = 1 ]; then\n'
        f"  cat <<'P1'\n{_PAGE_ONE}\nP1\n"
        f"  cat <<'P2'\n{_PAGE_TWO}\nP2\n"
        "else\n"
        f"  cat <<'P1'\n{_PAGE_ONE}\nP1\n"
        "fi\n"
    )
    stub.chmod(0o755)


def _run_scan(script: str, bin_dir: Path, tmp: Path) -> str:
    runner = tmp / "scan.sh"
    runner.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n" + script + '\necho "$CODEX_REVIEWS"\n'
    )
    runner.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    # AUTHOR is the PR author the scan compares the commenter against (PI-1003).
    # Anyone but the connector, so this file keeps measuring pagination alone.
    env.update(OWNER="o", REPO_NAME="r", PR_NUMBER="1", SHA=_HEAD, AUTHOR="pr-author")
    out = subprocess.run(["bash", str(runner)], capture_output=True, text=True, env=env, cwd=tmp)
    assert out.returncode == 0, f"scan failed: {out.stdout}\n{out.stderr}"
    return out.stdout.strip()


@pytest.mark.skipif(not shutil.which("jq"), reason="jq is required by the scan")
def test_codex_marker_beyond_the_first_page_is_counted(tmp_path: Path):
    """A marker on page two must be found. The old single-page reader missed it."""
    script = _extract_codex_scan(_scaffold_with_lifecycle(tmp_path / "proj"))

    # The shipped scan, against a gh that serves both pages.
    bin_ok = tmp_path / "bin-ok"
    _stub_gh(bin_ok, paginate=True)
    assert _run_scan(script, bin_ok, tmp_path) == "1"

    # THE FALSIFIER, and it is the reason this test exists rather than a hash:
    # the same script against a gh that serves only the first page is exactly
    # the old `comments(last:100)` behaviour, and it must come back empty.
    bin_window = tmp_path / "bin-window"
    _stub_gh(bin_window, paginate=False)
    assert _run_scan(script, bin_window, tmp_path) == "0"


@pytest.mark.skipif(not shutil.which("jq"), reason="jq is required by the scan")
def test_the_scan_actually_paginates(tmp_path: Path):
    """`--paginate` and the cursor plumbing must be present in what ships.

    Behaviour above proves the marker is found; this pins HOW, because a stub
    that returns everything on one call would let a non-paginating script pass
    the behavioural check. Both halves are needed.
    """
    script = _extract_codex_scan(_scaffold_with_lifecycle(tmp_path / "proj"))
    assert "--paginate" in script
    assert "$endCursor" in script
    assert re.search(r"pageInfo\s*{\s*hasNextPage\s+endCursor\s*}", script)
    # `--paginate` emits one document per page, so the filter must slurp.
    assert "jq -s" in script


def test_thread_state_is_sampled_after_the_marker_scan(tmp_path: Path):
    """Sampling threads BEFORE pagination lets a mid-run review post a false green.

    `--paginate` walks pages sequentially, so a review published during the walk
    can be seen by a later page while `reviewThreads` still holds the pre-review
    state — a review counted, no unresolved threads, SUCCESS over live findings.
    Ordering is the fix, so ordering is what this asserts (Codex P2 on #986).
    """
    text = _scaffold_with_lifecycle(tmp_path / "proj").read_text()
    assert text.index("CODEX_REVIEWS=$(") < text.index("REVIEW_DATA=$("), (
        "reviewThreads is sampled before the comment pagination — a review landing "
        "mid-walk would be counted while its threads were not"
    )
