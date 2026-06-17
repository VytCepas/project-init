"""PI-168 / ADR-012: prod-safety guard contract — deny-table + wiring."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK = _REPO_ROOT / "templates" / "fallback" / "dot_claude" / "hooks" / "prod_guard.py"

DESTRUCTIVE = [
    "terraform destroy -auto-approve",
    "kubectl delete namespace prod",
    "helm uninstall api --namespace prod",
    "aws ec2 terminate-instances --instance-ids i-123",
    "aws s3 rb s3://prod-assets --force",
    "gcloud sql instances delete prod-db",
    "az group delete --name prod-rg",
    'psql -c "DROP DATABASE prod;"',
    "mysql -e 'drop table users'",
    "rm -rf /var/lib/data",
    "rm -rf ~/projects",
    "gh repo delete VytCepas/project-init",
    "docker system prune -af",
    # Global flags before the destructive verb (PR #174 review, P1).
    "kubectl --context prod delete namespace prod",
    "helm -n prod uninstall api",
    "aws --profile prod s3 rb s3://prod-assets --force",
    "aws --region eu-west-1 ec2 terminate-instances --instance-ids i-1",
]

SAFE = [
    "terraform plan",
    "kubectl get pods -n prod",
    "aws s3 ls",
    "git status",
    "rm -rf ./build",
    "rm -rf /tmp/scratch",
    "uv run pytest",
    "psql -c 'select * from users'",
]


def _run_hook(payload: dict, cwd: Path) -> dict | None:
    result = subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    )
    assert result.returncode == 0, "guard must always exit 0 (fail-open)"
    return json.loads(result.stdout) if result.stdout.strip() else None


def _payload(command: str, mode: str = "default", cwd: Path | None = None) -> dict:
    return {
        "tool_input": {"command": command},
        "permission_mode": mode,
        "cwd": str(cwd) if cwd else ".",
    }


class TestVerdicts:
    @pytest.mark.parametrize("command", DESTRUCTIVE)
    def test_destructive_asks_in_interactive(self, tmp_path: Path, command: str):
        verdict = _run_hook(_payload(command, "default", tmp_path), tmp_path)
        assert verdict is not None, f"not flagged: {command}"
        assert verdict["hookSpecificOutput"]["permissionDecision"] == "ask"

    @pytest.mark.parametrize("command", DESTRUCTIVE)
    def test_destructive_blocks_in_autonomous(self, tmp_path: Path, command: str):
        verdict = _run_hook(_payload(command, "bypassPermissions", tmp_path), tmp_path)
        assert verdict == {"decision": "block", "reason": verdict["reason"]}
        assert "prod_guard" in verdict["reason"]
        assert "credential separation" in verdict["reason"]

    @pytest.mark.parametrize("command", SAFE)
    def test_safe_commands_pass(self, tmp_path: Path, command: str):
        assert _run_hook(_payload(command, "bypassPermissions", tmp_path), tmp_path) is None

    def test_allowlist_suppresses_flag(self, tmp_path: Path):
        config = tmp_path / ".claude" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            'safety:\n  allow: ["kubectl delete .* --context kind-dev"]\n'
        )
        command = "kubectl delete pod web --context kind-dev"
        assert _run_hook(_payload(command, "bypassPermissions", tmp_path), tmp_path) is None
        # Same verb without the allowed context is still blocked.
        other = "kubectl delete pod web --context prod"
        assert _run_hook(_payload(other, "bypassPermissions", tmp_path), tmp_path) is not None

    def test_allowlist_honored_from_subdirectory(self, tmp_path: Path):
        """Bash often runs after `cd` into a subdir — the guard walks up to
        the project's config.yaml (PR #174 review)."""
        config = tmp_path / ".claude" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text('safety:\n  allow: ["kubectl delete .* --context kind-dev"]\n')
        subdir = tmp_path / "services" / "api"
        subdir.mkdir(parents=True)
        command = "kubectl delete pod web --context kind-dev"
        payload = _payload(command, "bypassPermissions", subdir)
        assert _run_hook(payload, subdir) is None

    def test_allowlist_multiline_yaml_suppresses_flag(self, tmp_path: Path):
        """PI-187: a multi-line YAML allow list must work, not just inline JSON
        — the old parser silently dropped it to []."""
        config = tmp_path / ".claude" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            'safety:\n  allow:\n    - "kubectl delete .* --context kind-dev"\n'
        )
        command = "kubectl delete pod web --context kind-dev"
        assert _run_hook(_payload(command, "bypassPermissions", tmp_path), tmp_path) is None
        # A verb not on the list is still blocked.
        other = "kubectl delete pod web --context prod"
        assert _run_hook(_payload(other, "bypassPermissions", tmp_path), tmp_path) is not None

    def test_garbage_stdin_fails_open(self, tmp_path: Path):
        result = subprocess.run(
            ["python3", str(_HOOK)],
            input="not json at all",
            capture_output=True,
            text=True,
            cwd=tmp_path,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_corrupt_allowlist_fails_open_but_still_guards(self, tmp_path: Path):
        config = tmp_path / ".claude" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("safety:\n  allow: [broken json\n")
        verdict = _run_hook(
            _payload("terraform destroy", "bypassPermissions", tmp_path), tmp_path
        )
        assert verdict is not None, "broken allowlist must not disable the guard"

    def test_scalar_inline_allow_does_not_overpermit(self, tmp_path: Path):
        """A scalar `allow:` (valid JSON string/object, not a list) must not be
        iterated character-by-character into an allowlist whose single-char
        patterns silently suppress every command (PI-187 review)."""
        config = tmp_path / ".claude" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text('safety:\n  allow: "terraform destroy"\n')
        verdict = _run_hook(
            _payload("terraform destroy", "bypassPermissions", tmp_path), tmp_path
        )
        assert verdict is not None, "a scalar allow must not disable the guard"


class TestWiring:
    def test_fallback_settings_wire_the_guard(self, tmp_path: Path):
        """Default scaffolds get the guard from the plugin; --no-plugin
        scaffolds wire the local copy."""
        from tests.helpers import fallback_preset, fallback_variables

        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        commands = [
            h["command"]
            for entry in settings["hooks"]["PreToolUse"]
            for h in entry["hooks"]
        ]
        assert any("prod_guard.py" in c for c in commands)
        assert (target / ".claude" / "hooks" / "prod_guard.py").is_file()

    def test_config_has_safety_allow_section(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        config = (target / ".claude" / "config.yaml").read_text()
        assert "safety:" in config
        assert "allow: []" in config

    def test_plugin_ships_the_guard(self):
        plugin_hooks = json.loads(
            (_REPO_ROOT / "plugins/project-init-workflow/hooks/hooks.json").read_text()
        )
        commands = [
            h["command"]
            for entry in plugin_hooks["hooks"]["PreToolUse"]
            for h in entry["hooks"]
        ]
        assert any("prod_guard.py" in c for c in commands)

    def test_docs_state_guardrail_vs_boundary(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        secrets = (target / ".claude" / "docs" / "guides" / "secrets.md").read_text()
        assert "guardrail" in secrets
        assert "cannot delete what the session cannot reach" in secrets
        agents_md = (target / "AGENTS.md").read_text()
        assert "prod_guard" in agents_md
