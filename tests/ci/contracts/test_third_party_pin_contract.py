"""#356: cross-file contract — the vetted pin must not drift from what ships.

Lives under a tests/<family>/contracts/ directory (auto-marked ``contract``) because it asserts a
template/manifest relationship, not pure logic (per docs/development/testing.md).
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module():
    path = REPO_ROOT / "tools" / "check-third-party-updates.py"
    spec = importlib.util.spec_from_file_location("check_third_party_updates", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_manifest_pin_matches_installer_version():
    """The manifest pin and CCR_VERSION in the scaffolded installer must stay in
    lockstep — the whole point of `apply`. Guards silent drift (#356)."""
    mod = _load_module()
    pinned = mod.load_manifest()["ccr"]["pinned"]
    installer = (
        REPO_ROOT / "templates" / "multi-model" / "dot_agents" / "scripts" / "setup_models.sh"
    ).read_text(encoding="utf-8")
    assert f'CCR_VERSION="{pinned}"' in installer, (
        f"manifest pins ccr at {pinned} but setup_models.sh disagrees — run "
        "tools/check-third-party-updates.py apply ccr <version>"
    )


def test_no_contract_test_restates_a_managed_pin():
    """`apply` bumps the manifest and every `used_in` file. A version literal in a
    test is invisible to it, so a routine bump leaves the test asserting a version
    the scaffold no longer ships (#689).

    Contract tests must read the pin from the manifest, as
    `test_multi_model_overlay._pinned_ccr_version()` does.

    An AST walk, not a text grep: matching `ast.Constant` values exactly means a
    docstring that *mentions* `"2.0.0"` is not an offender (its constant is the
    whole docstring), while `X = "2.0.0"` is. A line-based filter here was
    vacuous — `PINNED_CCR_VERSION` contains the substring "pinned".

    Scoped to the contracts tier: `tests/ci/unit/test_third_party_updates.py` uses the
    version as fixture data for the bumper itself, which is legitimate.
    """
    mod = _load_module()
    managed = {tool["pinned"] for tool in mod.load_manifest().values()}

    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "tests").glob("*/contracts/*.py")):
        if path.name == "test_third_party_pin_contract.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in managed:
                offenders.append(f"{path.name}:{node.lineno}: literal {node.value!r}")

    assert not offenders, (
        "a contract test restates a manifest-managed pin as a literal; read it from "
        "tools/pinned-third-party.toml instead:\n  " + "\n  ".join(offenders)
    )


def test_router_hold_and_installer_refusal_name_the_same_boundary():
    """#1005: two defences against a router that rewrites the user's Claude Code
    settings — the manifest hold (no bump is ever proposed or applied) and the
    installer's own refusal (a hand-edited pin is refused before installing).
    They must agree on where 3.x starts, and the pin must sit below it."""
    mod = _load_module()
    ccr = mod.load_manifest()["ccr"]
    assert ccr.get("hold_at"), "the ccr pin lost its hold; see #1005 before lifting it"
    assert mod.held(ccr["pinned"], ccr) is None, "the pin itself is inside the held range"

    installer = (
        REPO_ROOT / "templates" / "multi-model" / "dot_agents" / "scripts" / "setup_models.sh"
    ).read_text(encoding="utf-8")
    major = ccr["hold_at"].split(".")[0]
    assert f"CCR_FIRST_UNSUPPORTED_MAJOR={major}\n" in installer
    assert "\nrequire_supported_ccr\n" in installer, "the refusal is defined but never called"


def test_claude_code_is_installed_unpinned_by_design():
    """#689: not an oversight — the operator's own CLI, off the request path.

    Pinning it would hold every scaffolded project behind a bump PR on a
    fast-moving tool. The installer must say so, and the manifest must not claim
    ownership of a version it never bumps.
    """
    mod = _load_module()
    # Exact package match: CCR's own name (@musistudio/claude-code-router)
    # contains the substring "claude-code".
    packages = {tool["package"] for tool in mod.load_manifest().values()}
    assert "@anthropic-ai/claude-code" not in packages, (
        "claude-code is in the manifest but nothing pins or bumps it"
    )

    installer = (
        REPO_ROOT / "templates" / "multi-model" / "dot_agents" / "scripts" / "setup_models.sh"
    ).read_text(encoding="utf-8")
    assert 'CLAUDE_PKG="@anthropic-ai/claude-code"' in installer
    assert "CLAUDE_VERSION" not in installer, "a version pin appeared without a manifest entry"
    assert "deliberately NOT pinned" in installer, "the decision must stay recorded at the pin site"


