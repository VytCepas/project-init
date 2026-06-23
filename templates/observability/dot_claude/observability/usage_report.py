"""Observability usage report (ADR-019, #405) — file-based, zero-egress analyzer.

Reads the always-present Claude Code transcript JSONL plus an optional guarded
hook self-log and emits a text summary (stdout) + a self-contained
``dashboard.html`` (inline CSS, no CDN, no JS). Deterministic, stdlib-only;
runs via ``_py.sh``.

**Aggregate-only by construction.** It extracts only names, counts, and numbers
— never prompt text, tool-input bodies, command strings, or file contents. The
one place it reads a tool-input body (Edit/Write) it derives a line *count* and
discards the text. **Zero-egress:** transcript + local ``git`` only; never
``gh`` or the network.

Scope is Claude Code only (the transcript format). Four buckets:
Adoption / Cost / Productivity / Reliability — see the bucket builders below.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from html import escape
from pathlib import Path

# --- Static price table (USD per 1M tokens) -------------------------------
# Approximate, embedded so the analyzer stays zero-egress. Prices drift — this
# is labelled "approximate" in the output and matched by model-id substring so
# new point releases inherit a sane default. Cache multipliers follow the
# documented economics: cache writes ~1.25x base input, reads ~0.1x base input.
_PRICES = (
    # (substring, input_per_mtok, output_per_mtok)
    ("opus", 5.0, 25.0),
    ("sonnet", 3.0, 15.0),
    ("haiku", 1.0, 5.0),
    ("fable", 10.0, 50.0),
    ("mythos", 10.0, 50.0),
)
_DEFAULT_PRICE = (5.0, 25.0)  # unknown model → assume Opus-tier (conservative)
_CACHE_WRITE_MULT = 1.25
_CACHE_READ_MULT = 0.10


def project_slug(project_dir: str) -> str:
    """Claude Code's transcript directory slug for an absolute project path.

    Claude replaces every character that is not alphanumeric or ``-`` with
    ``-`` (so ``/``, ``.``, and ``_`` all become ``-``), which for an absolute
    path yields a leading ``-``. Empirically verified against
    ``~/.claude/projects/`` (e.g. ``/home/u/projects/project_init`` →
    ``-home-u-projects-project-init``).
    """
    return "".join(c if (c.isalnum() or c == "-") else "-" for c in project_dir)


def _price_for(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    for sub, inp, out in _PRICES:
        if sub in m:
            return inp, out
    return _DEFAULT_PRICE


def _projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def discover_transcript(
    *, transcript: str | None, session_id: str | None, project_dir: Path
) -> Path:
    """Locate the transcript JSONL. Never silently empty — raise on miss.

    Order: explicit ``--transcript`` → ``--session-id`` under the derived slug
    → newest ``*.jsonl`` under the derived slug → newest ``*.jsonl`` anywhere
    under ``~/.claude/projects`` whose entries' ``cwd`` matches the project dir.
    """
    if transcript:
        p = Path(transcript).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"--transcript not found: {p}")
        return p

    slug = project_slug(str(project_dir))
    slug_dir = _projects_root() / slug

    if session_id:
        p = slug_dir / f"{session_id}.jsonl"
        if not p.is_file():
            raise FileNotFoundError(
                f"session {session_id} not found at {p} — pass --transcript explicitly"
            )
        return p

    if slug_dir.is_dir():
        jsonls = sorted(slug_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
        if jsonls:
            return jsonls[-1]

    # Fallback: scan all project dirs, keep transcripts whose cwd matches.
    target = str(project_dir)
    candidates: list[tuple[float, Path]] = []
    root = _projects_root()
    if root.is_dir():
        for f in root.glob("*/*.jsonl"):
            if _transcript_cwd(f) == target:
                candidates.append((f.stat().st_mtime, f))
    if candidates:
        return max(candidates)[1]

    raise FileNotFoundError(
        "no transcript found for "
        f"{project_dir} (looked under {slug_dir}/ and by cwd) — "
        "pass --transcript <path> explicitly"
    )


def _iter_entries(path: Path):
    """Yield parsed JSON objects from a JSONL file, skipping unparseable lines."""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            yield obj


def _transcript_cwd(path: Path) -> str | None:
    """First ``cwd`` field found in a transcript (used for the cwd fallback)."""
    for obj in _iter_entries(path):
        cwd = obj.get("cwd")
        if isinstance(cwd, str):
            return cwd
    return None


def _count_lines(text: object) -> int:
    """Line count of a string body — the only number derived from a tool input.

    The text itself is never stored or emitted (aggregate-only)."""
    if not isinstance(text, str) or not text:
        return 0
    return text.count("\n") + 1


def parse_transcript(path: Path) -> dict:
    """Single pass over the transcript → raw aggregates (names/counts/numbers).

    Returns plain dicts/ints only; no prompt, command, or file content is kept.
    """
    skills: dict[str, int] = {}
    subagents: dict[str, int] = {}
    tools: dict[str, int] = {}
    mcp_tools: dict[str, int] = {}
    models: dict[str, dict[str, int]] = {}
    tool_use_names: dict[str, str] = {}  # tool_use_id -> tool name (for reliability)
    tool_errors: dict[str, int] = {}
    tool_calls = 0
    tool_results = 0
    loc_added = 0
    edits = 0
    writes = 0

    for obj in _iter_entries(path):
        etype = obj.get("type")
        if etype == "assistant":
            msg = obj.get("message") or {}
            model = msg.get("model")
            usage = msg.get("usage") or {}
            if model and isinstance(usage, dict):
                acc = models.setdefault(
                    model,
                    {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0, "messages": 0},
                )
                acc["input"] += int(usage.get("input_tokens") or 0)
                acc["output"] += int(usage.get("output_tokens") or 0)
                acc["cache_creation"] += int(usage.get("cache_creation_input_tokens") or 0)
                acc["cache_read"] += int(usage.get("cache_read_input_tokens") or 0)
                acc["messages"] += 1
            for block in msg.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name") or "?"
                inp = block.get("input") or {}
                tool_calls += 1
                tid = block.get("id")
                if isinstance(tid, str):
                    tool_use_names[tid] = name
                if name == "Skill":
                    skills[inp.get("skill") or "?"] = skills.get(inp.get("skill") or "?", 0) + 1
                elif name in ("Task", "Agent"):
                    key = inp.get("subagent_type") or inp.get("description") or "?"
                    subagents[key] = subagents.get(key, 0) + 1
                elif name.startswith("mcp__"):
                    mcp_tools[name] = mcp_tools.get(name, 0) + 1
                else:
                    tools[name] = tools.get(name, 0) + 1
                # LoC heuristic: count lines in the *new* body, discard the text.
                if name == "Write":
                    writes += 1
                    loc_added += _count_lines(inp.get("content"))
                elif name == "Edit":
                    edits += 1
                    loc_added += _count_lines(inp.get("new_string"))
        elif etype == "user":
            msg = obj.get("message") or {}
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results += 1
                        if block.get("is_error"):
                            tid = block.get("tool_use_id")
                            name = tool_use_names.get(tid, "?") if isinstance(tid, str) else "?"
                            tool_errors[name] = tool_errors.get(name, 0) + 1

    return {
        "skills": skills,
        "subagents": subagents,
        "tools": tools,
        "mcp_tools": mcp_tools,
        "models": models,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "tool_errors": tool_errors,
        "loc_added": loc_added,
        "edits": edits,
        "writes": writes,
    }


def load_usage_log(obs_dir: Path) -> dict[str, int]:
    """Hook counts from the guarded self-log (``usage.jsonl``), if present.

    Each line is ``{"hook": "<name>", ...}`` (the exact schema is finalised by
    the sibling self-log issue). Absent or unreadable ⇒ empty (the report still
    renders three buckets from the transcript)."""
    hooks: dict[str, int] = {}
    log = obs_dir / "usage.jsonl"
    if not log.is_file():
        return hooks
    for obj in _iter_entries(log):
        name = obj.get("hook") or obj.get("hook_event_name")
        if isinstance(name, str):
            hooks[name] = hooks.get(name, 0) + 1
    return hooks


def _git_counts(project_dir: Path) -> dict[str, int | None]:
    """Local-git-only productivity signals — no ``gh``, no network."""

    def _run(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", "-C", str(project_dir), *args],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    commits = _run("rev-list", "--count", "HEAD")
    merges = _run("rev-list", "--count", "--merges", "HEAD")
    return {
        "commits": int(commits) if commits and commits.isdigit() else None,
        "merge_commits": int(merges) if merges and merges.isdigit() else None,
    }


def _model_cost(acc: dict[str, int], price: tuple[float, float]) -> float:
    inp, out = price
    return (
        acc["input"] / 1_000_000 * inp
        + acc["output"] / 1_000_000 * out
        + acc["cache_creation"] / 1_000_000 * inp * _CACHE_WRITE_MULT
        + acc["cache_read"] / 1_000_000 * inp * _CACHE_READ_MULT
    )


def analyze(raw: dict, hooks: dict[str, int], git: dict) -> dict:
    """Fold raw aggregates into the four reporting buckets (numbers only)."""
    # Cost per model + totals.
    cost_rows = []
    total_cost = 0.0
    total_tokens = 0
    total_cache_read = 0
    total_cache_in = 0
    for model, acc in sorted(raw["models"].items()):
        cost = _model_cost(acc, _price_for(model))
        total_cost += cost
        tokens = acc["input"] + acc["output"] + acc["cache_creation"] + acc["cache_read"]
        total_tokens += tokens
        total_cache_read += acc["cache_read"]
        total_cache_in += acc["input"] + acc["cache_creation"] + acc["cache_read"]
        cost_rows.append(
            {
                "model": model,
                "messages": acc["messages"],
                "input": acc["input"],
                "output": acc["output"],
                "cache_creation": acc["cache_creation"],
                "cache_read": acc["cache_read"],
                "cost_usd": round(cost, 4),
            }
        )
    cache_ratio = (total_cache_read / total_cache_in) if total_cache_in else 0.0

    errors = sum(raw["tool_errors"].values())
    calls = raw["tool_calls"]
    error_rate = (errors / calls) if calls else 0.0

    return {
        "adoption": {
            "skills": raw["skills"],
            "subagents": raw["subagents"],
            "tools": raw["tools"],
            "mcp_tools": raw["mcp_tools"],
            "hooks": hooks,
        },
        "cost": {
            "models": cost_rows,
            "total_cost_usd": round(total_cost, 4),
            "total_tokens": total_tokens,
            "cache_read_ratio": round(cache_ratio, 4),
            "approximate": True,
        },
        "productivity": {
            "loc_added_approx": raw["loc_added"],
            "edits": raw["edits"],
            "writes": raw["writes"],
            "commits": git["commits"],
            "merge_commits": git["merge_commits"],
        },
        "reliability": {
            "tool_calls": calls,
            "tool_results": raw["tool_results"],
            "errors": errors,
            "error_rate": round(error_rate, 4),
            "errors_by_tool": raw["tool_errors"],
            "accept_reject": "not available (OTEL-only)",
            "active_time": "not available (OTEL-only)",
        },
    }


# --- Rendering ------------------------------------------------------------


def _fmt_counts(d: dict[str, int]) -> str:
    if not d:
        return "    (none)"
    return "\n".join(f"    {k}: {v}" for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0])))


def render_text(report: dict, transcript: Path) -> str:
    a, c, p, r = (report[k] for k in ("adoption", "cost", "productivity", "reliability"))
    lines = [
        "Claude Code usage report (aggregate-only, zero-egress)",
        f"transcript: {transcript}",
        "",
        "== Adoption ==",
        "  Skills:",
        _fmt_counts(a["skills"]),
        "  Sub-agents:",
        _fmt_counts(a["subagents"]),
        "  Tools:",
        _fmt_counts(a["tools"]),
        "  MCP tools:",
        _fmt_counts(a["mcp_tools"]),
        "  Hooks (self-log):",
        _fmt_counts(a["hooks"]),
        "",
        "== Cost (approximate, static price table) ==",
        f"  Total: ${c['total_cost_usd']:.4f} over {c['total_tokens']:,} tokens",
        f"  Cache-read ratio: {c['cache_read_ratio']:.1%}",
    ]
    for row in c["models"]:
        lines.append(
            f"    {row['model']}: ${row['cost_usd']:.4f} "
            f"(in {row['input']:,} / out {row['output']:,} / "
            f"cache {row['cache_read']:,}r {row['cache_creation']:,}w)"
        )
    lines += [
        "",
        "== Productivity ==",
        f"  LoC added (approx): {p['loc_added_approx']:,} "
        f"(edits {p['edits']}, writes {p['writes']})",
        f"  Commits (local git): {p['commits'] if p['commits'] is not None else 'n/a'}",
        f"  Merge commits (local heuristic): "
        f"{p['merge_commits'] if p['merge_commits'] is not None else 'n/a'}",
        "",
        "== Reliability ==",
        f"  Tool calls: {r['tool_calls']} | results: {r['tool_results']} | "
        f"errors: {r['errors']} ({r['error_rate']:.1%})",
        "  Errors by tool:",
        _fmt_counts(r["errors_by_tool"]),
        f"  Accept/reject: {r['accept_reject']}",
        f"  Active time: {r['active_time']}",
        "",
    ]
    return "\n".join(lines)


def _bars(d: dict[str, int]) -> str:
    if not d:
        return '<p class="muted">(none)</p>'
    items = sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))
    top = items[0][1] or 1
    rows = []
    for name, count in items:
        pct = int(count / top * 100)
        rows.append(
            f'<div class="bar"><span class="lbl">{escape(name)}</span>'
            f'<span class="track"><span class="fill" style="width:{pct}%"></span></span>'
            f'<span class="num">{count}</span></div>'
        )
    return "\n".join(rows)


def render_html(report: dict, transcript: Path) -> str:
    a, c, p, r = (report[k] for k in ("adoption", "cost", "productivity", "reliability"))
    rows = "".join(
        f"<tr><td>{escape(row['model'])}</td><td>{row['messages']}</td>"
        f"<td>{row['input']:,}</td><td>{row['output']:,}</td>"
        f"<td>{row['cache_read']:,}</td><td>${row['cost_usd']:.4f}</td></tr>"
        for row in c["models"]
    )
    css = (
        "body{font:14px/1.5 system-ui,sans-serif;margin:0;background:#0f1115;color:#e6e6e6;"
        "padding:2rem}h1{font-size:1.4rem}h2{font-size:1.05rem;margin-top:1.8rem;"
        "border-bottom:1px solid #2a2e37;padding-bottom:.3rem}.muted{color:#8a8f98}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1.2rem}"
        ".card{background:#161a22;border:1px solid #2a2e37;border-radius:8px;padding:1rem}"
        ".bar{display:flex;align-items:center;gap:.5rem;margin:.25rem 0}"
        ".lbl{flex:0 0 38%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
        ".track{flex:1;background:#222732;border-radius:4px;height:.7rem;overflow:hidden}"
        ".fill{display:block;height:100%;background:#5b8def}.num{flex:0 0 3rem;text-align:right}"
        "table{border-collapse:collapse;width:100%}td,th{padding:.35rem .6rem;"
        "border-bottom:1px solid #2a2e37;text-align:right}td:first-child,th:first-child{text-align:left}"
        ".kpi{font-size:1.6rem;font-weight:600}"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude Code usage report</title><style>{css}</style></head><body>
<h1>Claude Code usage report</h1>
<p class="muted">Aggregate-only, zero-egress. Transcript: {escape(str(transcript))}</p>
<div class="grid">
<div class="card"><h2>Cost (approx)</h2>
<p class="kpi">${c['total_cost_usd']:.2f}</p>
<p class="muted">{c['total_tokens']:,} tokens · {c['cache_read_ratio']:.0%} cache-read</p></div>
<div class="card"><h2>Productivity</h2>
<p class="kpi">{p['loc_added_approx']:,} LoC</p>
<p class="muted">{p['edits']} edits · {p['writes']} writes · """
    f"""{p['commits'] if p['commits'] is not None else 'n/a'} commits</p></div>
<div class="card"><h2>Reliability</h2>
<p class="kpi">{r['error_rate']:.0%} errors</p>
<p class="muted">{r['tool_calls']} calls · {r['errors']} errors</p></div>
</div>
<h2>Adoption — Skills</h2>{_bars(a['skills'])}
<h2>Adoption — Sub-agents</h2>{_bars(a['subagents'])}
<h2>Adoption — Tools</h2>{_bars(a['tools'])}
<h2>Adoption — MCP tools</h2>{_bars(a['mcp_tools'])}
<h2>Adoption — Hooks (self-log)</h2>{_bars(a['hooks'])}
<h2>Cost by model</h2>
<table><tr><th>Model</th><th>Msgs</th><th>Input</th><th>Output</th><th>Cache read</th><th>Cost</th></tr>
{rows}</table>
<h2>Reliability — errors by tool</h2>{_bars(r['errors_by_tool'])}
<p class="muted">Accept/reject and exact active-time are OTEL-only and not captured here.</p>
</body></html>
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="usage_report.py",
        description="File-based, zero-egress Claude Code usage report (aggregate-only).",
    )
    parser.add_argument("--transcript", help="Path to a transcript JSONL (overrides discovery)")
    parser.add_argument("--session-id", help="Session id to resolve under the project slug")
    parser.add_argument(
        "--project-dir",
        default=str(Path.cwd()),
        help="Project directory (default: cwd) — drives slug + git signals",
    )
    parser.add_argument(
        "--html",
        default=".claude/observability/dashboard.html",
        help="Where to write the self-contained HTML report",
    )
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve()
    try:
        transcript = discover_transcript(
            transcript=args.transcript,
            session_id=args.session_id,
            project_dir=project_dir,
        )
    except FileNotFoundError as e:
        sys.stderr.write(f"usage_report: {e}\n")
        return 1

    raw = parse_transcript(transcript)
    hooks = load_usage_log(project_dir / ".claude" / "observability")
    git = _git_counts(project_dir)
    report = analyze(raw, hooks, git)

    sys.stdout.write(render_text(report, transcript))

    html_path = Path(args.html)
    if not html_path.is_absolute():
        html_path = project_dir / html_path
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html(report, transcript), encoding="utf-8", newline="\n")
    sys.stdout.write(f"\nHTML report written to {html_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
