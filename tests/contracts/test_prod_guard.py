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
    # ── PI-906: the cloud/data verb set the table used to miss entirely ──
    # BigQuery removal — dataset (-r -d) is the wide blast radius, table (-t)
    # the common one; a global flag may precede the verb.
    "bq rm -r -f -d my-proj:analytics",
    "bq rm -f -t my-proj:analytics.sessions",
    "bq --project_id=my-proj rm -r -f -d analytics",
    # GCS recursive removal, BOTH spellings. `gcloud storage rm` carries no
    # `delete` token, so the pre-existing `gcloud delete` rule never saw it.
    "gsutil rm -r gs://prod-assets",
    "gsutil -m rm -r gs://prod-assets/exports",
    "gsutil rm -R gs://prod-assets",
    "gcloud storage rm -r gs://prod-assets",
    "gcloud storage rm --recursive gs://prod-assets/exports",
    # dbt --full-refresh drops and rebuilds incrementals; flags in either order.
    "dbt run --full-refresh --target prod",
    "dbt run --target prod --full-refresh",
    "dbt run --full-refresh -t prod",
    "dbt run --full-refresh --target=production",
    # Shell-quoted target values (PR #915 review, P1). The shell strips these
    # before dbt sees them; the guard reads the raw command, so it must too.
    'dbt run --full-refresh --target "prod"',
    "dbt run --full-refresh --target='prod'",
    'dbt run --full-refresh --target "production"',
    # IAM mutation on a shared identity: high-privilege grants and any removal.
    "gcloud projects add-iam-policy-binding mbd --member=user:a@b.c --role roles/owner",
    "gcloud projects add-iam-policy-binding mbd --member=user:a@b.c --role=roles/editor",
    "gcloud projects add-iam-policy-binding mbd --member=user:a@b.c --role=roles/storage.admin",
    "gcloud projects remove-iam-policy-binding mbd --member=user:a@b.c --role=roles/viewer",
    # Quoted role values (PR #915 review, P1) — gcloud receives an identical
    # argument, so the guard must see through the quoting the shell removes.
    'gcloud projects add-iam-policy-binding mbd --member=user:a@b.c --role="roles/owner"',
    "gcloud projects add-iam-policy-binding mbd --member=user:a@b.c --role='roles/editor'",
    'gcloud projects add-iam-policy-binding mbd --member=user:a@b.c --role="roles/storage.admin"',
    # A full-table DELETE empties it as surely as TRUNCATE.
    'bq query --use_legacy_sql=false "DELETE FROM analytics.sessions WHERE 1=1"',
    "psql -c 'delete from users'",
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
    # ── PI-906 negative cases. These are DAILY commands: a guard that nags on
    # them gets switched off, and a disabled guard protects nothing. Every rule
    # added for PI-906 has its counterpart here.
    'bq query --use_legacy_sql=false "SELECT 1"',
    # A SELECT may legitimately carry the word `delete` in a column, a literal
    # or an identifier — only `DELETE FROM` is the destructive statement.
    "bq query \"SELECT is_deleted FROM analytics.sessions WHERE state = 'delete'\"",
    # "delete from" IS ORDINARY ENGLISH, unlike "drop table" or "truncate
    # table". The first cut of this rule was a bare `\bdelete\s+from\b` and it
    # flagged all six of these — measured against the real DENY_RULES, not
    # supposed. Every one is a command someone types weekly, and the last three
    # concern the guard's own subject matter, so writing a commit message about
    # this very rule tripped it.
    'git commit -m "chore: delete from the stale cache"',
    'git log --grep "delete from"',
    "echo 'how to delete from a list in python'",
    'grep -rn "DELETE FROM" src/',
    "# TODO: delete from the queue once drained",
    'echo "we should delete from that table eventually"',
    "bq ls my-proj:analytics",
    "bq show my-proj:analytics.sessions",
    "bq load --source_format=CSV my-proj:analytics.t gs://b/f.csv",
    # Reading the guarded command's own docs is not running it.
    "bq rm --help",
    # The rule exempts BOTH help spellings; only the long one was pinned, so a
    # regression that dropped `-h` would have gone unnoticed (PR #915 review).
    "bq rm -h",
    "bq help rm",
    "gsutil ls gs://prod-assets",
    "gsutil cp gs://prod-assets/a.csv .",
    # `-r` on a COPY is routine; only a recursive rm is flagged.
    "gsutil -m cp -r ./dist gs://prod-assets/dist",
    "gcloud storage ls gs://prod-assets",
    "gcloud storage cp -r ./dist gs://prod-assets/dist",
    # Deliberate parity with the `aws s3 rm --recursive` rule: a SINGLE-object
    # delete is not flagged, only the recursive form that empties a bucket.
    # Pinned because an over-match mutant that dropped the recursive
    # requirement otherwise survived the whole suite (PI-906 mutation run).
    "gsutil rm gs://prod-assets/one-export.csv",
    "gcloud storage rm gs://prod-assets/one-export.csv",
    "dbt run",
    "dbt run --target dev",
    # Deliberate: a full refresh against a DEV target is ordinary work.
    "dbt run --full-refresh --target dev",
    # `prod-dev` is a DEV target whose name merely starts with the guarded
    # letters. The first cut flagged it, because a plain `\b` after `prod`
    # matches inside `prod-dev` — `-` is a non-word character (PR #915 review).
    "dbt run --full-refresh --target prod-dev",
    "dbt run --full-refresh --target=prod-staging",
    "dbt test",
    "dbt build --target dev",
    "gcloud projects get-iam-policy mbd",
    # A low-privilege grant is not an estate handover.
    "gcloud projects add-iam-policy-binding mbd --member=user:a@b.c --role=roles/bigquery.dataViewer",
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

    @pytest.mark.parametrize(
        ("command", "label"),
        [
            ("bq rm -r -f -d my-proj:analytics", "bq rm (BigQuery dataset/table removal)"),
            ("gsutil rm -r gs://prod-assets", "gsutil recursive bucket removal"),
            # THE RULE DEFECT (PI-906): this used to slip past a rule that looks
            # like it covers gcloud. `\bgcloud\b…\bdelete\b` keys on the token
            # `delete`, and the modern spelling of recursive bucket deletion
            # does not carry it. Pinning the LABEL, not just "flagged", is what
            # makes that regression visible — a command caught incidentally by
            # some other rule would report a different one.
            (
                "gcloud storage rm -r gs://prod-assets",
                "gcloud storage recursive bucket removal",
            ),
            (
                "dbt run --full-refresh --target prod",
                "dbt --full-refresh against a production target",
            ),
            (
                "gcloud projects add-iam-policy-binding mbd --member=user:a@b.c --role roles/owner",
                "gcloud IAM grant of owner/editor/admin",
            ),
            (
                "gcloud projects remove-iam-policy-binding mbd --member=user:a@b.c --role=roles/x",
                "gcloud IAM binding removal",
            ),
            ('psql -c "DELETE FROM sessions WHERE 1=1"', "SQL DELETE FROM"),
        ],
    )
    def test_each_new_rule_is_the_one_that_fires(self, tmp_path: Path, command: str, label: str):
        """PI-906: each command is caught by its OWN rule, not by accident."""
        verdict = _run_hook(_payload(command, "bypassPermissions", tmp_path), tmp_path)
        assert verdict is not None, f"not flagged: {command}"
        reason = verdict["hookSpecificOutput"]["permissionDecisionReason"]
        assert f"'{label}'" in reason, reason

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


