"""PI-981: `review/decision` counts only a review of the CURRENT head commit.

A review used to count for ever. Once one had landed and its threads were
resolved, every later push went green on commits nobody had reviewed. The gate's
header asked "has a review landed?" while the merge it guards needed "has THIS
code been reviewed?".

These tests run the whole "Post commit status" step as RENDERED into a scaffold,
extracted from the workflow rather than retyped, against a stub `gh`. They read
the status the step POSTS, never the workflow's text, because a text assertion
stays green while the shell it describes is broken.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables

# The connector names a commit by its first ten hex digits, so the two SHAs must
# differ inside those ten, or an OLD review would match HEAD by prefix.
HEAD = "c4c4817225" + "ab" * 15
OLD = "20e3701b6f" + "ab" * 15

pytestmark = pytest.mark.skipif(not shutil.which("jq"), reason="jq is required by the step")


def _workflow(target: Path) -> Path:
    """Render a lifecycle-ON scaffold and return its review-status workflow."""
    preset = load_preset("obsidian-only")
    stack = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    extra = overlay_layers([], no_plugin=False, memory_stack=stack, lifecycle=True)
    preset = {**preset, "layers": [*preset["layers"], *extra]}
    scaffold(target, preset, make_variables(memory_stack=stack, plugin_mode="true"))
    return target / ".github" / "workflows" / "review-status.yml"


def _step_script(workflow: Path) -> str:
    """The `run: |` body of the status step, dedented out of the YAML block."""
    lines = workflow.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "run: |") + 1
    return "\n".join(line[10:] for line in lines[start:])


_GH_STUB = """#!/usr/bin/env bash
case "$*" in
*"--method POST"*) printf '%s\\n' "$@" > "$T_POSTED" ;;
*"--json headRefOid"*) echo "$T_HEAD" ;;
*"--json reviewDecision"*) echo "$T_DECISION" ;;
*"--paginate repos/"*"/reviews"*) cat "$T_REVIEWS" ;;
*"graphql --paginate"*) cat "$T_COMMENTS" ;;
*"api graphql"*) cat "$T_THREADS" ;;
*) echo "unexpected gh call: $*" >&2; exit 97 ;;
esac
"""


def _codex_comment(body: str) -> dict[str, object]:
    return {"author": {"login": "chatgpt-codex-connector"}, "body": body}


def _clean_codex_review(sha: str) -> str:
    return f"Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** `{sha[:10]}`\n"


def _run_step(
    tmp_path: Path,
    *,
    reviews: list[dict[str, object]] | None = None,
    comments: list[dict[str, object]] | None = None,
    unresolved: int = 0,
    decision: str = "",
) -> dict[str, str]:
    script = _step_script(_workflow(tmp_path / "proj"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(_GH_STUB)
    (bin_dir / "gh").chmod(0o755)

    (tmp_path / "reviews.json").write_text(json.dumps(reviews or []))
    page = {
        "data": {
            "repository": {
                "pullRequest": {
                    "comments": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": comments or [],
                    }
                }
            }
        }
    }
    (tmp_path / "comments.json").write_text(json.dumps(page))
    threads = [{"isResolved": False}] * unresolved + [{"isResolved": True}]
    (tmp_path / "threads.json").write_text(
        json.dumps({"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": threads}}}}})
    )
    posted = tmp_path / "posted.txt"

    runner = tmp_path / "step.sh"
    runner.write_text("#!/usr/bin/env bash\n" + script + "\n")
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(
        GH_TOKEN="x",
        PR_NUMBER="7",
        REPO="o/r",
        OWNER="o",
        REPO_NAME="r",
        REVIEW_URL="",
        T_HEAD=HEAD,
        T_DECISION=decision,
        T_REVIEWS=str(tmp_path / "reviews.json"),
        T_COMMENTS=str(tmp_path / "comments.json"),
        T_THREADS=str(tmp_path / "threads.json"),
        T_POSTED=str(posted),
    )
    out = subprocess.run(
        ["bash", str(runner)], capture_output=True, text=True, env=env, cwd=tmp_path
    )
    assert out.returncode == 0, f"step failed: {out.stdout}\n{out.stderr}"
    fields = {}
    for arg in posted.read_text().splitlines():
        key, sep, value = arg.partition("=")
        if sep:
            fields[key] = value
    assert any(arg == f"repos/o/r/statuses/{HEAD}" for arg in posted.read_text().splitlines()), (
        "the status was not posted to the head SHA"
    )
    return fields


def test_a_formal_review_of_an_older_commit_does_not_count(tmp_path: Path):
    """THE DEFECT: a review of a previous head used to turn a new head green."""
    fields = _run_step(tmp_path, reviews=[{"commit_id": OLD, "state": "COMMENTED"}])
    assert fields["state"] == "pending"
    assert fields["description"] == f"Awaiting review of {HEAD[:7]}"


def test_a_formal_review_of_the_head_counts(tmp_path: Path):
    """The control. Without it, the test above passes for a gate that never goes green."""
    fields = _run_step(tmp_path, reviews=[{"commit_id": HEAD, "state": "COMMENTED"}])
    assert fields["state"] == "success"
    assert fields["description"] == "Reviewed — no open comments"


def test_a_codex_comment_review_of_an_older_commit_does_not_count(tmp_path: Path):
    fields = _run_step(tmp_path, comments=[_codex_comment(_clean_codex_review(OLD))])
    assert fields["state"] == "pending"


def test_a_codex_comment_review_of_the_head_counts(tmp_path: Path):
    fields = _run_step(tmp_path, comments=[_codex_comment(_clean_codex_review(HEAD))])
    assert fields["state"] == "success"


def test_a_codex_comment_that_names_no_commit_counts_for_nothing(tmp_path: Path):
    """Fail loud, not open: an unattributable review cannot vouch for the head."""
    fields = _run_step(tmp_path, comments=[_codex_comment("Codex Review: found nothing\n")])
    assert fields["state"] == "pending"


def test_an_unsubmitted_review_on_the_head_does_not_count(tmp_path: Path):
    fields = _run_step(tmp_path, reviews=[{"commit_id": HEAD, "state": "PENDING"}])
    assert fields["state"] == "pending"


def test_a_stale_approval_does_not_green_a_new_head(tmp_path: Path):
    """reviewDecision stays APPROVED across pushes; the head check must still hold."""
    fields = _run_step(
        tmp_path, reviews=[{"commit_id": OLD, "state": "APPROVED"}], decision="APPROVED"
    )
    assert fields["state"] == "pending"


def test_open_threads_still_fail_a_reviewed_head(tmp_path: Path):
    fields = _run_step(tmp_path, reviews=[{"commit_id": HEAD, "state": "COMMENTED"}], unresolved=2)
    assert fields["state"] == "failure"
    assert fields["description"] == "2 unresolved review comment(s)"


def test_the_head_check_needs_no_contents_scope(tmp_path: Path):
    """Formal reviews are read from REST, whose `commit_id` is a plain field.

    GraphQL's `reviews.nodes.commit` is a Commit object, which needs contents:read
    and killed this job on private repos once already. The permissions block
    must stay as narrow as it was.
    """
    text = _workflow(tmp_path / "proj").read_text()
    assert 'gh api --paginate "repos/${REPO}/pulls/${PR_NUMBER}/reviews"' in text
    permissions = text.split("\npermissions:\n", 1)[1].split("\n\n", 1)[0]
    assert "contents" not in permissions
    assert text.index("FORMAL_REVIEWS=$(") < text.index("REVIEW_DATA=$("), (
        "reviewThreads is sampled before the formal-review count — a review landing "
        "between the two would be counted while its threads were not"
    )
