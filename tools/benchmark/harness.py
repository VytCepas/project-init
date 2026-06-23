"""Benchmark collection harness (#271) — the runner every dimension feeds.

Two cleanly separable halves:

- **Orchestration** (``setup_*_target`` / ``run_task`` / the ``run`` CLI) drives
  ``claude -p`` against bare and scaffolded temp targets. It needs the Claude
  CLI + an API key + network, so it is **run manually**, never in CI and never
  from the scaffold runtime (CLAUDE.md / ADR-001).
- **Parsing → normalized record** (``build_record`` + ``tools.benchmark.transcript``)
  is pure and fully testable against fixture transcripts. This is the stable
  contract #272/#273/#275 consume.

Run: ``uv run python -m tools.benchmark.harness run --task all --preset obsidian-only``
or, to normalize a transcript you already have:
``uv run python -m tools.benchmark.harness record-from --task feat --target bare --transcript <path>``
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from tools.benchmark.prices import apply_cost, load_prices
from tools.benchmark.record import RunRecord, write_records
from tools.benchmark.scoring import Score, rework_cycles
from tools.benchmark.scoring import score as score_run
from tools.benchmark.transcript import parse as parse_transcript

_HERE = Path(__file__).resolve().parent
_TASKS_DIR = _HERE / "tasks"
_RESULTS_DIR = _HERE / "results"
_DEFAULT_MODEL = "claude-opus-4-8"
_TASK_IDS = ("feat", "fix", "qa", "noop")


# --- task specs -----------------------------------------------------------


def load_task(task_id: str) -> dict:
    """Load and minimally validate a task spec from tasks/<id>.toml."""
    path = _TASKS_DIR / f"{task_id}.toml"
    if not path.is_file():
        raise FileNotFoundError(f"unknown task {task_id!r} (no {path})")
    spec = tomllib.loads(path.read_text(encoding="utf-8"))
    if not spec.get("prompt"):
        raise ValueError(f"task {task_id!r} has no prompt")
    spec.setdefault("id", task_id)
    return spec


def load_all_tasks() -> dict[str, dict]:
    """Load every task spec in the methodology's set (feat/fix/qa/noop)."""
    return {tid: load_task(tid) for tid in _TASK_IDS}


# --- transcript discovery (mirrors Claude Code's slug rule) ---------------


def project_slug(project_dir: str) -> str:
    """Claude Code transcript-dir slug: non-alphanumeric/non-dash → ``-``."""
    return "".join(c if (c.isalnum() or c == "-") else "-" for c in project_dir)


def transcript_path_for(config_dir: Path, target_dir: Path, session_id: str) -> Path:
    """Where Claude Code writes the transcript under an isolated CLAUDE_CONFIG_DIR."""
    slug = project_slug(str(target_dir.resolve()))
    return config_dir / "projects" / slug / f"{session_id}.jsonl"


# --- target setup (testable — no agent) -----------------------------------


def _git_init(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(target), "init", "-q"], check=False, timeout=30)


# pytest is the deterministic check runner (#273) and must be available in BOTH
# arms so the comparison isolates what the scaffold actually adds (conventions,
# skills, CLAUDE.md) — not whether the test runner happens to be installed. uv
# includes the `dev` dependency-group by default, so `uv run pytest` resolves.
_MINIMAL_PYPROJECT = """\
[project]
name = "benchmark-target"
version = "0.0.0"
requires-python = ">=3.11"

[dependency-groups]
dev = ["pytest"]
"""


def setup_bare_target(target: Path) -> Path:
    """Create the baseline target — a temp project with NO ``.claude/``.

    Carries a minimal pyproject (with pytest in its dev group) + git so the
    deterministic checks run on the bare arm too, isolating the scaffold's real
    contribution rather than test-runner availability.
    """
    _git_init(target)
    (target / "pyproject.toml").write_text(_MINIMAL_PYPROJECT, encoding="utf-8")
    return target


def seed_task(target: Path, task: dict) -> None:
    """Materialize a task's ``[[seed_files]]`` into the target before the run.

    Some tasks (e.g. ``fix``) need a pre-existing fixture — a failing + passing
    test to repair — rather than starting from an empty project. Tasks without
    seed files are a no-op.
    """
    for spec in task.get("seed_files", []):
        dest = target / spec["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Strip the leading newline the TOML triple-quote literal carries.
        dest.write_text(spec["content"].lstrip("\n"), encoding="utf-8")


def prepare_target(target_dir: Path, target: str, task: dict, *, model: str) -> Path:
    """Create a FRESH target for one run and seed the task fixture.

    Recreated per ``(task, run_index)`` so each run measures an identical clean
    baseline — a prior task's writes (or an earlier repeat) never leak in.
    """
    if target == "bare":
        setup_bare_target(target_dir)
    else:
        setup_scaffolded_target(target_dir, target, model=model)
    seed_task(target_dir, task)
    return target_dir


def setup_scaffolded_target(target: Path, preset: str, *, model: str = _DEFAULT_MODEL) -> Path:
    """The same temp project + project-init output for one preset."""
    from project_init.__main__ import main as project_init_main

    _git_init(target)
    (target / "pyproject.toml").write_text(_MINIMAL_PYPROJECT, encoding="utf-8")
    rc = project_init_main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            preset,
            "--name",
            "benchmark-target",
            "--description",
            "benchmark scaffolded target",
            "--language",
            "python",
        ]
    )
    if rc != 0:
        raise RuntimeError(f"project-init failed (rc={rc}) for preset {preset!r}")
    return target


