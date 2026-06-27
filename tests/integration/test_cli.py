from __future__ import annotations

from pathlib import Path

import pytest


class TestCLI:
    def test_non_interactive_obsidian_only(self, tmp_target: Path):
        from project_init.__main__ import main

        rc = main(
            [
                str(tmp_target),
                "--non-interactive",
                "--preset",
                "obsidian-only",
                "--name",
                "cli-test",
                "--description",
                "testing cli",
                "--language",
                "python",
            ]
        )
        assert rc == 0
        assert (tmp_target / ".claude" / "config.yaml").is_file()

    def test_non_interactive_graphify(self, tmp_target: Path):
        from project_init.__main__ import main

        rc = main(
            [
                str(tmp_target),
                "--non-interactive",
                "--preset",
                "obsidian-graphify",
                "--name",
                "cli-gr",
                "--description",
                "testing graphify",
                "--language",
                "python",
            ]
        )
        assert rc == 0
        assert (tmp_target / ".claude" / "scripts" / "setup_graphify.sh").is_file()

    def test_interactive_abort_at_prompt_leaves_no_dir(self, tmp_path: Path, monkeypatch):
        """PI-199: a Ctrl-C (or error) at an interactive prompt must not leave
        an empty target dir behind — input is gathered before the dir exists."""
        from project_init import __main__

        target = tmp_path / "aborted-proj"

        def boom(**_kw):
            raise KeyboardInterrupt

        monkeypatch.setattr(__main__, "_gather_inputs_interactive", boom)
        with pytest.raises(KeyboardInterrupt):
            # Interactive (no --non-interactive); --preset skips the preset prompt.
            __main__.main([str(target), "--preset", "obsidian-only"])
        assert not target.exists()

    def test_non_interactive_requires_flags(self):
        from project_init.__main__ import main

        with pytest.raises(SystemExit):
            main(["--non-interactive"])

    def test_target_is_existing_file_rejected_cleanly(self, tmp_path: Path):
        """A target that exists as a file must fail with a clean parser error,
        not an uncaught FileExistsError from mkdir(exist_ok=True) (e2e sweep)."""
        from project_init.__main__ import main

        target = tmp_path / "afile"
        target.write_text("x")
        with pytest.raises(SystemExit) as exc:
            main(
                [
                    str(target),
                    "--non-interactive",
                    "--name",
                    "p",
                    "--description",
                    "d",
                    "--language",
                    "python",
                    "--preset",
                    "core",
                ]
            )
        assert exc.value.code == 2  # argparse parser.error exit code

    @pytest.mark.parametrize(
        "bad_name",
        [
            'ev"il',
            "C:\\projects\\foo",
            "line\nbreak",
            "del\x7fchar",
            "nel\x85here",
            "lsep\u2028here",
            "psep\u2029here",
        ],
        ids=[
            "double-quote",
            "backslash",
            "newline",
            "del-0x7f",
            "nel-0x85",
            "line-sep-2028",
            "para-sep-2029",
        ],
    )
    def test_yaml_breaking_name_rejected(self, tmp_path: Path, bad_name: str):
        """Quotes/backslashes/newlines/control chars (incl. DEL) in name/desc/owner
        are rejected — each would corrupt config.yaml's double-quoted YAML value
        (e2e sweep + Codex/Copilot review)."""
        from project_init.__main__ import main

        with pytest.raises(SystemExit) as exc:
            main(
                [
                    str(tmp_path / "p"),
                    "--non-interactive",
                    "--name",
                    bad_name,
                    "--description",
                    "d",
                    "--language",
                    "python",
                    "--preset",
                    "core",
                ]
            )
        assert exc.value.code == 2
        assert not (tmp_path / "p").exists()  # rejected before creating the dir

    def test_apostrophe_in_name_allowed(self, tmp_path: Path):
        """Single quotes are safe in double-quoted YAML — must NOT be rejected."""
        from project_init.__main__ import main

        target = tmp_path / "p"
        rc = main(
            [
                str(target),
                "--non-interactive",
                "--name",
                "Vy's tool",
                "--description",
                "A 'fast' one",
                "--language",
                "python",
                "--preset",
                "core",
            ]
        )
        assert rc == 0
        assert 'Vy\'s tool' in (target / ".claude" / "config.yaml").read_text()

    def test_target_mkdir_oserror_reported_cleanly(self, tmp_path: Path, monkeypatch):
        """A mkdir OSError (e.g. PermissionError on a read-only parent) must surface
        as a clean parser error, not an uncaught traceback (e2e sweep)."""
        from project_init import __main__
        from project_init.__main__ import main

        def boom(*_a, **_k):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(__main__.Path, "mkdir", boom)
        with pytest.raises(SystemExit) as exc:
            main(
                [
                    str(tmp_path / "sub"),
                    "--non-interactive",
                    "--name",
                    "p",
                    "--description",
                    "d",
                    "--language",
                    "python",
                    "--preset",
                    "core",
                ]
            )
        assert exc.value.code == 2


