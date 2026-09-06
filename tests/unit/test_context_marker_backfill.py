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

from project_init.scaffold import _RECORD_MARKER, _TEMPLATES_DIR
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


def test_backfilled_comment_states_the_same_scope_as_a_fresh_scaffold() -> None:
    """#968 — an UPGRADED repo must not describe an unscoped stand-down.

    #968 closed the gap between config.yaml and AGENTS.md for fresh scaffolds.
    This block is the third surface, on the path that issue did not touch, and
    it still said the ambient layer "stands down inside it" full stop. An
    upgraded repo would therefore contradict a freshly scaffolded one — the
    exact defect, reintroduced one path over.

    Caught by review on PR #971 rather than by a test, so this is the test.
    """
    spliced = _ensure_context_key(_PRE_901)
    lowered = spliced.lower()
    assert "scoped, not total" in lowered
    assert "silent" in lowered, "does not say what happens where AGENTS.md is silent"
    # The unscoped wording must be gone, not merely supplemented.
    assert "stands down inside it" not in lowered


def test_backfilled_scope_matches_the_template_wording() -> None:
    """The two producers must not drift — assert on both, not on one.

    Reading the template rather than restating its text: a copy of the wording
    in this test would pass while the template said something else, which is the
    whole failure mode here.
    """
    template = (_TEMPLATES_DIR / "base" / "dot_agents" / "config.yaml.tmpl").read_text(
        encoding="utf-8"
    )
    spliced = _ensure_context_key(_PRE_901)
    for phrase in ("scoped", "silent", "project matters"):
        assert phrase in template.lower(), f"template lost {phrase!r}"
        assert phrase in spliced.lower(), f"upgrade block lost {phrase!r}"
