"""PI-255: enterprise GitHub host support — host-aware lifecycle scripts and
install.sh API-base resolution (ADR-013, spike #254).

The lifecycle scripts are copied verbatim (not rendered), so host-awareness must
hold at runtime via the gh_host.sh helper rather than via template variables.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "templates/base/dot_claude/scripts"
# Lifecycle scripts moved to the lifecycle overlay (#476); gh_host.sh stays in
# base (shared host resolver also sourced by the deploy scripts).
_LIFECYCLE_SCRIPTS = _REPO_ROOT / "templates/lifecycle/dot_claude/scripts"
_GH_HOST = _SCRIPTS / "gh_host.sh"
_SETUP_GITHUB = _LIFECYCLE_SCRIPTS / "setup_github.sh"
_PUSH_WIKI = _LIFECYCLE_SCRIPTS / "push_wiki.sh"
_INSTALL = _REPO_ROOT / "install.sh"


class TestGhHostHelper:
    def test_helper_exists(self):
        assert _GH_HOST.exists(), "gh_host.sh must ship in templates/base scripts"

    def test_resolution_order_and_overrides_documented(self):
        s = _GH_HOST.read_text()
        for var in ("PROJECT_INIT_HOST", "GH_HOST", "PROJECT_INIT_API_BASE"):
            assert var in s, f"{var} must participate in host/API resolution"
        for fn in ("gh_host()", "gh_web_base()", "gh_api_base()"):
            assert fn in s

    def test_api_base_covers_every_host_tier(self):
        s = _GH_HOST.read_text()
        assert "/api/v3" in s, "GHES REST base must be handled"
        assert "api.%s" in s, "github.com & *.ghe.com use api.<host>"
        assert "*.ghe.com" in s, "data-residency hosts must be matched"


class TestScriptsAreHostAware:
    def test_setup_github_sources_helper(self):
        s = _SETUP_GITHUB.read_text()
        assert "gh_host.sh" in s
        assert 'gh auth status -h "$HOST"' in s, "auth check must target the repo host"

    def test_setup_github_has_no_hardcoded_repo_links(self):
        s = _SETUP_GITHUB.read_text()
        assert "https://github.com/$OWNER" not in s
        assert "https://github.com/users/$OWNER" not in s

    def test_push_wiki_clone_is_host_aware(self):
        s = _PUSH_WIKI.read_text()
        assert "gh_host.sh" in s
        assert "gh_web_base" in s
        assert "https://github.com/${REPO_SLUG}.wiki.git" not in s

    def test_install_sh_api_base_is_host_aware(self):
        s = _INSTALL.read_text()
        assert "PROJECT_INIT_API_BASE" in s
        assert "/api/v3" in s
        assert "https://api.github.com/repos/$slug" not in s, (
            "the release-tag API endpoint must be host-derived, not hardcoded"
        )


class TestHostHelperIsScaffolded:
    def test_gh_host_ships_into_projects(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        assert (target / ".claude" / "scripts" / "gh_host.sh").exists()


def _run_bash(snippet: str, *, cwd: Path | None = None, env_extra: dict | None = None) -> str:
    """Source gh_host.sh and run a snippet against the real helper. Host env vars
    are cleared so each case exercises the intended resolution path."""
    env = {k: v for k, v in os.environ.items() if k not in ("PROJECT_INIT_HOST", "GH_HOST")}
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["bash", "-c", f'. "{_GH_HOST}"; {snippet}'],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class TestGhHostParsing:
    """Behavioral tests — exercise the real bash helper, not just substrings, so
    broken URL parsing cannot pass silently (ssh:// and scheme-bearing forms)."""

    def test_normalize_handles_all_url_forms(self):
        cases = {
            "https://ghes.example.com/org/repo.git": "ghes.example.com",
            "ssh://git@ghes.example.com/org/repo.git": "ghes.example.com",
            "ssh://git@ghes.example.com:22/org/repo.git": "ghes.example.com",
            "git@github.com:owner/repo.git": "github.com",
            "https://octocorp.ghe.com/org/repo.git": "octocorp.ghe.com",
            "https://ghes.example.com": "ghes.example.com",
            "github.com": "github.com",
        }
        for raw, expected in cases.items():
            assert _run_bash(f'_gh_host_normalize "{raw}"') == expected, raw

    def test_override_with_scheme_is_normalized(self):
        # PROJECT_INIT_HOST short-circuits before any gh/git lookup.
        out = _run_bash("gh_host", env_extra={"PROJECT_INIT_HOST": "https://ghes.example.com"})
        assert out == "ghes.example.com"

    def test_ssh_remote_is_parsed(self, tmp_path: Path):
        repo = tmp_path / "r"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "ssh://git@ghes.example.com/org/repo.git"],
            cwd=repo,
            check=True,
        )
        # Empty gh config dir → gh is unauthenticated → fast fallback to the git remote.
        out = _run_bash("gh_host", cwd=repo, env_extra={"GH_CONFIG_DIR": str(tmp_path / "ghcfg")})
        assert out == "ghes.example.com"
