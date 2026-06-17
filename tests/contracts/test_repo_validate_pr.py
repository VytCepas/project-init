"""PI-200: the root validate-pr workflow must verify the PR title's scope key
number is among the Closes numbers — a `type(PI-N): ...` PR must `Closes #N`
(PI-N maps to issue #N), so it can't auto-close an unrelated issue.

The workflow's added check is mirrored here so its bash logic can be exercised
directly with sample inputs; a content test guards that the workflow keeps it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Mirror of the check in .github/workflows/validate-pr.yml (closes-keyword job).
_CHECK = r"""
set -eo pipefail
TITLE_KEY_NUM=$(echo "$PR_TITLE" | sed -nE 's/.*\([A-Z][A-Z0-9]*-([0-9]+)\).*/\1/p')
if [ -n "$TITLE_KEY_NUM" ]; then
  CLOSES_NUMS=$(echo "$PR_BODY" | grep -oiE 'closes\s+#[0-9]+' | grep -oE '[0-9]+' || true)
  if echo "$CLOSES_NUMS" | grep -qx "$TITLE_KEY_NUM"; then
    echo "MATCH"
  else
    echo "MISMATCH"; exit 1
  fi
fi
"""


def _run(title: str, body: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PR_TITLE": title, "PR_BODY": body}
    return subprocess.run(
        ["bash", "-c", _CHECK], env=env, capture_output=True, text=True
    )


def test_workflow_keeps_the_key_match_check():
    wf = (_REPO_ROOT / ".github" / "workflows" / "validate-pr.yml").read_text()
    assert "TITLE_KEY_NUM" in wf
    assert "is not among the Closes numbers" in wf


def test_matching_key_and_closes_passes():
    r = _run("fix(PI-99): bug", "Closes #99")
    assert r.returncode == 0 and "MATCH" in r.stdout


def test_mismatched_key_and_closes_fails():
    r = _run("fix(PI-99): bug", "Closes #1")
    assert r.returncode == 1 and "MISMATCH" in r.stdout


def test_scopeless_title_is_not_checked():
    r = _run("fix: typo", "")
    assert r.returncode == 0


def test_multiple_closes_with_key_among_them_passes():
    r = _run("fix(PI-99): bug", "Closes #1\nCloses #99")
    assert r.returncode == 0 and "MATCH" in r.stdout
