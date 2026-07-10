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
    return [entry["cron"] for entry in schedule if "cron" in entry]


def job(workflow: dict, name: str) -> dict:
    """Return job `name`, asserting it exists (a clear message, not a KeyError)."""
    jobs = workflow.get("jobs") or {}
    assert name in jobs, f"no `{name}` job in the workflow (jobs: {sorted(jobs)})"
    return jobs[name]


def job_names(workflow: dict) -> list[str]:
    return list((workflow.get("jobs") or {}).keys())


def needs(workflow: dict, name: str) -> list[str]:
    """Job `name`'s `needs` as a list — `needs:` may be a string or a list."""
    raw = job(workflow, name).get("needs") or []
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
    (PR #742 review, Codex). Conservative and line-based: drop full-line comments
    and inline comments introduced by whitespace-then-`#`. A `#` inside a quoted
    string or `${#var}` is not stripped, so a needle hiding there could still
    match — but that errs toward a false NEGATIVE (a real command not found ->
    the test fails loudly), never a silent false positive.
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
    """True if any step's `run:` script actually INVOKES `needle`.

    Shell comments are stripped first, so a command preserved only as a comment
    does not count (PR #742 review).
    """
    return any(needle in _strip_shell_comments(cmd) for cmd in run_commands(job_dict))
