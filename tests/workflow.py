"""Structural access to a rendered GitHub Actions workflow (#739).

The workflow contract tests used to slice `ci.yml` as text and substring-match.
That is the "assert the prose, not the behaviour" trap this repo keeps hitting:
`assert "just fuzz" in ci` passed while the `run:` step was deleted (matched a
comment); a `needs:` read as one line missed a multiline `- fuzz`; asserting a
command's *absence* false-positived on a comment quoting it. Three of PR #736's
review findings and one in #741 trace to string-slicing.

Parse the YAML instead. Comments vanish at parse time, `needs` is a list whatever
its source formatting, a missing job raises rather than passing quietly.

`pyyaml` is already a dev dependency (added for #719's workflow-schema gate). The
"don't reach for pyyaml" rule in CLAUDE.md is about the *scaffolder's runtime* —
it must stay small — not its test suite; `actionlint-py` and `shellcheck-py` are
already dev-only test tools.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def load_workflow(target: Path, name: str = "ci.yml") -> dict:
    """Parse a scaffolded workflow file into a mapping.

    Asserts the top level is a mapping: an empty or malformed file parses to
    None/str, and every downstream helper would then raise an opaque
    AttributeError instead of a clear failure (PR #742 review).
    """
    text = (target / ".github" / "workflows" / name).read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict), f"{name} did not parse to a mapping: {type(parsed).__name__}"
    return parsed


def on_triggers(workflow: dict) -> dict:
    """Return the `on:` block.

    YAML 1.1 (pyyaml) parses the bareword `on` as the boolean `True`, so the
    trigger block lives under the key `True`, not `"on"`. Every caller would trip
    on this; centralise it here.
    """
    return workflow.get(True) or workflow.get("on") or {}


def schedule_crons(workflow: dict) -> list[str]:
    """Every cron expression in the `on.schedule` block."""
    schedule = on_triggers(workflow).get("schedule") or []
    assert isinstance(schedule, list), f"`on.schedule` is not a list: {type(schedule).__name__}"
    return [entry["cron"] for entry in schedule if isinstance(entry, dict) and "cron" in entry]


def _jobs(workflow: dict) -> dict:
    jobs = workflow.get("jobs") or {}
    assert isinstance(jobs, dict), f"`jobs:` is not a mapping: {type(jobs).__name__}"
    return jobs


def job(workflow: dict, name: str) -> dict:
    """Return job `name`, asserting it exists (a clear message, not a KeyError)."""
    jobs = _jobs(workflow)
    assert name in jobs, f"no `{name}` job in the workflow (jobs: {sorted(jobs)})"
    return jobs[name]


def job_names(workflow: dict) -> list[str]:
    return list(_jobs(workflow).keys())


def needs(workflow: dict, name: str) -> list[str]:
    """Job `name`'s `needs` as a list — `needs:` may be a string or a list.

    Asserts the shape: a bare `list(raw)` on a mapping would silently return its
    keys, so a structurally wrong `needs:` could pass a contract test (PR #742
    review).
    """
    raw = job(workflow, name).get("needs") or []
    assert isinstance(raw, (str, list)), f"`needs:` on `{name}` is neither str nor list: {type(raw).__name__}"
    return [raw] if isinstance(raw, str) else list(raw)


def steps(job_dict: dict) -> list[dict]:
    raw = job_dict.get("steps") or []
    assert isinstance(raw, list) and all(isinstance(s, dict) for s in raw), (
        f"`steps:` is not a list of mappings: {type(raw).__name__}"
    )
    return raw


def run_commands(job_dict: dict) -> list[str]:
    """The `run:` script of every step in a job (skips `uses:` steps)."""
    return [step["run"] for step in steps(job_dict) if "run" in step]


def uses(job_dict: dict) -> list[str]:
    """The `uses:` reference of every action step in a job."""
    return [step["uses"] for step in steps(job_dict) if "uses" in step]


def _strip_shell_comments(script: str) -> str:
    """Drop shell comments from a `run:` script before matching against it.

    Parsing `run:` from YAML removes the *workflow* comments, but the value is a
    shell script that can carry its OWN `#` comments — so `job_runs_command`
    would match a command kept only as a comment (`echo x  # just fuzz`),
    reintroducing the exact defect #739 fixes inside the helper that fixes it
    (PR #742 review, Codex).

    A naive line-based heuristic, NOT a shell parser: drop full-line comments,
    and truncate each line at the first whitespace-then-`#`. That deliberately
    over-strips — a `#` after whitespace INSIDE a quoted string (`echo "a # b"`)
    is also cut (PR #742 review). The error direction is safe: over-stripping can
    only DROP text, so a real command that followed such a `#` goes unmatched and
    the test fails loudly — never a silent false positive. The callers match
    tool invocations (`just fuzz`, `bun install …`) that do not appear as quoted
    `#`-bearing data in these workflows, so the imprecision does not bite.
    """
    out = []
    for line in script.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        marker = re.search(r"\s#", line)
        out.append(line[: marker.start()] if marker else line)
    return "\n".join(out)


def job_runs_command(job_dict: dict, needle: str) -> bool:
    """True if `needle` appears in any step's `run:` script, comments removed.

    A substring match on the comment-stripped script, NOT a parse of the command
    line — `echo "just fuzz"` (the needle as data) would still match (PR #742
    review). It exists to reject the common failure it was built for: a needle
    kept only as a comment. Pass a distinctive needle (a recipe/binary name) so
    the data-vs-invocation gap stays theoretical.
    """
    return any(needle in _strip_shell_comments(cmd) for cmd in run_commands(job_dict))
