"""The `ci:` descriptor block reaches EXISTING scaffolds, not just fresh ones (PI-828).

`.agents/config.yaml` is excluded from drift comparison (it holds hand-edited
fields), so a template addition alone would never appear in an already-scaffolded
project. `upgrade` splices the block in — idempotently, and without ever
rewriting an endpoint the owner set by hand.
"""

from __future__ import annotations

from project_init.scaffold import _RECORD_MARKER
from project_init.upgrade import _ensure_ci_block

_PRE_828 = """\
project:
  name: "app"

tooling:
  lint_command: "just lint"

hooks:
  expected: [pre-commit, commit-msg, pre-push]
"""


def _with_record(body: str) -> str:
    return f"{body}\n{_RECORD_MARKER}\nvariables: {{}}\n"


def test_backfill_adds_the_ci_block_to_a_pre_828_config() -> None:
    assert "status_url:" in _ensure_ci_block(_PRE_828)


def test_backfill_puts_ci_above_hooks() -> None:
    out = _ensure_ci_block(_PRE_828)
    assert out.index("\nci:") < out.index("\nhooks:")


def test_backfill_is_idempotent() -> None:
    once = _ensure_ci_block(_PRE_828)
    assert _ensure_ci_block(once) == once


def test_backfill_never_clobbers_a_hand_set_status_url() -> None:
    # The whole point of the field is that a human sets it. A second upgrade
    # must not reset it to "".
    configured = _ensure_ci_block(_PRE_828).replace(
        'status_url: ""', 'status_url: "https://jenkins.example.com/job/app/lastBuild/api/json"'
    )
    out = _ensure_ci_block(configured)
    # Not just "the URL survives" — a second, empty `ci:` block spliced in above
    # it would leave the URL in the text but hand the reader the empty one.
    assert out.count("status_url:") == 1
    assert "jenkins.example.com" in out


def test_backfill_leaves_the_scaffold_record_intact() -> None:
    out = _ensure_ci_block(_with_record(_PRE_828))
    assert out.count(_RECORD_MARKER) == 1
    assert out.index("\nci:") < out.index(_RECORD_MARKER)


def test_backfill_reaches_a_config_without_a_hooks_key() -> None:
    # PI-880: a config old enough to lack `ci:` also predates `hooks:`, so the
    # splice must not depend on `hooks:` being there. With no `hooks:`/`updates:`
    # anchor it appends the block rather than silently dropping it.
    out = _ensure_ci_block("project:\n  name: app\n")
    assert "status_url:" in out


def test_backfill_anchors_above_updates_when_hooks_is_absent() -> None:
    # The realistic pre-`hooks:` shape (PI-880): the field pass guarantees an
    # `updates:` key, so `ci:` lands just above it — template order preserved.
    pre = 'project:\n  name: "app"\n\ntooling:\n  lint_command: "x"\n\nupdates:\n  declined_additions: {}\n'
    out = _ensure_ci_block(pre)
    assert out.index("\nci:") < out.index("\nupdates:")
