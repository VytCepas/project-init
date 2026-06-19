"""PI-301 / ADR-014: opt-in branch model (promotion chain) — flag, resolver,
rendered config, and the upgrade backfill for pre-branch-model records."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

from project_init.__main__ import (
    ScaffoldInputs,
    _build_parser,
    _build_variables,
    resolve_branch_chain,
)
from project_init.scaffold import load_preset, scaffold
from tests.helpers import fallback_preset, fallback_variables, make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DAG_HOOK = _REPO_ROOT / ".claude" / "hooks" / "dag_workflow.py"


def _load_dag():
    spec = importlib.util.spec_from_file_location("dag_workflow_under_test", _DAG_HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _inputs(branch_chain: list[str]) -> ScaffoldInputs:
    return ScaffoldInputs(
        project_name="p",
        project_description="d",
        language="python",
        selected_mcps=[],
        owner="",
        license_choice="none",
        devcontainer=False,
        mise=False,
        vscode=False,
        agents=["claude"],
        no_plugin=False,
        profile="individual",
        branch_chain=branch_chain,
    )


def _vars(branch_chain: list[str]) -> dict:
    return _build_variables(load_preset("obsidian-only"), _inputs(branch_chain))


class TestResolveBranchChain:
    def test_empty_and_single_trunk_default_to_main(self):
        assert resolve_branch_chain("") == ["main"]
        assert resolve_branch_chain("single-trunk") == ["main"]

    def test_named_presets(self):
        assert resolve_branch_chain("dev-test-main") == ["dev", "test", "main"]
        assert resolve_branch_chain("dev-uat-preprod-main") == [
            "dev",
            "uat",
            "preprod",
            "main",
        ]

    def test_custom_chain_preserves_order(self):
        assert resolve_branch_chain("dev,stage,main") == ["dev", "stage", "main"]

    def test_custom_chain_dedups(self):
        assert resolve_branch_chain("dev,dev,main") == ["dev", "main"]

    def test_invalid_branch_name_raises(self):
        with pytest.raises(ValueError, match="invalid branch name"):
            resolve_branch_chain("dev, Test Branch, main")


class TestBranchModelFlag:
    def test_default_is_none(self):
        # None lets the resolver default to single-trunk explicitly.
        args = _build_parser().parse_args(["."])
        assert args.branch_model is None

    def test_accepts_value(self):
        args = _build_parser().parse_args([".", "--branch-model", "dev-test-main"])
        assert args.branch_model == "dev-test-main"


class TestBranchModelVariables:
    def test_single_trunk_flags(self):
        v = _vars(["main"])
        assert v["branch_chain"] == "main"
        assert v["base_branch"] == "main"
        assert v["production_branch"] == "main"
        assert v["single_trunk"] == "true"
        assert v["multi_env"] == ""
        assert v["branch_chain_yaml"] == '"main"'

    def test_multi_env_flags(self):
        v = _vars(["dev", "test", "main"])
        assert v["branch_chain"] == "dev,test,main"
        assert v["base_branch"] == "dev"
        assert v["production_branch"] == "main"
        assert v["single_trunk"] == ""
        assert v["multi_env"] == "true"
        assert v["branch_chain_yaml"] == '"dev", "test", "main"'


class TestBranchModelRecorded:
    def test_config_yaml_default_is_single_trunk(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        cfg = (target / ".claude" / "config.yaml").read_text()
        assert 'promotion_chain: ["main"]' in cfg

    def test_config_yaml_records_a_chain(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(
            target,
            load_preset("obsidian-only"),
            make_variables(
                branch_chain="dev,test,main",
                branch_chain_yaml='"dev", "test", "main"',
                base_branch="dev",
                production_branch="main",
                single_trunk="",
                multi_env="true",
            ),
            strict=True,
        )
        cfg = (target / ".claude" / "config.yaml").read_text()
        assert 'promotion_chain: ["dev", "test", "main"]' in cfg


class TestUpgradeBackfill:
    def test_pre_branch_model_record_upgrades_without_crash(self, tmp_path: Path):
        """A record predating branch_model must still re-render — config.yaml.tmpl
        uses {{branch_chain_yaml}} and upgrade renders strictly."""
        from project_init.upgrade import run_upgrade, write_scaffold_record

        target = tmp_path / "p"
        variables = make_variables()
        created = scaffold(target, load_preset("obsidian-only"), variables, strict=True)
        # Simulate a pre-#301 record: drop every branch-model variable.
        drop = ("branch_chain", "base_branch", "production_branch", "single_trunk", "multi_env")
        legacy = {k: v for k, v in variables.items() if not k.startswith(drop)}
        write_scaffold_record(target, "obsidian-only", legacy, created)
        # Strict re-render must succeed (branch vars are backfilled to single-trunk).
        assert run_upgrade(target, apply=False) == 0


class TestBaseBranchReader:
    def test_reads_first_chain_element(self, tmp_path: Path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text('  branch_model:\n    promotion_chain: ["dev", "test", "main"]\n')
        assert _load_dag()._base_branch(cfg) == "dev"

    def test_single_trunk_returns_main(self, tmp_path: Path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text('    promotion_chain: ["main"]\n')
        assert _load_dag()._base_branch(cfg) == "main"

    def test_missing_config_returns_none(self, tmp_path: Path):
        assert _load_dag()._base_branch(tmp_path / "absent.yaml") is None

    def test_no_chain_returns_none(self, tmp_path: Path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("project:\n  name: x\n")
        assert _load_dag()._base_branch(cfg) is None

    def test_reads_unquoted_chain(self, tmp_path: Path):
        # config.yaml is hand-editable; tolerate unquoted lists (ADR-014 prose).
        cfg = tmp_path / "config.yaml"
        cfg.write_text("    promotion_chain: [dev, test, main]\n")
        assert _load_dag()._base_branch(cfg) == "dev"


class TestBaseBranchWiring:
    """The base-branch wiring must survive scaffolding into a real project tree
    (repo rule: templates/ changes need a scaffold-into-tempdir test)."""

    def _scaffold(self, tmp_path: Path) -> Path:
        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        return target

    def test_scaffolded_gh_host_defines_base_branch(self, tmp_path: Path):
        target = self._scaffold(tmp_path)
        assert "base_branch()" in (target / ".claude/scripts/gh_host.sh").read_text()

    def test_scaffolded_start_issue_targets_base(self, tmp_path: Path):
        target = self._scaffold(tmp_path)
        s = (target / ".claude/scripts/start_issue.sh").read_text()
        assert "gh_host.sh" in s
        assert "--base" in s

    def test_scaffolded_dag_workflow_has_base_reader(self, tmp_path: Path):
        target = self._scaffold(tmp_path)
        assert "_base_branch" in (target / ".claude/hooks/dag_workflow.py").read_text()


class TestPromotionChain:
    def test_quoted(self, tmp_path: Path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text('    promotion_chain: ["dev", "test", "main"]\n')
        assert _load_dag()._promotion_chain(cfg) == ["dev", "test", "main"]

    def test_unquoted(self, tmp_path: Path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text("    promotion_chain: [dev, test, main]\n")
        assert _load_dag()._promotion_chain(cfg) == ["dev", "test", "main"]

    def test_single(self, tmp_path: Path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text('    promotion_chain: ["main"]\n')
        assert _load_dag()._promotion_chain(cfg) == ["main"]

    def test_missing(self, tmp_path: Path):
        assert _load_dag()._promotion_chain(tmp_path / "absent.yaml") == []


class TestPromoteEnvValidation:
    def _dag(self, monkeypatch, chain: list[str]):
        dag = _load_dag()
        monkeypatch.setattr(dag, "_promotion_chain", lambda *a, **k: chain)
        return dag

    def test_single_trunk_refused(self, monkeypatch):
        assert self._dag(monkeypatch, ["main"]).cmd_promote_env("main") == 1

    def test_no_target_refused(self, monkeypatch):
        assert self._dag(monkeypatch, ["dev", "test", "main"]).cmd_promote_env(None) == 1

    def test_unknown_target_refused(self, monkeypatch):
        assert self._dag(monkeypatch, ["dev", "test", "main"]).cmd_promote_env("nope") == 1

    def test_base_target_refused(self, monkeypatch):
        assert self._dag(monkeypatch, ["dev", "test", "main"]).cmd_promote_env("dev") == 1

    def test_aborts_on_checkout_failure(self, monkeypatch):
        # A failed checkout must abort before merge/push (Codex P1): otherwise the
        # ff-merge runs on the wrong branch and a stale ref gets pushed as success.
        dag = self._dag(monkeypatch, ["dev", "test", "main"])
        monkeypatch.setattr(dag, "_current_branch", lambda: "dev")
        calls: list[str] = []

        def fake_git(args: list[str]) -> tuple[int, str]:
            calls.append(args[0])
            if args[0] == "checkout" and "-B" in args:
                return (1, "error: local changes would be overwritten")
            return (0, "")

        monkeypatch.setattr(dag, "_git", fake_git)
        assert dag.cmd_promote_env("test") == 1
        assert "merge" not in calls
        assert "push" not in calls

    def test_push_uses_no_verify(self, monkeypatch):
        # The promotion push must skip the local pre-push hook (bare env-branch
        # names fail its type-prefix rule); server-side rulesets still govern.
        dag = self._dag(monkeypatch, ["dev", "test", "main"])
        monkeypatch.setattr(dag, "_current_branch", lambda: "dev")
        pushes: list[list[str]] = []

        def fake_git(args: list[str]) -> tuple[int, str]:
            if args[0] == "push":
                pushes.append(args)
            return (0, "")

        monkeypatch.setattr(dag, "_git", fake_git)
        assert dag.cmd_promote_env("test") == 0
        assert pushes and "--no-verify" in pushes[0]


class TestPromoteEnvFastForward:
    def test_promotes_by_fast_forward(self, tmp_path: Path, monkeypatch):
        remote = tmp_path / "remote.git"
        work = tmp_path / "work"
        subprocess.run(
            ["git", "init", "--bare", "-b", "main", str(remote)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "clone", str(remote), str(work)], check=True, capture_output=True
        )

        def g(*args: str) -> None:
            subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)

        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        (work / "a.txt").write_text("1")
        g("add", "-A")
        g("commit", "-m", "init")
        g("branch", "dev")
        g("branch", "test")
        g("push", "origin", "main", "dev", "test")
        g("checkout", "dev")
        (work / "b.txt").write_text("2")
        g("add", "-A")
        g("commit", "-m", "feat")
        g("push", "origin", "dev")
        (work / ".claude").mkdir()
        (work / ".claude" / "config.yaml").write_text(
            '    promotion_chain: ["dev", "test", "main"]\n'
        )
        monkeypatch.chdir(work)
        assert _load_dag().cmd_promote_env("test") == 0

        def sha(ref: str) -> str:
            return subprocess.run(
                ["git", "-C", str(work), "rev-parse", ref],
                capture_output=True, text=True,
            ).stdout.strip()

        assert sha("origin/test") == sha("origin/dev")


class TestPromoteEnvShim:
    def test_shim_scaffolded(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        shim = (target / ".claude/scripts/promote_env.sh").read_text()
        assert "dag_workflow.py" in shim
        assert "promote-env" in shim


class TestSetupEnvBranches:
    SCRIPT = _REPO_ROOT / "templates/base/dot_claude/scripts/setup_env_branches.sh"
    GH_HOST = _REPO_ROOT / "templates/base/dot_claude/scripts/gh_host.sh"

    def _chain(self, tmp_path: Path, line: str) -> str:
        cfg = tmp_path / ".claude" / "config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(line)
        out = subprocess.run(
            ["bash", "-c", f'cd "{tmp_path}" && . "{self.GH_HOST}" && promotion_chain'],
            capture_output=True, text=True,
        )
        return out.stdout.strip()

    def test_promotion_chain_quoted(self, tmp_path: Path):
        assert self._chain(tmp_path, '    promotion_chain: ["dev", "test", "main"]\n') == "dev test main"

    def test_promotion_chain_unquoted(self, tmp_path: Path):
        assert self._chain(tmp_path, "    promotion_chain: [dev, test, main]\n") == "dev test main"

    def test_promotion_chain_single(self, tmp_path: Path):
        assert self._chain(tmp_path, '    promotion_chain: ["main"]\n') == "main"

    def test_single_trunk_noop_guard(self):
        assert "-lt 2" in self.SCRIPT.read_text()

    def test_sets_squash_only_policy(self):
        s = self.SCRIPT.read_text()
        assert "allow_squash_merge=true" in s
        assert "allow_merge_commit=false" in s
        assert "delete_branch_on_merge=true" in s

    def test_creates_branches_via_refs_api(self):
        assert "git/refs" in self.SCRIPT.read_text()

    def test_org_ruleset_gated_with_empty_bypass(self):
        s = self.SCRIPT.read_text()
        assert 'PROFILE" = "org"' in s
        assert '"bypass_actors": []' in s

    def test_governance_consistent_with_setup_github(self):
        # Mirror setup_github.sh's baseline: secret-scan required, linear history,
        # conversation resolution (Copilot review on #308).
        s = self.SCRIPT.read_text()
        assert "CI / Secret scan (gitleaks)" in s
        assert "required_conversation_resolution" in s
        assert '"type": "required_linear_history"' in s

    def test_scaffolded_and_executable(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        script = target / ".claude/scripts/setup_env_branches.sh"
        assert script.is_file()
        assert script.stat().st_mode & 0o111


class TestCIRetargeting:
    def _scaffold(self, tmp_path: Path, **overrides: str) -> Path:
        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(**overrides), strict=True)
        return target

    def test_validate_pr_default_targets_main(self, tmp_path: Path):
        vp = (self._scaffold(tmp_path) / ".github/workflows/validate-pr.yml").read_text()
        assert "branches: [main]" in vp

    def test_validate_pr_targets_base_for_env(self, tmp_path: Path):
        vp = (self._scaffold(tmp_path, base_branch="dev") / ".github/workflows/validate-pr.yml").read_text()
        assert "branches: [dev]" in vp

    def test_ci_targets_base_for_env(self, tmp_path: Path):
        ci = (self._scaffold(tmp_path, base_branch="dev") / ".github/workflows/ci.yml").read_text()
        assert "branches: [dev]" in ci
        assert "branches: [main]" not in ci


class TestBranchModelDocs:
    def test_project_init_md_documents_branch_model(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        doc = (target / ".claude/project-init.md").read_text()
        assert "Branch model (ADR-014)" in doc
        assert "promote_env.sh" in doc
        assert "setup_env_branches.sh" in doc

    def test_github_workflow_skill_mentions_base_branch(self):
        skill = (
            _REPO_ROOT
            / "templates/fallback/dot_claude/skills/github_workflow/SKILL.md"
        ).read_text()
        assert "Branch model (ADR-014)" in skill
        assert "base branch" in skill
        assert "promote_env.sh" in skill
        assert "project.branch_model.promotion_chain" in skill
