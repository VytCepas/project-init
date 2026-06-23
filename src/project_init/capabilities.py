"""Deterministic capabilities inventory (PI-374, ADR-017).

Generates ``.claude/CAPABILITIES.md`` — a surface-independent list of what the
scaffold gave the agent (skills, hooks, MCP servers) plus the exact options
chosen, derived from the canonical sources (the shared skill set, the scaffolded
``settings.json`` hooks, the MCP catalog) and the config record. No LLM
(ADR-001); regenerated on every scaffold/upgrade so it never drifts. Readable by
any surface — humans, Claude, Codex, Cursor, Antigravity — one source of truth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from project_init.mcps import servers_for_ids
from project_init.scaffold import _TEMPLATES_DIR

_NAME_RE = re.compile(r"^name:\s*(.+)$", re.MULTILINE)
_DESC_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)
_SCRIPT_RE = re.compile(r'([\w./$"{}-]+\.(?:sh|py))')

_OUTPUT_REL = Path(".claude/CAPABILITIES.md")


def _skill_meta(skill_md: Path) -> tuple[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    name = _NAME_RE.search(text)
    desc = _DESC_RE.search(text)
    return (
        name.group(1).strip() if name else skill_md.parent.name,
        desc.group(1).strip() if desc else "",
    )


def canonical_skills() -> list[tuple[str, str]]:
    """Return (name, description) for every skill the scaffold ships.

    Both the always-rendered base skills (e.g. ``plan``, as ``SKILL.md.tmpl``)
    and the shared fallback/plugin skill set — the canonical skill source.
    Deduped by name, sorted.
    """
    dirs = (
        _TEMPLATES_DIR / "base" / "dot_claude" / "skills",
        _TEMPLATES_DIR / "fallback" / "dot_claude" / "skills",
    )
    seen: dict[str, tuple[str, str]] = {}
    for skills_dir in dirs:
        # SKILL.md and SKILL.md.tmpl (base 'plan' is templated; frontmatter is
        # static so the name/description read fine).
        for p in sorted(skills_dir.glob("*/SKILL.md*")):
            name, desc = _skill_meta(p)
            seen.setdefault(name, (name, desc))
    return sorted(seen.values())


def _script_name(command: str) -> str:
    """Return the meaningful hook script in a settings.json command.

    Skips the _py.sh interpreter shim.
    """
    files = [m.split("/")[-1].strip('"') for m in _SCRIPT_RE.findall(command)]
    files = [f for f in files if f != "_py.sh"]
    return files[-1] if files else command.split()[0]


def canonical_hooks(variables: dict[str, str]) -> list[tuple[str, str]]:
    """(event, script) pairs for the always-on hooks.

    The same hook set fires whether the project is plugin- or no-plugin-mode
    (the plugin just wires what ``settings.json`` wires directly), but in plugin
    mode the wiring isn't in the target's ``settings.json`` and the plugin file
    isn't packaged. So derive from the packaged, mode-independent canonical
    source: render ``settings.json.tmpl`` in no-plugin form and read its hooks.
    """
    from project_init.scaffold import _render

    tmpl = _TEMPLATES_DIR / "base" / "dot_claude" / "settings.json.tmpl"
    rendered = _render(
        tmpl.read_text(encoding="utf-8"),
        {**variables, "no_plugin": "true", "plugin_mode": ""},
    )
    try:
        data = json.loads(rendered)
    except json.JSONDecodeError:
        return []
    out: list[tuple[str, str]] = []
    for event, entries in (data.get("hooks") or {}).items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                if cmd:
                    out.append((event, _script_name(cmd)))
    return out


def surface_hooks(variables: dict[str, str]) -> list[tuple[str, str]]:
    """(hook file, events) for the GUI surfaces selected via --agents (#366).

    Reflects the per-surface hook configs scaffold() emits for cursor/antigravity
    so the inventory shows them alongside the native Claude hooks.
    """
    from project_init import surfaces

    agents = [a.strip() for a in variables.get("agents", "").split(",") if a.strip()]
    rows: list[tuple[str, str]] = []
    for name in agents:
        spec = surfaces.SURFACES.get(name)
        if not spec or not spec.get("hooks_file"):
            continue
        config = json.loads(spec["hooks_render"]())
        events = list(config.get("hooks") or config.get("safety-gate") or {})
        label = spec["hooks_file"]
        if spec.get("experimental"):
            label += " (experimental)"
        rows.append((label, ", ".join(events)))
    return rows


def _mcp_ids(variables: dict[str, str]) -> list[str]:
    raw = variables.get("installed_mcps", "none")
    if raw in ("", "none"):
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _chosen_options(variables: dict[str, str]) -> list[tuple[str, str]]:
    # Pairs (label, value) read straight from the config record / variables.
    g = variables.get
    return [
        ("Agents/surfaces", g("agents", "claude") or "claude"),
        ("Profile", g("profile", "individual") or "individual"),
        ("Delivery", g("delivery", "prototype") or "prototype"),
        ("Deploy", g("deploy_target", "none") or "none"),
        ("IaC", g("iac", "none") or "none"),
        ("Multi-model (CCR)", "on" if g("multi_model") else "off"),
        ("AI governance", "on" if g("governance") else "off"),
        ("Observability", "on" if g("observability") else "off"),
        ("Distribution", "no-plugin" if g("no_plugin") else "plugin"),
        ("MCP servers", g("installed_mcps", "none") or "none"),
        ("Memory stack", g("memory_stack", "obsidian-only") or "obsidian-only"),
    ]


def _table(headers: tuple[str, str], rows: list[tuple[str, str]]) -> list[str]:
    out = [f"| {headers[0]} | {headers[1]} |", "|---|---|"]
    for a, b in rows:
        # Escape pipes so descriptions can't break the table.
        out.append(f"| {a} | {b.replace('|', chr(92) + '|')} |")
    return out


def render(variables: dict[str, str]) -> str:
    """The CAPABILITIES.md content for a scaffold described by *variables*."""
    skills = canonical_skills()
    hooks = canonical_hooks(variables)
    servers = servers_for_ids(_mcp_ids(variables))

    lines = [
        "# Capabilities",
        "",
        "<!-- Generated by project-init (PI-374) — do not edit by hand; it is",
        "regenerated on every scaffold/upgrade. -->",
        "",
        "Surface-independent inventory of what the scaffold gave this project's",
        "agent — readable on any surface (Claude, Codex, Cursor, Antigravity, …).",
        "",
        "## Chosen options",
        "",
        *_table(("Option", "Value"), _chosen_options(variables)),
        "",
        f"## Skills ({len(skills)})",
        "",
        *_table(("Skill", "Description"), skills),
        "",
        "## Hooks",
        "",
    ]
    if hooks:
        lines += _table(("Event", "Script"), hooks)
    else:
        lines.append("_No hooks wired._")
    gui_hooks = surface_hooks(variables)
    if gui_hooks:
        lines += [
            "",
            "### GUI surface hooks",
            "",
            *_table(("Config file", "Events"), gui_hooks),
        ]
    lines += ["", f"## MCP servers ({len(servers)})", ""]
    if servers:
        rows = [
            (name, " ".join([spec.get("command", "")] + spec.get("args", [])).strip())
            for name, spec in sorted(servers.items())
        ]
        lines += _table(("Server", "Invocation"), rows)
    else:
        lines.append("_None selected._")
    lines.append("")
    return "\n".join(lines)


def emit(target: Path, variables: dict[str, str]) -> list[Path]:
    """Write .claude/CAPABILITIES.md.

    Always (over)written — it is a generated inventory, not user-editable config.
    """
    dest = target / _OUTPUT_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(variables), encoding="utf-8", newline="\n")
    return [_OUTPUT_REL]
