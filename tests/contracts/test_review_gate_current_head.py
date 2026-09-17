"""PI-981: `review/decision` counts only a review of the CURRENT head commit.

A review used to count for ever. Once one had landed and its threads were
resolved, every later push went green on commits nobody had reviewed. The gate's
header asked "has a review landed?" while the merge it guards needed "has THIS
code been reviewed?".

PI-1003: and only a review by somebody OTHER THAN THE AUTHOR. GitHub records a
reply to a review thread as a formal COMMENTED review — empty body, the replier
as its user, the head it was written against as its commit_id — so the author's
own reply satisfied "a review of the head" on a commit no reviewer had seen.

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

# REST spells a bot's login with the `[bot]` suffix, and the author filter
# compares REST against REST — a fixture that dropped the suffix would hide a
# lookup that had drifted to GraphQL's spelling.
AUTHOR = "pr-author"
REVIEWER = "copilot-pull-request-reviewer[bot]"

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
jqprog=""; prev=""
for a in "$@"; do [ "$prev" = "--jq" ] && jqprog="$a"; prev="$a"; done
case "$*" in
*"--method POST"*) printf '%s\\n' "$@" > "$T_POSTED" ;;
*"--json headRefOid"*) echo "$T_HEAD" ;;
*"--json reviewDecision"*) echo "$T_DECISION" ;;
*"--paginate repos/"*"/reviews"*) cat "$T_REVIEWS" ;;
*"graphql --paginate"*) cat "$T_COMMENTS" ;;
*"api graphql"*) cat "$T_THREADS" ;;
# The PR object — whatever `repos/.../pulls/N` the arm above did not take. It is
# answered by running the step's OWN jq program over the fixture, so a lookup
# that read a field REST does not carry (GraphQL's `.author.login`) comes back
# empty here too. `gh --jq` prints a null as an empty line; `jq -r` prints
# "null", so the sed restores gh's answer.
*"api repos/"*"/pulls/"*) jq -r "$jqprog" "$T_PR" | sed 's/^null$//' ;;
*) echo "unexpected gh call: $*" >&2; exit 97 ;;
esac
"""


def _codex_comment(body: str) -> dict[str, object]:
    return {"author": {"login": "chatgpt-codex-connector"}, "body": body}


def _review(sha: str, state: str = "COMMENTED", login: str = REVIEWER) -> dict[str, object]:
    """A formal review, as REST `pulls/{n}/reviews` lists it."""
    return {"commit_id": sha, "state": state, "user": {"login": login}}


def _author_reply(sha: str) -> dict[str, object]:
    """The PR author's reply to a review thread, as REST records it: a formal
    COMMENTED review, empty body, on the head the reply was written against."""
    return {"commit_id": sha, "state": "COMMENTED", "body": "", "user": {"login": AUTHOR}}


def _clean_codex_review(sha: str) -> str:
    return f"Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** `{sha[:10]}`\n"


def _run_step(  # noqa: PLR0913 — one keyword argument per answer the stub gh serves
    tmp_path: Path,
    *,
    reviews: list[dict[str, object]] | None = None,
    comments: list[dict[str, object]] | None = None,
    unresolved: int = 0,
    decision: str = "",
    pr: dict[str, object] | None = None,
) -> dict[str, str]:
    script = _step_script(_workflow(tmp_path / "proj"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(_GH_STUB)
    (bin_dir / "gh").chmod(0o755)

    (tmp_path / "reviews.json").write_text(json.dumps(reviews or []))
    # REST `pulls/{n}`: the PR object the step reads the author from.
    (tmp_path / "pr.json").write_text(
        json.dumps(pr if pr is not None else {"number": 7, "user": {"login": AUTHOR}})
    )
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
        T_PR=str(tmp_path / "pr.json"),
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
    fields = _run_step(tmp_path, reviews=[_review(OLD)])
    assert fields["state"] == "pending"
    assert fields["description"] == f"Awaiting review of {HEAD[:7]}"


def test_a_formal_review_of_the_head_counts(tmp_path: Path):
    """The control. Without it, the test above passes for a gate that never goes green."""
    fields = _run_step(tmp_path, reviews=[_review(HEAD)])
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
    fields = _run_step(tmp_path, reviews=[_review(HEAD, "PENDING")])
    assert fields["state"] == "pending"


def test_a_stale_approval_does_not_green_a_new_head(tmp_path: Path):
    """reviewDecision stays APPROVED across pushes; the head check must still hold."""
    fields = _run_step(tmp_path, reviews=[_review(OLD, "APPROVED")], decision="APPROVED")
    assert fields["state"] == "pending"


def test_open_threads_still_fail_a_reviewed_head(tmp_path: Path):
    fields = _run_step(tmp_path, reviews=[_review(HEAD)], unresolved=2)
    assert fields["state"] == "failure"
    assert fields["description"] == "2 unresolved review comment(s)"


def test_the_head_check_needs_no_contents_scope(tmp_path: Path):
    """Formal reviews are read from REST, whose `commit_id` is a plain field.

    GraphQL's `reviews.nodes.commit` is a Commit object, which needs contents:read
    and killed this job on private repos once already. The permissions block
    must stay as narrow as it was — and the author lookup added for PI-1003 must
    stay inside it: `pulls/{n}` is listed under the same "Pull requests: read".
    """
    text = _workflow(tmp_path / "proj").read_text()
    assert 'gh api --paginate "repos/${REPO}/pulls/${PR_NUMBER}/reviews"' in text
    assert 'gh api "repos/${REPO}/pulls/${PR_NUMBER}"' in text
    permissions = text.split("\npermissions:\n", 1)[1].split("\n\n", 1)[0]
    assert "contents" not in permissions
    assert text.index("FORMAL_REVIEWS=$(") < text.index("REVIEW_DATA=$("), (
        "reviewThreads is sampled before the formal-review count — a review landing "
        "between the two would be counted while its threads were not"
    )


# ── PI-1003: the PR author's own review is not a review of the head ──


def test_the_authors_own_thread_reply_does_not_review_the_head(tmp_path: Path):
    """THE DEFECT: push, reply to a thread, resolve it, and the check went green.

    Measured on #1000: the reply posted 22s after the push became a formal
    COMMENTED review of the new head, two minutes before the reviewer reached it.
    """
    fields = _run_step(tmp_path, reviews=[_author_reply(HEAD)])
    assert fields["state"] == "pending"
    assert fields["description"] == f"Awaiting review of {HEAD[:7]}"


def test_a_reviewer_of_the_head_still_counts_beside_the_authors_reply(tmp_path: Path):
    """The control: only the AUTHOR's reviews are dropped, not the reviewer's.

    Without it the test above passes for a gate that counts nothing at all.
    """
    fields = _run_step(tmp_path, reviews=[_author_reply(HEAD), _review(HEAD)])
    assert fields["state"] == "success"
    assert fields["description"] == "Reviewed — no open comments"


def test_a_human_reviewer_who_is_not_the_author_counts(tmp_path: Path):
    """The filter is the author, not an allowlist of bots: a second human reviews."""
    fields = _run_step(tmp_path, reviews=[_review(HEAD, login="another-human")])
    assert fields["state"] == "success"


def test_an_unreadable_author_counts_no_formal_review(tmp_path: Path):
    """Fail closed: a filter that cannot name the author must not become a no-op.

    Dropping the `$author != ""` clause turns an author the API did not name into
    "every review counts", which is the defect back with no way to see it.
    """
    fields = _run_step(tmp_path, reviews=[_review(HEAD)], pr={"number": 7, "user": None})
    assert fields["state"] == "pending"