class TestCLIGovernanceFlags:
    """PI-145: --license and --owner render governance files."""

    def _run(self, target: Path, *extra: str) -> int:
        from project_init.__main__ import main

        return main(
            [
                str(target),
                "--non-interactive",
                "--preset",
                "obsidian-only",
                "--name",
                "gov-cli",
                "--description",
                "test",
                "--language",
                "python",
                *extra,
            ]
        )

    def test_license_and_owner_render(self, tmp_path: Path):
        from datetime import date

        target = tmp_path / "p"
        assert self._run(target, "--license", "mit", "--owner", "@acme/core") == 0
        license_text = (target / "LICENSE").read_text()
        assert "MIT License" in license_text
        # PI-181: the LICENSE copyright holder drops the GitHub-handle "@" ...
        assert f"{date.today().year} acme/core" in license_text
        assert "@acme/core" not in license_text
        # ... while CODEOWNERS keeps it (required syntax).
        assert "*       @acme/core" in (target / ".github" / "CODEOWNERS").read_text()

    def test_no_license_flag_renders_no_file(self, tmp_path: Path):
        target = tmp_path / "p"
        assert self._run(target) == 0
        assert not (target / "LICENSE").exists()
        assert (target / "CONTRIBUTING.md").exists()

    def test_invalid_license_is_rejected(self, tmp_path: Path):
        with pytest.raises(SystemExit):
            self._run(tmp_path / "p", "--license", "gpl-3.0")

    def test_license_holder_falls_back_to_project_name(self, tmp_path: Path):
        target = tmp_path / "p"
        assert self._run(target, "--license", "proprietary") == 0
        assert "gov-cli. All rights reserved." in (target / "LICENSE").read_text()


class TestCLIOverlayFlags:
    """PI-140/PI-146: opt-in overlay flags render their files; defaults stay off."""

    def _run(self, target: Path, *extra: str) -> int:
        from project_init.__main__ import main

        return main(
            [
                str(target),
                "--non-interactive",
                "--preset",
                "obsidian-only",
                "--name",
                "overlay-cli",
                "--description",
                "test",
                "--language",
                "python",
                *extra,
            ]
        )

    def test_all_overlays_render(self, tmp_path: Path):
        target = tmp_path / "p"
        assert self._run(target, "--mise", "--vscode", "--devcontainer") == 0
        assert (target / "mise.toml").exists()
        assert (target / ".vscode" / "settings.json").exists()
        assert (target / ".devcontainer" / "devcontainer.json").exists()

    def test_default_scaffold_unchanged(self, tmp_path: Path):
        target = tmp_path / "p"
        assert self._run(target) == 0
        assert not (target / "mise.toml").exists()
        assert not (target / ".vscode").exists()
        assert not (target / ".devcontainer").exists()
        assert (target / ".env.example").exists(), "env pattern is always scaffolded"

    def test_agents_flag_renders_overlays(self, tmp_path: Path):
        target = tmp_path / "p"
        assert self._run(target, "--agents", "codex,antigravity,ollama") == 0
        assert (target / ".agents" / "skills" / "github_workflow" / "SKILL.md").is_file()
        assert (target / ".codex" / "hooks.json").is_file()
        assert (target / ".agents" / "hooks.json").is_file()
        assert (target / ".claude" / "hooks" / "agent_guard_adapter.py").is_file()

    def test_agents_default_is_claude_only(self, tmp_path: Path):
        target = tmp_path / "p"
        assert self._run(target) == 0
        assert not (target / ".agents").exists()
        assert not (target / ".codex").exists()

    def test_unknown_agent_rejected(self, tmp_path: Path):
        with pytest.raises(SystemExit):
            self._run(tmp_path / "p", "--agents", "claude,windsurf")

    def test_upgrade_re_renders_agent_overlays(self, tmp_path: Path):
        """The recorded agents list restores overlay layers on re-render —
        a codex-scaffolded project upgrades drift-free."""
        from project_init.__main__ import main

        target = tmp_path / "p"
        assert self._run(target, "--agents", "codex") == 0
        assert main(["upgrade", str(target), "--apply"]) == 0
        assert (target / ".codex" / "hooks.json").is_file()
        # No spurious .new conflicts from the overlay files.
        assert not list(target.rglob("*.new"))


class TestCLINonInteractiveCommandVariables:
    """PI-16: CLI passes correct command variables based on --language."""

    def test_python_cli_writes_uv_commands(self, tmp_path: Path):
        from project_init.__main__ import main

        target = tmp_path / "p"
        rc = main(
            [
                str(target),
                "--non-interactive",
                "--preset",
                "obsidian-only",
                "--name",
                "py-cli",
                "--description",
                "test",
                "--language",
                "python",
            ]
        )
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert 'lint_command: "uv run ruff check ."' in config

    def test_node_cli_writes_bun_commands(self, tmp_path: Path):
        from project_init.__main__ import main

        target = tmp_path / "p"
        rc = main(
            [
                str(target),
                "--non-interactive",
                "--preset",
                "obsidian-only",
                "--name",
                "node-cli",
                "--description",
                "test",
                "--language",
                "node",
            ]
        )
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert 'lint_command: "bunx eslint ."' in config

    def test_go_cli_writes_go_commands(self, tmp_path: Path):
        from project_init.__main__ import main

        target = tmp_path / "p"
        rc = main(
            [
                str(target),
                "--non-interactive",
                "--preset",
                "obsidian-only",
                "--name",
                "go-cli",
                "--description",
                "test",
                "--language",
                "go",
            ]
        )
        assert rc == 0
        config = (target / ".claude" / "config.yaml").read_text()
        assert 'lint_command: "golangci-lint run"' in config
        assert 'test_command: "go test ./..."' in config
