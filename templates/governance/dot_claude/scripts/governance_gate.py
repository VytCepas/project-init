"""Governance gate (ADR-018, #412) — presence-triggered system-card validator.

Validates every *real* ``SYSTEM_CARD.md`` under ``.claude/governance/`` (the
shipped ``examples/`` are excluded) and exits non-zero on any violation. A
project with no real card passes — the gate is genuinely opt-in: it fires only
when a team deliberately writes a card.

Deterministic, stdlib-only. Invoked via ``_py.sh`` by ``governance_gate.sh`` and
the CI ``governance`` job. The manifest is flat ``key: value`` scalars only — no
PyYAML, no nesting.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

DEFAULT_STALENESS_DAYS = 180

REQUIRED = (
    "system_name",
    "owner",
    "role",
    "use_case",
    "affected_users",
    "data_classes",
    "models_declared",
    "human_oversight",
    "logging",
    "classification",
    "allowed",
    "last_reviewed",
)
ROLES = {"provider", "deployer"}
CLASSIFICATIONS = {"prohibited", "high", "limited", "minimal"}
ALLOWED_VALUES = {"true", "false"}
YES_NO_NA = {"yes", "no", "n-a"}
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Flat ``key: value`` scalars between the first two ``---`` fences."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def is_placeholder(value: str) -> bool:
    v = (value or "").strip()
    return not v or v.startswith("<") or "REPLACE" in v or v.upper() == "PLACEHOLDER"


def find_cards(gov_dir: Path) -> list[Path]:
    """Real system cards (named SYSTEM_CARD.md), excluding the shipped examples/."""
    return [
        p
        for p in gov_dir.rglob("SYSTEM_CARD.md")
        if "examples" not in p.relative_to(gov_dir).parts
    ]


def staleness_days(gov_dir: Path) -> int:
    """Hardcoded default, overridable only via a flat ``staleness_days`` in
    ``.claude/governance/config.json`` (the shipped config.example.json is ignored)."""
    try:
        data = json.loads((gov_dir / "config.json").read_text(encoding="utf-8"))
        value = data.get("staleness_days")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return DEFAULT_STALENESS_DAYS


def _check_models_declared(value: str, root: Path, gov_dir: Path) -> list[str]:
    """Path containment + non-placeholder check for the declarations reference."""
    if Path(value).is_absolute():
        return [f"models_declared must be repo-root-relative, not absolute: {value}"]
    if ".." in Path(value).parts:
        return [f"models_declared must not contain '..' (path traversal): {value}"]
    resolved = (root / value).resolve()
    gov_resolved = gov_dir.resolve()
    if resolved != gov_resolved and gov_resolved not in resolved.parents:
        return [f"models_declared must resolve under .claude/governance/: {value}"]
    if not resolved.is_file():
        return [f"models_declared points at a missing file: {value}"]
    if "PLACEHOLDER" in resolved.read_text(encoding="utf-8"):
        return [f"models_declared file is not filled in (still a placeholder): {value}"]
    return []


def _check_staleness(value: str, max_age: int) -> list[str]:
    m = _DATE_RE.match(value)
    if not m:
        return [f"last_reviewed must be an ISO date YYYY-MM-DD; got {value!r}"]
    try:
        reviewed = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return [f"last_reviewed is not a valid date: {value!r}"]
    age = (date.today() - reviewed).days
    if age > max_age:
        return [f"last_reviewed is stale ({age} days old > {max_age}-day window); re-review"]
    return []


def validate_card(card: Path, root: Path, gov_dir: Path, max_age: int) -> list[str]:
    fm = parse_frontmatter(card.read_text(encoding="utf-8"))
    errs = [f"missing/placeholder field: {k}" for k in REQUIRED if is_placeholder(fm.get(k, ""))]

    role = fm.get("role", "")
    if role and not is_placeholder(role) and role not in ROLES:
        errs.append(f"role must be one of {sorted(ROLES)}; got {role!r}")
    classification = fm.get("classification", "")
    if classification and not is_placeholder(classification) and classification not in CLASSIFICATIONS:
        errs.append(f"classification must be one of {sorted(CLASSIFICATIONS)}; got {classification!r}")
    allowed = fm.get("allowed", "").lower()
    if allowed and not is_placeholder(allowed) and allowed not in ALLOWED_VALUES:
        errs.append(f"allowed must be true|false; got {fm.get('allowed')!r}")
    for field in ("human_oversight", "logging"):
        val = fm.get(field, "")
        if val and not is_placeholder(val) and val not in YES_NO_NA:
            errs.append(f"{field} must be one of {sorted(YES_NO_NA)}; got {val!r}")

    # `prohibited` is always a hard fail when allowed:true — `exception` only
    # records why the card is kept, it never permits running (Codex r2 #4).
    if classification == "prohibited" and allowed == "true":
        errs.append(
            "classification 'prohibited' requires allowed:false — a prohibited system "
            "must not run; the 'exception' field documents why the card is retained, "
            "it is never permission to run"
        )

    models_declared = fm.get("models_declared", "")
    if models_declared and not is_placeholder(models_declared):
        errs += _check_models_declared(models_declared, root, gov_dir)
    last_reviewed = fm.get("last_reviewed", "")
    if last_reviewed and not is_placeholder(last_reviewed):
        errs += _check_staleness(last_reviewed, max_age)
    return errs


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    gov_dir = root / ".claude" / "governance"
    if not gov_dir.is_dir():
        return 0
    cards = find_cards(gov_dir)
    if not cards:
        print("governance gate: no SYSTEM_CARD.md found — nothing to check (pass).")
        return 0
    max_age = staleness_days(gov_dir)
    failed = False
    for card in sorted(cards):
        rel = card.relative_to(root)
        errs = validate_card(card, root, gov_dir, max_age)
        if errs:
            failed = True
            print(f"FAIL {rel}:")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"OK   {rel}")
    if failed:
        print("\ngovernance gate failed — fix the system card(s) above.")
        return 1
    print("governance gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
