"""#579: dependency license compliance scanning.

A non-blocking license-scan CI job flags copyleft (GPL/AGPL) dependencies, with
a per-language tool and a tunable deny-list, plus a `just license` recipe. Rust
uses cargo-deny driven by a scaffolded deny.toml (allow-list model). Introduced
non-blocking (not in ci-gate's needs), the same rollout semgrep/scorecard used.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _job_code(ci: str, job: str) -> str:
    """`job`'s block with comment lines removed.

    Asserting the ABSENCE of a command over the raw block is a trap: this job's
    own comment quotes the very command it must not run
    (`--frozen-lockfile 2>/dev/null || bun install`, #738), so a naive
    `not in job` check fails on the prose. Strip comments and assert over code.
    """
    match = re.search(rf"^  {re.escape(job)}:$", ci, flags=re.MULTILINE)
    assert match is not None, f"no `{job}:` job in the rendered workflow"
    rest = ci[match.start() :]
    nxt = re.search(r"^  [a-z][a-z0-9-]*:$", rest[len(f"  {job}:") :], flags=re.MULTILINE)
    block = rest if nxt is None else rest[: len(f"  {job}:") + nxt.start()]
    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("#"))


def _scaffold(target: Path, language: str = "python", **overrides: str) -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    scaffold(
        target, load_preset("obsidian-only"), make_variables(language=language, **flags, **overrides), strict=True
    )
    return target


def _ci(target: Path) -> str:
    return (target / ".github" / "workflows" / "ci.yml").read_text()


def _justfile(target: Path) -> str:
    return (target / "justfile").read_text()


class TestLicenseScanJob:
    @pytest.mark.parametrize("language", ["python", "node", "go", "rust"])
    def test_job_present(self, tmp_path: Path, language: str):
        ci = _ci(_scaffold(tmp_path / language, language))
        assert "license-scan:" in ci

    def test_non_blocking_not_in_ci_gate_needs(self, tmp_path: Path):
        ci = _ci(_scaffold(tmp_path / "p", "python"))
        gate_start = ci.index("ci-gate:")
        needs_line = next(
            line for line in ci[gate_start:].splitlines() if line.lstrip().startswith("needs:")
        )
        assert "license-scan" not in needs_line, "license-scan must stay non-blocking initially"

    @pytest.mark.parametrize(
        "language,tool",
        [
            ("python", "pip-licenses"),
            ("node", "license-checker"),
            ("go", "go-licenses"),
            ("rust", "cargo-deny"),
        ],
    )
    def test_per_language_tool_wired(self, tmp_path: Path, language: str, tool: str):
        ci = _ci(_scaffold(tmp_path / language, language))
        assert tool in ci
        assert "just license" in ci

    def test_renders_cleanly(self, tmp_path: Path):
        ci = _ci(_scaffold(tmp_path / "p", "rust"))
        assert "{{#if" not in ci and "{{/if" not in ci


class TestLicenseRecipe:
    @pytest.mark.parametrize(
        "language,needle",
        [
            ("python", 'pip-licenses --from=mixed --fail-on "GPL;AGPL" --partial-match'),
            ("node", 'license-checker --production --failOn "GPL'),
            ("go", "go-licenses check ./... --disallowed_types=forbidden,restricted"),
            ("rust", "cargo deny check licenses"),
        ],
    )
    def test_recipe_uses_expected_deny_list(self, tmp_path: Path, language: str, needle: str):
        justfile = _justfile(_scaffold(tmp_path / language, language))
        assert "license:" in justfile
        assert needle in justfile


class TestRustDenyToml:
    def test_deny_toml_rendered_for_rust(self, tmp_path: Path):
        deny = (_scaffold(tmp_path / "rust", "rust") / "deny.toml").read_text()
        assert "[licenses]" in deny
        assert "version = 2" in deny
        # Allow-list model; unused entries must not error.
        assert "unused-allowed-license" in deny
        assert '"MIT"' in deny and '"Apache-2.0"' in deny

    @pytest.mark.parametrize("language", ["python", "node", "go"])
    def test_deny_toml_absent_for_non_rust(self, tmp_path: Path, language: str):
        assert not (_scaffold(tmp_path / language, language) / "deny.toml").exists()


class TestLicenseDocumented:
    @pytest.mark.parametrize(
        "language,rules_file",
        [("python", "python.md"), ("node", "node.md"), ("go", "go.md"), ("rust", "rust.md")],
    )
    def test_rules_mention_license(self, tmp_path: Path, language: str, rules_file: str):
        rules = (_scaffold(tmp_path / language, language) / ".agents" / "rules" / rules_file).read_text()
        assert "license" in rules.lower()


class TestNodeLicenseScanInstall:
    """#738: the node install step must not swallow a stale lockfile, and the job
    must not be born red on a fresh scaffold.
    """

    def _job(self, tmp_path: Path) -> str:
        return _job_code(_ci(_scaffold(tmp_path / "n", "node")), "license-scan")

    def test_no_silent_fallback_off_frozen_lockfile(self, tmp_path: Path):
        """`--frozen-lockfile 2>/dev/null || bun install` rewrites bun.lock and
        installs the undeclared dep, so the scan inspects a dependency set the
        repo never committed. Verified against bun 1.3.14.
        """
        job = self._job(tmp_path)
        assert "|| bun install" not in job, job
        assert "2>/dev/null" not in job, job

    def test_frozen_only_when_a_lockfile_exists(self, tmp_path: Path):
        job = self._job(tmp_path)
        assert "bun install --frozen-lockfile" in job
        assert "[ -f bun.lock ]" in job

    def test_install_and_scan_are_skipped_without_a_package_json(self, tmp_path: Path):
        """A fresh scaffold has no package.json: `bun install` exits 1 there, and
        `bunx license-checker` exits 0 — born red, then vacuously green. Both
        steps gate on the manifest check instead.
        """
        job = self._job(tmp_path)
        assert "steps.pkg.outputs.exists == 'true'" in job
        gated = [
            line for line in job.splitlines()
            if line.strip().startswith("if: steps.pkg.outputs.exists")
        ]
        assert len(gated) == 2, f"expected install + scan gated, got {len(gated)}:\n{job}"