# --- agent run (manual only — needs claude + API key + network) -----------


def run_task(
    target_dir: Path,
    task: dict,
    *,
    model: str,
    config_dir: Path,
) -> dict:
    """Drive ``claude -p`` on one task; return {session_id, wall_clock_s, cost_estimate}.

    Requires the Claude CLI. Wraps the subprocess for the authoritative
    wall-clock (methodology). The throwaway ``config_dir`` isolates the run from
    the user's history and keeps fixed-overhead clean.
    """
    if shutil.which("claude") is None:
        raise RuntimeError("the `claude` CLI is not installed — run_task is manual-only")
    cmd = [
        "claude",
        "-p",
        task["prompt"],
        "--output-format",
        "json",
        "--model",
        model,
        # Throwaway dir → safe to skip interactive permission prompts headlessly.
        "--permission-mode",
        "bypassPermissions",
    ]
    # Inherit the caller's env (ANTHROPIC_API_KEY, proxy vars, …) and only
    # override CLAUDE_CONFIG_DIR so the run is isolated from the user's history.
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config_dir)}
    start = time.monotonic()
    proc = subprocess.run(
        cmd, cwd=str(target_dir), capture_output=True, text=True, env=env, timeout=1800
    )
    wall_clock_s = time.monotonic() - start
    session_id, cost, result_text = "", None, ""
    try:
        out = json.loads(proc.stdout)
        if isinstance(out, dict):
            session_id = out.get("session_id") or ""
            cost = out.get("total_cost_usd")
            result_text = out.get("result") or ""  # final agent text (for the regex check)
    except (ValueError, TypeError):
        pass
    return {
        "session_id": session_id,
        "wall_clock_s": wall_clock_s,
        "cost_estimate": cost,
        "result": result_text,
    }


# --- normalized record (pure — testable) ----------------------------------


@dataclass(frozen=True)
class RunContext:
    """Identity + harness-measured metadata for one run (the ``(task,target,run)`` key)."""

    task: str
    target: str  # "bare" or a preset name
    run_index: int
    model: str
    session_id: str = ""
    wall_clock_s: float | None = None


def build_record(ctx: RunContext, transcript_path: Path) -> RunRecord:
    """Assemble a :class:`RunRecord` from a transcript. Pure: parse + pack."""
    agg = parse_transcript(transcript_path)
    return RunRecord(
        task=ctx.task,
        target=ctx.target,
        run_index=ctx.run_index,
        model=ctx.model or (agg.models[0] if agg.models else ""),
        claude_version=agg.claude_version,
        session_id=ctx.session_id,
        transcript_path=str(transcript_path),
        input_tokens=agg.input_tokens,
        output_tokens=agg.output_tokens,
        cache_read_tokens=agg.cache_read_tokens,
        cache_creation_tokens=agg.cache_creation_tokens,
        total_tokens=agg.total_tokens,
        tool_calls=agg.tool_calls,
        turns=agg.turns,
        wall_clock_s=ctx.wall_clock_s,
        first_ts=agg.first_ts,
        last_ts=agg.last_ts,
    )


# --- CLI ------------------------------------------------------------------


def _apply_score(record: RunRecord, result: Score) -> None:
    """Copy a :class:`Score` onto the record's accuracy fields (#273)."""
    record.success = result.success
    record.first_try = result.first_try
    record.rework_cycles = result.rework_cycles


def _warn_if_unpriced(record: RunRecord) -> None:
    """Emit the documented warning when a record's model has no price row."""
    if record.cost_usd is None:
        sys.stderr.write(
            f"benchmark: no price row for model {record.model!r} — cost_usd left null\n"
        )