_DESTRUCTIVE = "terraform destroy -auto-approve"
_PERMISSIVE = 'safety:\n  allow: [".*"]\n'


def _flagged(cwd: Path) -> bool:
    """True when the guard flags a destructive command run from *cwd*."""
    return _run_hook(_payload(_DESTRUCTIVE, "bypassPermissions", cwd), cwd) is not None


class TestContextMarkerValue:
    """harbor#4 H1 — the `context:` value, whose reader lived only in harbor.

    project-init has WRITTEN this key since PI-901 (template + upgrade splice)
    and read it nowhere, so `context: ambient` was a field the schema defines,
    the wizard emits and no code in this repo acts on. Every case here is a
    fixture in harbor's shared suite (fixtures/marker/cases.json); the ids are
    quoted so a divergence is traceable to one line of one contract.

    What `ambient` means HERE: the owner declaring the repo does not govern
    itself, so its `safety.allow` does not relax the deny table. The safe
    direction, and the one the guard already takes when no config exists.
    """

    def test_ambient_repo_cannot_supply_an_allowlist(self, tmp_path: Path):
        """M18: the opt-out decides, even though the marker is present."""
        agents = tmp_path / ".agents"
        agents.mkdir()
        agents.joinpath("config.yaml").write_text("context: ambient\n" + _PERMISSIVE)
        assert _flagged(tmp_path), "an opted-out repo relaxed the deny table anyway"

    def test_context_repo_still_supplies_its_allowlist(self, tmp_path: Path):
        """M20: the value only ever ADDS an opt-out. `context: repo` is what
        every fresh scaffold emits, and it must resolve exactly as presence
        alone already did — the case that proves the reader discriminates
        rather than merely rejecting everything."""
        agents = tmp_path / ".agents"
        agents.mkdir()
        agents.joinpath("config.yaml").write_text("context: repo\n" + _PERMISSIVE)
        assert not _flagged(tmp_path), "a governed repo lost its own allowlist"

    def test_absent_context_is_not_ambient(self, tmp_path: Path):
        """M21: every config scaffolded before PI-901 lacks the key, which is
        why `context` is optional in the schema. Absence means unknown and
        falls back to presence; reading it as `ambient` would silently drop the
        allowlist of the entire installed base."""
        agents = tmp_path / ".agents"
        agents.mkdir()
        agents.joinpath("config.yaml").write_text(_PERMISSIVE)
        assert not _flagged(tmp_path)

    def test_commented_out_ambient_is_documentation(self, tmp_path: Path):
        """M22: `# context: ambient` is a note someone wrote, not a declaration."""
        agents = tmp_path / ".agents"
        agents.mkdir()
        agents.joinpath("config.yaml").write_text(
            "# context: ambient\ncontext: repo\n" + _PERMISSIVE
        )
        assert not _flagged(tmp_path)

    def test_nested_context_key_is_a_different_key(self, tmp_path: Path):
        """M23: `context` is TOP-LEVEL. One indented under an unrelated block
        shares a name and nothing else — matching it would opt a whole repo out
        on the strength of a nested value nobody meant as a boundary."""
        agents = tmp_path / ".agents"
        agents.mkdir()
        agents.joinpath("config.yaml").write_text(
            "context: repo\ntooling:\n  context: ambient\n" + _PERMISSIVE
        )
        assert not _flagged(tmp_path)

    @pytest.mark.parametrize(
        ("spelling", "case"),
        [
            ("context : ambient\n", "M25 space before the colon"),
            ('"context": ambient\n', "M26 quoted key"),
            ('context: "ambient"\n', "M27 quoted value"),
            ("context: ambient  # opted out\n", "trailing comment"),
            ("context: ambient\t# tab before the comment\n", "tab before the comment"),
        ],
    )
    def test_every_valid_top_level_spelling_counts(self, tmp_path: Path, spelling: str, case: str):
        """M25-M27: the reader is deliberately the permissive one about
        spelling, because MISSING a genuine opt-out is the unsafe direction —
        the repo keeps a governed repo's privileges it disclaimed. `upgrade.py`
        preserves exactly these spellings, so a spelling the writer keeps and
        the reader misses is an opt-out that survives in the file and is then
        ignored."""
        agents = tmp_path / ".agents"
        agents.mkdir()
        agents.joinpath("config.yaml").write_text(spelling + _PERMISSIVE)
        assert _flagged(tmp_path), f"{case}: a valid opt-out was not read"

    @pytest.mark.parametrize(
        "spelling",
        ["context: ambient#typo\n", 'context: "ambient"#x\n', "context: ambientish\n"],
    )
    def test_a_hash_without_whitespace_is_part_of_the_value(self, tmp_path: Path, spelling: str):
        """PR #927 review. `#` begins a YAML comment only when preceded by
        whitespace; otherwise it belongs to the plain scalar. So
        `context: ambient#typo` is the value `ambient#typo`, not `ambient`, and
        reading it as an opt-out silently discards the repo's allowlist on a
        typo. The direction is safe for this guard and still wrong — the
        orchestrator's real YAML parser resolves the same line differently, and
        three readers disagreeing about one line is what the shared fixtures
        exist to prevent."""
        agents = tmp_path / ".agents"
        agents.mkdir()
        agents.joinpath("config.yaml").write_text(spelling + _PERMISSIVE)
        assert not _flagged(tmp_path), f"{spelling!r} was read as an opt-out"

    def test_inner_optout_is_not_overruled_by_an_outer_marker(self, tmp_path: Path):
        """M19: the value is read AT the marker the walk finds and decides
        there. Continuing the walk would let an outer repo's allowlist govern a
        directory whose owner explicitly opted out."""
        outer = tmp_path / ".agents"
        outer.mkdir()
        outer.joinpath("config.yaml").write_text("context: repo\n" + _PERMISSIVE)
        inner = tmp_path / "sub"
        (inner / ".agents").mkdir(parents=True)
        (inner / ".agents" / "config.yaml").write_text("context: ambient\n")
        assert _flagged(inner), "an inner opt-out fell through to the outer allowlist"
        # …and the outer repo itself is unaffected.
        assert not _flagged(tmp_path)


