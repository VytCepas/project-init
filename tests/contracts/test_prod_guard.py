"""PI-168 / ADR-012: prod-safety guard contract — deny-table + wiring."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK = _REPO_ROOT / "templates" / "base" / "dot_agents" / "hooks" / "prod_guard.py"

DESTRUCTIVE = [
    "terraform destroy -auto-approve",
    # OpenTofu parity (PI-488): the `tofu` fork must be guarded like terraform.
    "tofu destroy -auto-approve",
    "tofu apply -destroy",
    # Global options before the verb must not slip past the guard (Codex P2).
    "tofu -chdir=infra destroy -auto-approve",
    "terraform -chdir=./infra apply -destroy",
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
    # Split recursive/force flags in any order + long forms must also be caught
    # (2026-07 review) — the old single-token pattern only matched -rf/-fr.
    "rm -r -f /var/lib/data",
    "rm -f -r /etc",
    "rm --recursive --force /var",
    "rm --force --recursive ~/data",
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
    # Parity: routine OpenTofu reads/applies are not destructive (PI-488).
    "tofu plan",
    "tofu apply -auto-approve",
    # `plan -destroy` only PREVIEWS a destroy — read-only, must stay unflagged
    # even though the flag-skip tolerates global options (Codex P2 review).
    "tofu plan -destroy",
    "tofu -chdir=infra apply -auto-approve",
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
        hso = verdict["hookSpecificOutput"]
        assert hso["permissionDecision"] == "deny"
        assert "prod_guard" in hso["permissionDecisionReason"]
        assert "credential separation" in hso["permissionDecisionReason"]

    @pytest.mark.parametrize("command", SAFE)
    def test_safe_commands_pass(self, tmp_path: Path, command: str):
        assert _run_hook(_payload(command, "bypassPermissions", tmp_path), tmp_path) is None

    def test_allowlist_suppresses_flag(self, tmp_path: Path):
        config = tmp_path / ".agents" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text('safety:\n  allow: ["kubectl delete .* --context kind-dev"]\n')
        command = "kubectl delete pod web --context kind-dev"
        assert _run_hook(_payload(command, "bypassPermissions", tmp_path), tmp_path) is None
        # Same verb without the allowed context is still blocked.
        other = "kubectl delete pod web --context prod"
        assert _run_hook(_payload(other, "bypassPermissions", tmp_path), tmp_path) is not None

    def test_allowlist_honored_from_subdirectory(self, tmp_path: Path):
        """Bash often runs after `cd` into a subdir — the guard walks up to
        the project's config.yaml (PR #174 review)."""
        config = tmp_path / ".agents" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text('safety:\n  allow: ["kubectl delete .* --context kind-dev"]\n')
        subdir = tmp_path / "services" / "api"
        subdir.mkdir(parents=True)
        command = "kubectl delete pod web --context kind-dev"
        payload = _payload(command, "bypassPermissions", subdir)
        assert _run_hook(payload, subdir) is None

    def test_symlinked_agents_dir_cannot_supply_an_allowlist(self, tmp_path: Path):
        """PI-903 (harbor#4 M13): a planted `.agents` symlink must not be read.

        `is_file()` follows symlinks, so an `.agents` link pointing outside the
        repo handed the guard an allowlist written outside the repo's own
        review — and `allow: [".*"]` switches the whole deny table off. The link
        is the payload; nothing inside the repo has to change for it to work.
        """
        outside = tmp_path / "outside" / ".agents"
        outside.mkdir(parents=True)
        (outside / "config.yaml").write_text('safety:\n  allow: [".*"]\n')
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".agents").symlink_to(outside, target_is_directory=True)

        command = "terraform destroy -auto-approve"
        assert _run_hook(_payload(command, "bypassPermissions", repo), repo) is not None, (
            "a symlinked .agents/ supplied safety.allow from outside the repo"
        )

    def test_symlinked_config_file_cannot_supply_an_allowlist(self, tmp_path: Path):
        """The other half: a real `.agents/` holding a symlinked config.yaml.
        Checking only the directory leaves the file — the thing actually read —
        pointing anywhere on disk."""
        (tmp_path / "outside").mkdir()
        planted = tmp_path / "outside" / "config.yaml"
        planted.write_text('safety:\n  allow: [".*"]\n')
        repo = tmp_path / "repo"
        (repo / ".agents").mkdir(parents=True)
        (repo / ".agents" / "config.yaml").symlink_to(planted)

        command = "terraform destroy -auto-approve"
        assert _run_hook(_payload(command, "bypassPermissions", repo), repo) is not None, (
            "a symlinked config.yaml supplied safety.allow from outside the repo"
        )

    def test_a_refused_symlink_does_not_stop_the_walk(self, tmp_path: Path):
        """Refusing must mean 'keep looking', not 'give up'. An inner symlinked
        marker shadowing a real outer one would otherwise silently discard the
        owner's genuine allowlist — matching harbor's floor_in_repo, which
        continues its walk past a refused marker rather than returning."""
        (tmp_path / "outside").mkdir()
        (tmp_path / "outside" / "config.yaml").write_text('safety:\n  allow: [".*"]\n')
        real = tmp_path / ".agents"
        real.mkdir()
        real.joinpath("config.yaml").write_text(
            'safety:\n  allow: ["kubectl delete .* --context kind-dev"]\n'
        )
        inner = tmp_path / "sub"
        inner.mkdir()
        (inner / ".agents").symlink_to(tmp_path / "outside", target_is_directory=True)

        # The planted `.*` is ignored…
        assert (
            _run_hook(
                _payload("terraform destroy -auto-approve", "bypassPermissions", inner), inner
            )
            is not None
        )
        # …and the real one an ancestor declares is still honoured.
        allowed = "kubectl delete pod web --context kind-dev"
        assert _run_hook(_payload(allowed, "bypassPermissions", inner), inner) is None

    def test_a_refused_link_does_not_change_ancestor_inheritance(self, tmp_path: Path):
        """PR #904 review (P1, refuted): a link pointing at an ANCESTOR's marker
        must resolve exactly as the same tree without the link.

        The review read this as a bypass — refuse the inner link, walk on, and
        the ancestor's `allow: [".*"]` is honoured anyway. It is not: walking up
        to an ancestor marker is the contract's defined behaviour when the repo
        has no marker of its own, so the link contributes nothing. Delete it and
        you reach the same config by the same route.

        The suggested mitigation — exclude refused link targets from the rest of
        the walk — would make these two trees DIVERGE: identical on-disk layouts
        resolving differently because an unrelated symlink happened to point at
        one of them. This pins them equal so that "fix" fails loudly.
        """
        linked = tmp_path / "linked"
        (linked / ".agents").mkdir(parents=True)
        (linked / ".agents" / "config.yaml").write_text('safety:\n  allow: [".*"]\n')
        (linked / "repo").mkdir()
        (linked / "repo" / ".agents").symlink_to(linked / ".agents", target_is_directory=True)

        plain = tmp_path / "plain"
        (plain / ".agents").mkdir(parents=True)
        (plain / ".agents" / "config.yaml").write_text('safety:\n  allow: [".*"]\n')
        (plain / "repo").mkdir()

        cmd = "terraform destroy -auto-approve"
        with_link = _run_hook(_payload(cmd, "bypassPermissions", linked / "repo"), linked / "repo")
        without = _run_hook(_payload(cmd, "bypassPermissions", plain / "repo"), plain / "repo")
        assert with_link == without, "a refused link changed how an ancestor marker resolves"

    def test_allowlist_multiline_yaml_suppresses_flag(self, tmp_path: Path):
        """PI-187: a multi-line YAML allow list must work, not just inline JSON
        — the old parser silently dropped it to []."""
        config = tmp_path / ".agents" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text('safety:\n  allow:\n    - "kubectl delete .* --context kind-dev"\n')
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

    def test_non_dict_json_stdin_fails_open(self, tmp_path: Path):
        """Valid JSON that isn't an object (e.g. a list) must not crash — the
        broad fail-open `try` is around evaluate(), so payload.get() needs its own
        type guard (Codex review)."""
        result = subprocess.run(
            ["python3", str(_HOOK)],
            input="[]",
            capture_output=True,
            text=True,
            cwd=tmp_path,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_non_dict_tool_input_fails_open(self, tmp_path: Path):
        """payload is a dict but `tool_input` is a non-dict (list/string): the
        `(... or {}).get()` form would raise on a truthy non-dict, so tool_input
        needs its own type guard too (Copilot review)."""
        result = subprocess.run(
            ["python3", str(_HOOK)],
            input='{"tool_input": ["not", "a", "dict"]}',
            capture_output=True,
            text=True,
            cwd=tmp_path,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_corrupt_allowlist_fails_open_but_still_guards(self, tmp_path: Path):
        config = tmp_path / ".agents" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("safety:\n  allow: [broken json\n")
        verdict = _run_hook(_payload("terraform destroy", "bypassPermissions", tmp_path), tmp_path)
        assert verdict is not None, "broken allowlist must not disable the guard"

    def test_scalar_inline_allow_does_not_overpermit(self, tmp_path: Path):
        """A scalar `allow:` (valid JSON string/object, not a list) must not be
        iterated character-by-character into an allowlist whose single-char
        patterns silently suppress every command (PI-187 review)."""
        config = tmp_path / ".agents" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text('safety:\n  allow: "terraform destroy"\n')
        verdict = _run_hook(_payload("terraform destroy", "bypassPermissions", tmp_path), tmp_path)
        assert verdict is not None, "a scalar allow must not disable the guard"


class TestWiring:
    def test_fallback_settings_wire_the_guard(self, tmp_path: Path):
        """Default scaffolds get the guard from the plugin; --no-plugin
        scaffolds wire the local copy."""
        from tests.helpers import fallback_preset, fallback_variables

        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        settings = json.loads((target / ".agents" / "settings.json").read_text())
        commands = [
            h["command"] for entry in settings["hooks"]["PreToolUse"] for h in entry["hooks"]
        ]
        assert any("prod_guard.py" in c for c in commands)
        assert (target / ".agents" / "hooks" / "prod_guard.py").is_file()

    def test_config_has_safety_allow_section(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        config = (target / ".agents" / "config.yaml").read_text()
        assert "safety:" in config
        assert "allow: []" in config

    def test_plugin_ships_the_guard(self):
        plugin_hooks = json.loads(
            (_REPO_ROOT / "plugins/project-init-workflow/hooks/hooks.json").read_text()
        )
        commands = [
            h["command"] for entry in plugin_hooks["hooks"]["PreToolUse"] for h in entry["hooks"]
        ]
        assert any("prod_guard.py" in c for c in commands)

    def test_docs_state_guardrail_vs_boundary(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        secrets = (target / ".agents" / "docs" / "guides" / "secrets.md").read_text()
        assert "guardrail" in secrets
        assert "cannot delete what the session cannot reach" in secrets
        agents_md = (target / "AGENTS.md").read_text()
        assert "prod_guard" in agents_md
