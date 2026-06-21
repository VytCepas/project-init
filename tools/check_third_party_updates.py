#!/usr/bin/env python3
"""Check pinned third-party tools for newer releases and bump them in lockstep.

project-init owns a *vetted* pinned version of each external tool that sits on a
scaffolded project's request path (CCR first; ADR-016 §5, #356). This script is
the deterministic, no-LLM core of the scheduled "third-party-updates" workflow:

  check               report which pinned tools have a newer upstream release
  apply <tool> <ver>  bump the manifest pin + the version string in every file
                      that carries it (kept in lockstep), so a proposed update is
                      a single reviewable diff

The workflow runs `check --json`, security-scans each candidate (npm audit), then
`apply`s and opens a PR — never auto-merged. Stdlib only (tomllib + urllib); no
new dependencies, no LLM (CLAUDE.md / ADR-001).
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "tools" / "pinned_third_party.toml"
_NPM_ACCEPT = "application/vnd.npm.install-v1+json"  # abbreviated metadata


def load_manifest(path: Path = MANIFEST) -> dict:
    """Parse the pinned-tools manifest into ``{tool_id: {...}}``."""
    with path.open("rb") as fh:
        return tomllib.load(fh).get("tools", {})


def _version_key(version: str) -> tuple[int, ...]:
    """Comparable key for a dotted version; pre-release suffix is dropped.

    "2.0.10" > "2.0.9"; "2.1.0" > "2.0.99"; a "-beta" tail is ignored for ordering
    (we only ever bump to stable dist-tag 'latest', so this is sufficient here).
    """
    core = re.split(r"[-+]", version.strip(), maxsplit=1)[0]
    parts = []
    for piece in core.split("."):
        digits = re.sub(r"\D", "", piece)
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(candidate: str, pinned: str) -> bool:
    """True when ``candidate`` is a strictly newer version than ``pinned``."""
    return _version_key(candidate) > _version_key(pinned)


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": _NPM_ACCEPT})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (https registry)
        return json.load(resp)


def fetch_latest(tool: dict, *, get_json=_http_get_json) -> str:
    """Return the upstream 'latest' version for a manifest tool entry."""
    ecosystem = tool.get("ecosystem", "npm")
    if ecosystem != "npm":
        raise ValueError(f"unsupported ecosystem: {ecosystem!r} (only npm so far)")
    data = get_json(f"https://registry.npmjs.org/{tool['package']}")
    return data["dist-tags"]["latest"]


def check(manifest: dict, *, get_json=_http_get_json) -> list[dict]:
    """Report pinned-vs-latest for each tool. Network errors → error field set."""
    rows = []
    for tool_id, tool in manifest.items():
        row = {"tool": tool_id, "package": tool["package"], "pinned": tool["pinned"]}
        try:
            latest = fetch_latest(tool, get_json=get_json)
            row["latest"] = latest
            row["update_available"] = is_newer(latest, tool["pinned"])
        except Exception as exc:  # noqa: BLE001 — report, don't crash the sweep
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["update_available"] = False
        rows.append(row)
    return rows


def _replace_in_toml(text: str, tool_id: str, version: str) -> str:
    """Set ``pinned = "<version>"`` inside the ``[tools.<tool_id>]`` table only."""
    pattern = re.compile(
        r"(\[tools\." + re.escape(tool_id) + r"\][^\[]*?\bpinned\s*=\s*\")[^\"]*(\")",
        re.DOTALL,
    )
    new_text, n = pattern.subn(rf"\g<1>{version}\g<2>", text, count=1)
    if n != 1:
        raise ValueError(f"could not find pinned for [tools.{tool_id}] in the manifest")
    return new_text


def _replace_version_var(text: str, var: str, version: str) -> tuple[str, int]:
    """Set ``VAR="<version>"`` (shell assignment) wherever it appears."""
    pattern = re.compile(r"(^\s*" + re.escape(var) + r'\s*=\s*")[^"]*(")', re.MULTILINE)
    return pattern.subn(rf"\g<1>{version}\g<2>", text)


def apply(tool_id: str, version: str, *, manifest_path: Path = MANIFEST) -> list[Path]:
    """Bump the manifest pin and the version string in every used_in file.

    Returns the list of files changed. Pure file ops — no network, no LLM.
    """
    manifest = load_manifest(manifest_path)
    if tool_id not in manifest:
        raise KeyError(f"unknown tool: {tool_id!r}")
    tool = manifest[tool_id]
    changed: list[Path] = []

    manifest_path.write_text(
        _replace_in_toml(manifest_path.read_text(encoding="utf-8"), tool_id, version),
        encoding="utf-8",
    )
    changed.append(manifest_path)

    var = tool.get("version_var")
    for rel in tool.get("used_in", []):
        if not var:
            break
        path = REPO_ROOT / rel
        new_text, n = _replace_version_var(path.read_text(encoding="utf-8"), var, version)
        if n == 0:
            raise ValueError(f"{var} not found in {rel} — cannot bump in lockstep")
        path.write_text(new_text, encoding="utf-8")
        changed.append(path)
    return changed


def main(argv: list[str] | None = None) -> int:
    """CLI: ``check [--json]`` to report updates, ``apply <tool> <version>`` to bump."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="report tools with a newer upstream release")
    c.add_argument("--json", action="store_true", help="emit JSON (for the workflow)")
    a = sub.add_parser("apply", help="bump a tool's pin + its version string in lockstep")
    a.add_argument("tool")
    a.add_argument("version")
    args = parser.parse_args(argv)

    if args.cmd == "check":
        rows = check(load_manifest())
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for r in rows:
                if r.get("error"):
                    print(f"  {r['tool']}: ERROR {r['error']}")
                elif r["update_available"]:
                    print(f"  {r['tool']}: {r['pinned']} → {r['latest']}  UPDATE AVAILABLE")
                else:
                    print(f"  {r['tool']}: {r['pinned']} (up to date)")
        return 0

    changed = apply(args.tool, args.version)
    for p in changed:
        print(f"bumped {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
