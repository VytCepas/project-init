"""GitHub Actions workflow files must actually load.

PI-719: `review-status.yml` named `pull_request_review_thread` as a trigger. That
is a webhook event, not an Actions trigger, so GitHub rejected the whole file at
load time — every run became a startup failure with no jobs, posting no
`review/decision` status. It went unnoticed for a day because nothing yet
depended on that status.

Nothing in the suite ran a workflow linter, so no test could have caught it: YAML
parsed fine, and the contract tests only asserted on the file's *text*. This gate
runs `actionlint` over both the repo's own workflows and the ones a scaffold
emits — the rendered output, not the templates, so `{{...}}` gating bugs surface
too.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables

_ROOT = Path(__file__).resolve().parents[2]
_ACTIONLINT = shutil.which("actionlint")

# actionlint-py is a declared dev dependency, so `uv run pytest` always has the
# binary and this gate never silently skips — in CI or locally. The guard only
# fires for someone running pytest outside the project environment (PR #720
# review: the previous message claimed CI installed it, and CI did not).
pytestmark = pytest.mark.skipif(
    _ACTIONLINT is None,
    reason="actionlint not on PATH — run under `uv run` so the dev group is active",
)


def _lint(paths: list[Path]) -> subprocess.CompletedProcess:
    """Schema validity only — triggers, expressions, contexts.

    `-shellcheck=` / `-pyflakes=` disable actionlint's embedded linters, which
    fire only when those tools happen to be on PATH. CI runners preinstall
    shellcheck and developer machines usually don't, so leaving them enabled
    makes this gate pass locally and fail in CI on `run:` style findings
    (SC2016/SC2086 "info") unrelated to whether the workflow loads. The
    scaffolded shell scripts get a real shellcheck run in `test_shell_lint_gate`.
    """
    assert paths, "no workflow files found — the glob is wrong, not the repo"
    return subprocess.run(
        [_ACTIONLINT, "-shellcheck=", "-pyflakes=", *[str(p) for p in paths]],
        capture_output=True,
        text=True,
        check=False,
    )


def test_this_repos_workflows_load():
    result = _lint(sorted((_ROOT / ".github" / "workflows").glob("*.yml")))
    assert result.returncode == 0, result.stdout + result.stderr


def test_scaffolded_workflows_load(tmp_path: Path):
    """Renders the templates, so an invalid trigger cannot ship to a new project."""
    preset = load_preset("obsidian-only")
    extra = overlay_layers([], no_plugin=True, memory_stack="obsidian-only", lifecycle=True)
    preset = {**preset, "layers": [*preset["layers"], *extra]}
    target = tmp_path / "proj"
    scaffold(target, preset, make_variables(no_plugin="true", plugin_mode=""))

    workflows = sorted((target / ".github" / "workflows").glob("*.yml"))
    result = _lint(workflows)
    assert result.returncode == 0, result.stdout + result.stderr
