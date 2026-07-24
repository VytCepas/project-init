"""BOX-1: the box-profile seam (PI-897, harbor CONTRACTS/box-profile.md v1).

The contract under test: the loader returns None on EVERY failure path with
zero output; a present profile seeds wizard DEFAULTS only (flags win, every
seed changeable); absent ⇒ byte-identical pre-seam behavior (the Enter-only
equivalence test in test_wizard_gateway.py is the other half of that pin).
"""

from __future__ import annotations

from pathlib import Path

import project_init.__main__ as __main__
import project_init.wizard_prompts as _wiz
from project_init.box_profile import BoxProfile, load_box_profile

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "box_profile"


class TestLoader:
    def test_absent_returns_none_silently(self, tmp_path: Path, capsys):
        assert load_box_profile(tmp_path / "missing.toml") is None
        assert capsys.readouterr().out == ""

    def test_present_fixture_parses_with_contract_mapping(self):
        box = load_box_profile(_FIXTURES / "present.toml")
        assert box is not None
        assert box.harnesses == ("claude", "codex", "not-a-surface")
        assert box.mcp_roster == ("context7", "playwright", "not-an-mcp")
        # Contract mapping: org -> the wizard's org profile.
        assert box.profile == "org"

    def test_partial_fixture_defaults_unspecified_fields(self):
        box = load_box_profile(_FIXTURES / "partial.toml")
        assert box is not None
        assert box.harnesses == ("codex",)
        assert box.mcp_roster == ()
        assert box.profile is None

    def test_invalid_fixture_is_treated_as_absent(self, capsys):
        # Unknown schema_version AND a wrong-typed field — either alone suffices.
        assert load_box_profile(_FIXTURES / "invalid.toml") is None
        assert capsys.readouterr().out == ""

    def test_malformed_toml_is_treated_as_absent(self, tmp_path: Path, capsys):
        bad = tmp_path / "box-profile.toml"
        bad.write_text("schema_version = [unclosed")
        assert load_box_profile(bad) is None
        assert capsys.readouterr().out == ""

    def test_unknown_profile_value_is_treated_as_absent(self, tmp_path: Path):
        f = tmp_path / "box-profile.toml"
        f.write_text('schema_version = 1\nprofile = "enterprise"\n')
        assert load_box_profile(f) is None

    def test_unhashable_profile_type_is_treated_as_absent(self, tmp_path: Path, capsys):
        # PR #898 review: `profile = ["org"]` must hit the silent-absent path,
        # not raise TypeError from the membership test before the wizard starts.
        f = tmp_path / "box-profile.toml"
        f.write_text('schema_version = 1\nprofile = ["org"]\n')
        assert load_box_profile(f) is None
        assert capsys.readouterr().out == ""

    def test_env_override_wins(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "elsewhere.toml"
        f.write_text('schema_version = 1\nharnesses = ["codex"]\n')
        monkeypatch.setenv("PROJECT_INIT_BOX_PROFILE", str(f))
        box = load_box_profile()
        assert box is not None
        assert box.harnesses == ("codex",)


def _enter_only(monkeypatch, **kwargs):
    monkeypatch.setattr(_wiz, "_prompt", lambda _label, default="": default)
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: k.get("default", ""))
    monkeypatch.setattr("rich.prompt.IntPrompt.ask", lambda *a, **k: k.get("default", 1))
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: k.get("default", False))
    kwargs.setdefault("profile", None)
    return __main__._gather_inputs_interactive(default_name="demo", no_plugin=False, **kwargs)


def _box(**kw) -> BoxProfile:
    return BoxProfile(source=Path("/box/box-profile.toml"), **kw)


class TestWizardSeeding:
    def test_seeds_agents_mcps_profile_and_prints_one_advisory_line(self, monkeypatch, capsys):
        inputs = _enter_only(
            monkeypatch,
            box_profile=_box(
                harnesses=("claude", "codex", "not-a-surface"),
                mcp_roster=("context7", "not-an-mcp"),
                profile="org",
            ),
        )
        assert inputs.agents == ["claude", "codex"]
        assert [m["id"] for m in inputs.selected_mcps] == ["context7"]
        assert inputs.profile == "org"
        out = capsys.readouterr().out
        assert out.count("Box profile: /box/box-profile.toml") == 1
        assert "agents=claude,codex" in out
        assert "mcps=context7" in out
        assert "profile=org" in out
        # Single tokens: rich wraps the advisory line at 80 columns.
        assert "ignored" in out
        assert "not-a-surface" in out
        assert "not-an-mcp" in out

    def test_claude_is_ensured_even_when_the_box_omits_it(self, monkeypatch):
        inputs = _enter_only(monkeypatch, box_profile=_box(harnesses=("codex",)))
        assert inputs.agents == ["claude", "codex"]

    def test_flags_beat_the_box(self, monkeypatch):
        inputs = _enter_only(
            monkeypatch,
            box_profile=_box(harnesses=("codex",), mcp_roster=("context7-http",), profile="org"),
            cli_agents="claude",
            cli_mcps="context7",
            profile="individual",
        )
        assert inputs.agents == ["claude"]
        assert [m["id"] for m in inputs.selected_mcps] == ["context7"]
        assert inputs.profile == "individual"

    def test_org_profile_seed_hardens_enforcement_in_the_echo(self, monkeypatch, capsys):
        _enter_only(monkeypatch, box_profile=_box(profile="org"))
        out = capsys.readouterr().out
        assert "org / hard" in out  # enforcement row reflects the seeded profile

    def test_no_box_profile_prints_nothing_and_keeps_the_defaults(self, monkeypatch, capsys):
        inputs = _enter_only(monkeypatch, box_profile=None)
        out = capsys.readouterr().out
        assert "Box profile" not in out
        assert inputs.agents == ["claude", "vscode"]
        assert inputs.selected_mcps == []
        assert inputs.profile == "individual"

    def test_opened_groups_keep_box_seeds_as_their_defaults(self, monkeypatch, capsys):
        # PR #898 review: opening a seeded group must present the box seed as
        # the chooser DEFAULT (Enter keeps it), not reset to factory defaults.
        monkeypatch.setattr(_wiz, "_prompt", lambda _label, default="": default)
        monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: k.get("default", ""))
        monkeypatch.setattr("rich.prompt.IntPrompt.ask", lambda *a, **k: k.get("default", 1))
        monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: k.get("default", False))
        monkeypatch.setattr(
            _wiz, "_choose_gateway_interactive", lambda pinned: {"integrations", "overlays"}
        )
        inputs = __main__._gather_inputs_interactive(
            default_name="demo",
            no_plugin=False,
            profile=None,
            box_profile=_box(
                harnesses=("claude", "codex"), mcp_roster=("context7",), profile="org"
            ),
        )
        assert inputs.agents == ["claude", "codex"]
        assert [m["id"] for m in inputs.selected_mcps] == ["context7"]
        assert inputs.profile == "org"

    def test_all_unknown_harnesses_do_not_seed_but_are_reported(self, monkeypatch, capsys):
        inputs = _enter_only(monkeypatch, box_profile=_box(harnesses=("emacs", "vim")))
        assert inputs.agents == ["claude", "vscode"]  # untouched default
        out = capsys.readouterr().out
        assert "nothing (flags pinned)" in out
        assert "ignored" in out
        assert "emacs" in out
        assert "vim" in out
