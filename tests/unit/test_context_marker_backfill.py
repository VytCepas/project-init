"""The detect-and-defer marker reaches EXISTING scaffolds, not just fresh ones (PI-901).

`.agents/config.yaml` is never re-rendered wholesale on upgrade (it holds
hand-edited fields), so the template line alone would only ever mark *new*
projects. `upgrade` splices `context: repo` in — idempotently, and without ever
overwriting an owner who deliberately opted out with `context: ambient`.

harbor#4 H1 / harbor CONTRACTS/marker.md: the marker is what tells a root
orchestrator or a global agent environment to stand down inside a governed repo.
An unmarked repo is one the layer above keeps acting in.
"""

from __future__ import annotations

import pytest
import yaml

from project_init.scaffold import _RECORD_MARKER
from project_init.upgrade import _ensure_context_key

_PRE_901 = """\
# project-init: record of choices made at init time.

project:
  name: "app"

language: python

hooks:
  expected: [pre-commit, commit-msg, pre-push]
"""


def _with_record(body: str) -> str:
    return f"{body}\n{_RECORD_MARKER}\nvariables: {{}}\n"


def test_backfill_adds_the_marker_to_a_pre_901_config() -> None:
    assert "\ncontext: repo\n" in _ensure_context_key(_PRE_901)


def test_backfill_puts_context_above_project() -> None:
    # Template order: the marker is the first key a reader meets.
    out = _ensure_context_key(_PRE_901)
    assert out.index("\ncontext:") < out.index("\nproject:")


def test_backfill_is_idempotent() -> None:
    once = _ensure_context_key(_PRE_901)
    assert _ensure_context_key(once) == once


def test_backfill_never_revokes_a_deliberate_opt_out() -> None:
    # `ambient` is the owner saying "keep acting here". An upgrade that reset it
    # to `repo` would silently revoke that decision — and the failure is
    # invisible, because both values are valid.
    opted_out = _ensure_context_key(_PRE_901).replace("context: repo", "context: ambient")
    out = _ensure_context_key(opted_out)
    assert out.count("context:") == 1
    assert "context: ambient" in out


def test_backfill_leaves_the_scaffold_record_intact() -> None:
    out = _ensure_context_key(_with_record(_PRE_901))
    assert out.count(_RECORD_MARKER) == 1
    assert out.index("\ncontext:") < out.index(_RECORD_MARKER)


def test_a_commented_out_marker_does_not_count_as_present() -> None:
    # `# context: repo` in a comment is documentation, not a declaration. If the
    # presence check matched it the splice would no-op and the repo would stay
    # unmarked while looking marked to a human reading the file.
    commented = "# context: repo\n" + _PRE_901
    out = _ensure_context_key(commented)
    assert "\ncontext: repo\n" in out


@pytest.mark.parametrize(
    "line",
    [
        "context: ambient",
        "context : ambient",
        'context:  "ambient"',
        '"context": ambient',
        "'context': ambient",
    ],
)
def test_no_second_context_key_for_any_valid_yaml_spelling(line: str) -> None:
    # PR #902 review. A bare `^context:` check misses `context : ambient` and
    # `"context": ambient` — both valid YAML — and the splice then inserts a
    # SECOND logical `context` key. Duplicate-key-tolerant readers keep whichever
    # comes last (the inserted `repo`), silently revoking the opt-out; stricter
    # ones reject the descriptor outright. Either way the owner's decision is
    # gone and nothing says so.
    #
    # Asserted through a real YAML parser on the VALUE a reader would get, not
    # by re-running the production regex over the output — a test that counts
    # matches with the very pattern under test passes for every mutation of it.
    # (The first draft of this test did exactly that and survived reverting the
    # fix; caught by the mutation check CLAUDE.md asks for.)
    out = _ensure_context_key(f"{line}\n{_PRE_901}")
    assert yaml.safe_load(out.partition(_RECORD_MARKER)[0])["context"] == "ambient", out


def test_backfill_reaches_a_config_with_no_project_key() -> None:
    # The anchor must not be the single point of failure the `ci:` one was
    # (PI-880): with nothing to anchor on, prepend rather than silently drop.
    out = _ensure_context_key("language: python\n")
    assert out.startswith("# Detect-and-defer")
    assert "\ncontext: repo\n" in out