class TestHomeStopCondition:
    """harbor#4 M14 (owner decision 2026-08-02) — the walk stops before $HOME.

    One `~/.agents/config.yaml` otherwise supplies `safety.allow` to every
    command run anywhere beneath the home directory. The way it gets written is
    not an attack: project-init run once in the wrong cwd scaffolds `.agents/`
    right there, and M12's "a named FILE is required" does not help, because a
    scaffolder writes named files.
    """

    def test_a_marker_at_home_supplies_nothing(self, tmp_path: Path, monkeypatch):
        home = tmp_path / "home"
        (home / ".agents").mkdir(parents=True)
        (home / ".agents" / "config.yaml").write_text(_PERMISSIVE)
        work = home / "projects" / "thing"
        work.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        assert _flagged(work), "a marker at $HOME switched the deny table off machine-wide"

    def test_the_stop_does_not_swallow_repos_under_home(self, tmp_path: Path, monkeypatch):
        """M28: every repo the operator owns lives UNDER $HOME. A stop that
        swallowed them would un-govern the whole installed base while reading
        as a security fix."""
        home = tmp_path / "home"
        repo = home / "projects" / "thing"
        (repo / ".agents").mkdir(parents=True)
        (repo / ".agents" / "config.yaml").write_text(_PERMISSIVE)
        work = repo / "src"
        work.mkdir()
        monkeypatch.setenv("HOME", str(home))
        assert not _flagged(work), "a real repo under $HOME lost its allowlist"

    def test_a_repo_outside_home_still_walks_up(self, tmp_path: Path, monkeypatch):
        """M29: the stop is a property of the path being walked, not a global
        mode. /opt, a mounted volume and a CI checkout still walk to `/`."""
        (tmp_path / "elsewhere" / ".agents").mkdir(parents=True)
        (tmp_path / "elsewhere" / ".agents" / "config.yaml").write_text(_PERMISSIVE)
        work = tmp_path / "elsewhere" / "src"
        work.mkdir()
        home = tmp_path / "somehome"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        assert not _flagged(work)

    def test_a_symlink_loop_in_the_walk_path_does_not_stand_the_guard_down(
        self, tmp_path: Path, monkeypatch
    ):
        """PR #927 review. `Path.resolve()` raises RuntimeError on a symlink
        loop under Python 3.11 and 3.12 — measured on all three, 3.13 no longer
        does — and both are in this repo's CI matrix. An escaping exception does
        not crash the session, because the guard's outer handler is fail-open;
        it makes the guard STAND DOWN, so a planted loop switches the deny table
        off for that command.

        NOTE this assertion can only go red on 3.11/3.12. On 3.13+ resolve()
        returns the unresolved path and the test passes with or without the fix
        — which is why the fix was verified by running this file under 3.11
        directly, not only by the local suite.
        """
        home = tmp_path / "home"
        home.mkdir()
        (home / "a").symlink_to(home / "b")
        (home / "b").symlink_to(home / "a")
        monkeypatch.setenv("HOME", str(home))
        # The loop goes in the PAYLOAD's cwd, not the process's: a looping path
        # cannot be chdir'd into, so `subprocess(cwd=...)` fails before the guard
        # ever runs. The hook reads its cwd from the payload, which is the
        # interface that actually carries an attacker-influenced path.
        payload = _payload(_DESTRUCTIVE, "bypassPermissions", home / "a")
        assert _run_hook(payload, tmp_path) is not None

    def test_the_boundary_is_before_home_not_at_it(self, tmp_path: Path, monkeypatch):
        """M30: a session whose cwd IS $HOME resolves the same way, and the
        spelling `$HOME/.` must not walk past a stop that compares paths."""
        home = tmp_path / "home"
        (home / ".agents").mkdir(parents=True)
        (home / ".agents" / "config.yaml").write_text(_PERMISSIVE)
        monkeypatch.setenv("HOME", str(home))
        assert _flagged(home)
        assert _flagged(Path(str(home) + "/."))
