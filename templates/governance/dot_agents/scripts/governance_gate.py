"""Governance gate (ADR-018, #412) — system-card validator that never passes on silence.

Governance being enabled means the repo must say something about AI. The gate
passes only when ONE of these holds, and exits non-zero otherwise:

1. every *real* ``SYSTEM_CARD.md`` under ``.agents/governance/`` validates (the
   shipped ``examples/`` are excluded); or
2. there is no card AND ``.agents/governance/NO_AI_SYSTEM.md`` is present with a
   ``reason`` and a ``declared_on`` date — an explicit, dated declaration that
   this repo ships no AI system.

A card AND a declaration together contradict each other and fail. No card and
no declaration fails too: "nothing to declare" and "forgot to declare" must not
look the same.

Deterministic, stdlib-only. Invoked via ``_py.sh`` by ``governance_gate.sh`` and
the CI ``governance`` job. Both manifests are flat ``key: value`` scalars only —
no PyYAML, no nesting.
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
# The declaration that this repo ships no AI system (the alternative to a card).
# Repo-level, so a single fixed path — unlike cards, it is not searched for.
DECLARATION_FILE = "NO_AI_SYSTEM.md"
DECLARATION_REQUIRED = ("reason", "declared_on")
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
    """Real system cards (named SYSTEM_CARD.md), excluding the shipped examples/.

    Only the top-level ``.agents/governance/examples/`` is excluded — a card
    stored under a deeper directory that happens to be named ``examples`` is
    still a real card.
    """
    return [
        p for p in gov_dir.rglob("SYSTEM_CARD.md") if p.relative_to(gov_dir).parts[0] != "examples"
    ]


def staleness_days(gov_dir: Path) -> int:
    """Hardcoded default, overridable only via a flat ``staleness_days`` in
    ``.agents/governance/config.json`` (the shipped config.example.json is ignored)."""
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
        return [f"models_declared must resolve under .agents/governance/: {value}"]
    if not resolved.is_file():
        return [f"models_declared points at a missing file: {value}"]
    if "PLACEHOLDER" in resolved.read_text(encoding="utf-8"):
        return [f"models_declared file is not filled in (still a placeholder): {value}"]
    return []


def _date_age(field: str, value: str) -> tuple[int | None, list[str]]:
    """Age in days of an ISO ``YYYY-MM-DD`` *value*, or the reasons it is unusable."""
    m = _DATE_RE.match(value)
    if not m:
        return None, [f"{field} must be an ISO date YYYY-MM-DD; got {value!r}"]
    try:
        parsed = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None, [f"{field} is not a valid date: {value!r}"]
    age = (date.today() - parsed).days
    if age < 0:
        return None, [f"{field} is in the future: {value!r}"]
    return age, []


def _check_staleness(value: str, max_age: int) -> list[str]:
    age, errs = _date_age("last_reviewed", value)
    if age is not None and age > max_age:
        return [f"last_reviewed is stale ({age} days old > {max_age}-day window); re-review"]
    return errs


def validate_card(card: Path, root: Path, gov_dir: Path, max_age: int) -> list[str]:
    fm = parse_frontmatter(card.read_text(encoding="utf-8"))
    errs = [f"missing/placeholder field: {k}" for k in REQUIRED if is_placeholder(fm.get(k, ""))]

    role = fm.get("role", "")
    if role and not is_placeholder(role) and role not in ROLES:
        errs.append(f"role must be one of {sorted(ROLES)}; got {role!r}")
    classification = fm.get("classification", "")
    if (
        classification
        and not is_placeholder(classification)
        and classification not in CLASSIFICATIONS
    ):
        errs.append(
            f"classification must be one of {sorted(CLASSIFICATIONS)}; got {classification!r}"
        )
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


def validate_declaration(declaration: Path) -> list[str]:
    """A ``NO_AI_SYSTEM.md`` must carry a real reason and a valid, non-future date."""
    fm = parse_frontmatter(declaration.read_text(encoding="utf-8"))
    errs = [
        f"missing/placeholder field: {k}"
        for k in DECLARATION_REQUIRED
        if is_placeholder(fm.get(k, ""))
    ]
    declared_on = fm.get("declared_on", "")
    if declared_on and not is_placeholder(declared_on):
        errs += _date_age("declared_on", declared_on)[1]
    return errs


def _silence_message() -> str:
    """Failure text for a repo that has declared nothing — names both ways out."""
    return (
        "governance gate failed: governance is enabled but this repo declares nothing — "
        "no real SYSTEM_CARD.md and no NO_AI_SYSTEM.md. Satisfy the gate one of two ways:\n"
        "  1. It ships an AI system: copy "
        ".agents/governance/examples/SYSTEM_CARD.template.md to "
        ".agents/governance/SYSTEM_CARD.md and fill it in.\n"
        f"  2. It ships no AI system: create .agents/governance/{DECLARATION_FILE} "
        "(template: .agents/governance/examples/NO_AI_SYSTEM.template.md) holding\n"
        "       ---\n"
        "       reason: <why this repo ships no AI system>\n"
        "       declared_on: <YYYY-MM-DD>\n"
        "       ---"
    )


def _report(rel: Path, errs: list[str]) -> bool:
    """Print one file's verdict; True when it failed."""
    if errs:
        print(f"FAIL {rel}:")
        for e in errs:
            print(f"  - {e}")
        return True
    print(f"OK   {rel}")
    return False


def _check_declaration(root: Path, declaration: Path) -> int:
    """The no-card path: pass only on a valid, dated declaration."""
    if _report(declaration.relative_to(root), validate_declaration(declaration)):
        print(f"\ngovernance gate failed — fix {DECLARATION_FILE} above.")
        return 1
    fm = parse_frontmatter(declaration.read_text(encoding="utf-8"))
    print(f"  declared no AI system on {fm['declared_on']}: {fm['reason']}")
    print("governance gate passed (declared: no AI system).")
    return 0


def _contradiction(root: Path, declaration: Path, cards: list[Path]) -> list[str]:
    names = ", ".join(str(c.relative_to(root)) for c in sorted(cards))
    return [
        f"contradiction: {declaration.name} declares this repo ships no AI system, but a real "
        f"SYSTEM_CARD.md exists ({names}). Remove {declaration.name} if the card is right, "
        "or the card(s) if the declaration is right."
    ]


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    gov_dir = root / ".agents" / "governance"
    # A missing governance dir is not an exemption: with no card and no
    # declaration nothing is declared, so it falls through to the failure below.
    cards = find_cards(gov_dir) if gov_dir.is_dir() else []
    declaration = gov_dir / DECLARATION_FILE
    declared = declaration.is_file()
    if not cards and not declared:
        print(_silence_message())
        return 1
    if not cards:
        return _check_declaration(root, declaration)
    failed = False
    if declared:
        failed = _report(declaration.relative_to(root), _contradiction(root, declaration, cards))
    max_age = staleness_days(gov_dir)
    for card in sorted(cards):
        failed |= _report(card.relative_to(root), validate_card(card, root, gov_dir, max_age))
    if failed:
        print("\ngovernance gate failed — fix the problems above.")
        return 1
    print("governance gate passed.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] in (["-h"], ["--help"]):  # --help does no work (#992)
        print((__doc__ or "").strip())
        sys.exit(0)
    sys.exit(main(sys.argv))
