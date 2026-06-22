from __future__ import annotations

from pathlib import Path

import pytest


class TestMCPs:
    """Unit tests for the MCP catalog and formatting helpers."""

    def test_catalog_has_required_keys(self):
        from project_init.mcps import MCP_CATALOG
        for m in MCP_CATALOG:
            assert "id" in m
            assert "name" in m
            assert "description" in m
            assert "command" in m

    def test_catalog_contains_core_mcps(self):
        from project_init.mcps import MCP_CATALOG
        ids = {m["id"] for m in MCP_CATALOG}
        # Linear, GitHub, Filesystem removed (PI-25/PI-26): CLI alternatives cover all needs
        assert "context7" in ids
        assert "linear" not in ids
        assert "github" not in ids
        assert "filesystem" not in ids

    def test_no_db_catalog(self):
        """PI-387: postgres/sqlite DB MCPs removed (archived + unpatched CVEs)."""
        import project_init.mcps as mcps
        assert not hasattr(mcps, "DB_CATALOG")

    def test_playwright_mcp_defined(self):
        from project_init.mcps import PLAYWRIGHT_MCP
        assert PLAYWRIGHT_MCP["id"] == "playwright"
        assert "command" in PLAYWRIGHT_MCP

    def test_no_npx_in_any_command(self):
        from project_init.mcps import MCP_CATALOG, PLAYWRIGHT_MCP
        all_commands = [m["command"] for m in MCP_CATALOG] + [PLAYWRIGHT_MCP["command"]]
        for cmd in all_commands:
            assert "npx" not in cmd, f"npx found in command: {cmd}"
            assert "npm" not in cmd, f"npm found in command: {cmd}"

    def test_all_commands_use_bunx_with_separator(self):
        """Stdio entries use `bunx` with the `--` separator (PI-387); HTTP entries
        use `--transport http` instead (PI-397)."""
        from project_init.mcps import MCP_CATALOG, PLAYWRIGHT_MCP
        for entry in [*MCP_CATALOG, PLAYWRIGHT_MCP]:
            cmd = entry["command"]
            if "url" in entry.get("server", {}):  # HTTP/remote entry
                assert "--transport http" in cmd, f"HTTP entry must use --transport http: {cmd}"
            else:
                assert "bunx" in cmd, f"bunx not found in command: {cmd}"
                assert " -- " in cmd, f"missing `--` separator in command: {cmd}"

    def test_http_catalog_entry_exists(self):
        """PI-397: an HTTP/streamable catalog entry for cloud surfaces (web/mobile
        can't run stdio); never SSE."""
        from project_init.mcps import MCP_CATALOG
        http = [m for m in MCP_CATALOG if m["server"].get("type") == "http"]
        assert http, "expected at least one HTTP MCP catalog entry"
        for m in http:
            assert m["server"]["url"].startswith("https://")
            assert "--transport http" in m["command"]

    def test_format_installed_mcps_empty(self):
        from project_init.mcps import format_installed_mcps
        assert format_installed_mcps([]) == "none"

    def test_format_installed_mcps_single(self):
        from project_init.mcps import MCP_CATALOG, format_installed_mcps
        context7 = next(m for m in MCP_CATALOG if m["id"] == "context7")
        assert format_installed_mcps([context7]) == "context7"

    def test_format_installed_mcps_multiple(self):
        from project_init.mcps import MCP_CATALOG, PLAYWRIGHT_MCP, format_installed_mcps
        subset = [next(m for m in MCP_CATALOG if m["id"] == "context7"), PLAYWRIGHT_MCP]
        result = format_installed_mcps(subset)
        assert "context7" in result and "playwright" in result

    def test_format_installed_mcps_yaml_empty(self):
        from project_init.mcps import format_installed_mcps_yaml
        assert format_installed_mcps_yaml([]) == "[]"

    def test_format_installed_mcps_yaml_single(self):
        from project_init.mcps import MCP_CATALOG, format_installed_mcps_yaml
        context7 = next(m for m in MCP_CATALOG if m["id"] == "context7")
        assert format_installed_mcps_yaml([context7]) == '["context7"]'

    def test_format_installed_mcps_yaml_multiple(self):
        from project_init.mcps import MCP_CATALOG, PLAYWRIGHT_MCP, format_installed_mcps_yaml
        subset = [next(m for m in MCP_CATALOG if m["id"] == "context7"), PLAYWRIGHT_MCP]
        result = format_installed_mcps_yaml(subset)
        assert result.startswith("[") and result.endswith("]")
        assert '"context7"' in result and '"playwright"' in result


class TestMCPsNonInteractive:
    """Test --mcps / --browser flags via non-interactive CLI."""

    def test_mcps_flag_context7(self, tmp_path: Path):
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "mcp-test",
            "--description", "test",
            "--language", "python",
            "--mcps", "context7",
        ])
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert "context7" in config

    def test_db_flag_removed(self):
        """PI-387: --db is gone; passing it must be a CLI error."""
        from project_init.__main__ import main
        with pytest.raises(SystemExit):
            main(["x", "--non-interactive", "--preset", "obsidian-only",
                   "--name", "n", "--description", "d", "--language", "python",
                   "--db", "postgres"])

    def test_browser_flag_adds_playwright(self, tmp_path: Path):
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "browser-test",
            "--description", "test",
            "--language", "python",
            "--browser",
        ])
        assert rc == 0
        config = (target / ".clone" / "config.yaml") if False else (target / ".claude" / "config.yaml")
        assert "playwright" in config.read_text()

    def test_no_mcps_gives_none(self, tmp_path: Path):
        from project_init.__main__ import main
        target = tmp_path / "p"
        rc = main([
            str(target), "--non-interactive",
            "--preset", "obsidian-only",
            "--name", "empty-test",
            "--description", "test",
            "--language", "python",
        ])
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert "installed: []" in config

    def test_unknown_mcp_id_is_rejected(self, tmp_path: Path):
        """Silently ignoring typos hides real bugs — unknown IDs must error out."""
        from project_init.__main__ import main
        target = tmp_path / "p"
        with pytest.raises(SystemExit):
            main([
                str(target), "--non-interactive",
                "--preset", "obsidian-only",
                "--name", "bad-mcp-test",
                "--description", "test",
                "--language", "python",
                "--mcps", "nonexistent,anotherunknown",
            ])

    def test_unknown_preset_does_not_create_target_dir(self, tmp_path: Path):
        """A typo in --preset must fail BEFORE the target directory is created."""
        from project_init.__main__ import main
        target = tmp_path / "should-not-exist"
        with pytest.raises(SystemExit):
            main([
                str(target), "--non-interactive",
                "--preset", "definitely-not-a-real-preset",
                "--name", "x",
                "--description", "x",
            ])
        assert not target.exists(), (
            f"target dir {target} was created despite invalid preset"
        )

    def test_unknown_mcp_id_does_not_create_target_dir(self, tmp_path: Path):
        """An invalid MCP id must fail BEFORE the target directory is created. PI-20."""
        from project_init.__main__ import main
        target = tmp_path / "should-not-exist"
        with pytest.raises(SystemExit):
            main([
                str(target), "--non-interactive",
                "--preset", "obsidian-only",
                "--name", "test",
                "--description", "test",
                "--language", "python",
                "--mcps", "fakeone,anotherunknown",
            ])
        assert not target.exists(), (
            f"target dir {target} was created despite invalid MCP id"
        )
