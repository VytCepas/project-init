"""#356: cross-file contract — the vetted pin must not drift from what ships.

Lives under tests/contracts/ (auto-marked ``contract``) because it asserts a
template/manifest relationship, not pure logic (per docs/development/testing.md).
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    path = REPO_ROOT / "tools" / "check_third_party_updates.py"
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
        REPO_ROOT / "templates" / "multi_model" / "dot_agents" / "scripts" / "setup_models.sh"
    ).read_text(encoding="utf-8")
    assert f'CCR_VERSION="{pinned}"' in installer, (
        f"manifest pins ccr at {pinned} but setup_models.sh disagrees — run "
        "tools/check_third_party_updates.py apply ccr <version>"
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

    Scoped to tests/contracts/: `tests/unit/test_third_party_updates.py` uses the
    version as fixture data for the bumper itself, which is legitimate.
    """
    mod = _load_module()
    managed = {tool["pinned"] for tool in mod.load_manifest().values()}

    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "tests" / "contracts").glob("*.py")):
        if path.name == "test_third_party_pin_contract.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in managed:
                offenders.append(f"{path.name}:{node.lineno}: literal {node.value!r}")

    assert not offenders, (
        "a contract test restates a manifest-managed pin as a literal; read it from "
        "tools/pinned_third_party.toml instead:\n  " + "\n  ".join(offenders)
    )


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
        REPO_ROOT / "templates" / "multi_model" / "dot_agents" / "scripts" / "setup_models.sh"
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
            ), f"{tool_id}: {rel} does not carry {tool['version_var']}=\"{tool['pinned']}\""