def _cmd_record_from(args: argparse.Namespace) -> int:
    """Normalize an existing transcript into a record (no agent needed)."""
    transcript = Path(args.transcript).expanduser()
    if not transcript.is_file():
        sys.stderr.write(f"benchmark: transcript not found: {transcript}\n")
        return 1
    record = build_record(
        RunContext(
            task=args.task,
            target=args.target,
            run_index=args.run_index,
            model=args.model,
        ),
        transcript,
    )
    apply_cost(record, load_prices(Path(args.prices) if args.prices else None))
    _warn_if_unpriced(record)
    # No target dir to check against here — record the rework proxy from the
    # transcript; success/first_try stay null (use `run` for the full check).
    record.rework_cycles = rework_cycles(transcript)
    out = Path(args.out) if args.out else _RESULTS_DIR / "records.jsonl"
    write_records([record], out)
    sys.stdout.write(json.dumps(record.to_dict(), indent=2) + "\n")
    sys.stdout.write(f"\nappended to {out}\n")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Orchestrate bare + scaffolded runs (manual; needs the claude CLI)."""
    if shutil.which("claude") is None:
        sys.stderr.write("benchmark: the `claude` CLI is not installed — `run` is manual-only.\n")
        return 1
    tasks = load_all_tasks() if args.task == "all" else {args.task: load_task(args.task)}
    targets = ["bare", *args.preset]
    out = Path(args.out) if args.out else _RESULTS_DIR / "records.jsonl"
    prices = load_prices(Path(args.prices) if args.prices else None)
    records: list[RunRecord] = []
    with tempfile.TemporaryDirectory(prefix="pi-benchmark-") as tmp:
        tmp_root = Path(tmp)
        config_dir = tmp_root / "claude-config"
        for target in targets:
            for task_id, task in tasks.items():
                for run_index in range(args.repeats):
                    # Fresh target per run — clean baseline, no cross-run leakage.
                    tdir = tmp_root / f"target-{target}-{task_id}-{run_index}"
                    prepare_target(tdir, target, task, model=args.model)
                    result = run_task(tdir, task, model=args.model, config_dir=config_dir)
                    transcript = transcript_path_for(config_dir, tdir, result["session_id"])
                    if not transcript.is_file():
                        sys.stderr.write(
                            f"benchmark: no transcript for {target}/{task_id} run {run_index} "
                            f"(session {result['session_id']!r}) — skipping\n"
                        )
                        continue
                    record = build_record(
                        RunContext(
                            task=task_id,
                            target=target,
                            run_index=run_index,
                            model=args.model,
                            session_id=result["session_id"],
                            wall_clock_s=result["wall_clock_s"],
                        ),
                        transcript,
                    )
                    apply_cost(record, prices)
                    _warn_if_unpriced(record)
                    _apply_score(
                        record,
                        score_run(
                            task,
                            target_dir=tdir,
                            transcript_path=transcript,
                            agent_output=result.get("result", ""),
                        ),
                    )
                    records.append(record)
                    cost = f"${record.cost_usd:.4f}" if record.cost_usd is not None else "$?"
                    ok = {True: "ok", False: "FAIL", None: "n/a"}[record.success]
                    sys.stdout.write(
                        f"{target}/{task_id} run {run_index}: {ok}, "
                        f"{record.total_tokens} tok, {cost}, {record.tool_calls} tool calls, "
                        f"{record.wall_clock_s:.1f}s\n"
                    )
    if records:
        write_records(records, out)
        sys.stdout.write(f"\nwrote {len(records)} record(s) to {out}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse args and dispatch the ``run`` / ``record-from`` subcommands."""
    parser = argparse.ArgumentParser(
        prog="benchmark",
        description="Collection harness: run tasks in bare vs scaffolded targets (#271).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="orchestrate agent runs (manual; needs the claude CLI)")
    run.add_argument("--task", default="all", help="task id or 'all' (default)")
    run.add_argument(
        "--preset",
        action="append",
        default=[],
        help="scaffolded preset to compare against bare (repeatable)",
    )
    run.add_argument("--model", default=_DEFAULT_MODEL)
    run.add_argument("--repeats", type=int, default=5, help="repeats per (task,target) for variance")
    run.add_argument("--out", help="output JSONL (default: tools/benchmark/results/records.jsonl)")
    run.add_argument("--prices", help="price table JSON (default: tools/benchmark/model_prices.json)")
    run.set_defaults(func=_cmd_run)

    rec = sub.add_parser("record-from", help="normalize an existing transcript (no agent)")
    rec.add_argument("--task", required=True)
    rec.add_argument("--target", required=True, help="'bare' or a preset name")
    rec.add_argument("--transcript", required=True)
    # Default empty so the transcript's own model wins (build_record falls back
    # to it); pass --model only to override. The `run` subcommand pins the model.
    rec.add_argument("--model", default="", help="override; default = transcript's model")
    rec.add_argument("--run-index", type=int, default=0, dest="run_index")
    rec.add_argument("--out", help="output JSONL (default: tools/benchmark/results/records.jsonl)")
    rec.add_argument("--prices", help="price table JSON (default: tools/benchmark/model_prices.json)")
    rec.set_defaults(func=_cmd_record_from)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