def test_every_manifest_tool_declares_where_its_pin_lives():
    """`apply` rewrites `used_in`; an entry with none silently bumps nothing."""
    mod = _load_module()
    for tool_id, tool in mod.load_manifest().items():
        assert tool.get("used_in"), f"{tool_id}: no `used_in` — `apply` would rewrite nothing"
        assert tool.get("version_var"), f"{tool_id}: no `version_var` — `apply` cannot substitute"
        for rel in tool["used_in"]:
            path = REPO_ROOT / rel
            assert path.is_file(), f"{tool_id}: used_in path does not exist: {rel}"
            assert f'{tool["version_var"]}="{tool["pinned"]}"' in path.read_text(
                encoding="utf-8"
            ), f'{tool_id}: {rel} does not carry {tool["version_var"]}="{tool["pinned"]}"'


# ── tools/pinned-third-party.toml is a view of the box versions register ──────────────
# The register (the standard's standards/naming/versions.tsv, vendored with the naming package) holds the
# vetted pin and hold_at for every tool; this file keeps what only yard knows (the package, the
# version variable, used_in). The two must agree, or the bot proposes bumps the register refuses.
_REGISTER = REPO_ROOT / "templates" / "base" / "vendor" / "naming" / "registry" / "versions.tsv"


def _register_rows(text: str) -> dict[str, dict[str, str]]:
    """The register's rows by id (comments and the header skipped)."""
    rows: dict[str, dict[str, str]] = {}
    header: list[str] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        cells = line.split("\t")
        if not header:
            header = cells
            continue
        rows[cells[0]] = dict(zip(header, cells, strict=False))
    return rows


def _view_drift(manifest: dict, register: dict[str, dict[str, str]]) -> list[str]:
    """Every way a manifest tool disagrees with its register row (pure)."""
    problems: list[str] = []
    for tool_id, entry in manifest.items():
        row = register.get(f"tool.{tool_id}")
        if row is None:
            problems.append(f"{tool_id}: no row tool.{tool_id} in the register")
            continue
        if entry["pinned"] != row["value"]:
            problems.append(f"{tool_id}: pinned {entry['pinned']}, register {row['value']}")
        if entry.get("hold_at", "-") != row["hold_at"]:
            problems.append(
                f"{tool_id}: hold_at {entry.get('hold_at', '-')}, register {row['hold_at']}"
            )
    return problems


_ROW = "id\taxis\tname\tvalue\tsha\thold_at\thold_reason\tupgrade\tnote\n"


def test_a_manifest_that_disagrees_with_the_register_is_reported():
    """The check can fail: a changed pin, a changed hold and a missing row are each named."""
    register = _register_rows(_ROW + "tool.ccr\ttool\tx\t2.0.0\t-\t3.0.0\tr\tpr\tn\n")
    ok = {"ccr": {"pinned": "2.0.0", "hold_at": "3.0.0"}}
    assert _view_drift(ok, register) == []
    assert _view_drift({"ccr": {"pinned": "2.1.0", "hold_at": "3.0.0"}}, register) == [
        "ccr: pinned 2.1.0, register 2.0.0"
    ]
    assert _view_drift({"ccr": {"pinned": "2.0.0", "hold_at": "4.0.0"}}, register) == [
        "ccr: hold_at 4.0.0, register 3.0.0"
    ]
    assert _view_drift({"other": {"pinned": "1"}}, register) == [
        "other: no row tool.other in the register"
    ]


def test_the_manifest_is_a_view_of_the_vendored_register():
    """Once the naming package ships versions.tsv, the manifest must agree with it. Until then the
    vendored copy has no register, which is said, not passed over."""
    import pytest

    if not _REGISTER.is_file():
        pytest.skip("the vendored naming package predates no versions.tsv to compare yet")
    mod = _load_module()
    assert _view_drift(mod.load_manifest(), _register_rows(_REGISTER.read_text("utf-8"))) == []
