"""#271: benchmark collection harness — the testable (no-agent) core.

The agent-driving half (`claude -p`) is manual-only and not exercised here; the
parsing, record schema, task specs, and target setup are pure/deterministic and
fully covered. This is dev tooling under tools/ — imported, never scaffolded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.benchmark import harness, transcript
from tools.benchmark.record import RunRecord, read_records, write_records


def _write_transcript(path: Path) -> None:
    """A small but representative Claude Code transcript."""
    entries = [
        {"type": "user", "timestamp": "2026-06-23T10:00:00Z", "version": "2.1.181",
         "message": {"content": "hi"}},
        {
            "type": "assistant",
            "timestamp": "2026-06-23T10:00:05Z",
            "version": "2.1.181",
            "message": {
                "model": "claude-opus-4-8",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 800,
                    "cache_creation_input_tokens": 200,
                },
                "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
                    {"type": "tool_use", "id": "t2", "name": "Read", "input": {}},
                ],
            },
        },
        {
            "type": "assistant",
            "timestamp": "2026-06-23T10:00:09Z",
            "version": "2.1.181",
            "message": {
                "model": "claude-opus-4-8",
                "usage": {"input_tokens": 20, "output_tokens": 10,
                          "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                "content": [{"type": "text", "text": "done"}],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class TestTranscriptParse:
    def test_aggregates(self, tmp_path: Path):
        tx = tmp_path / "t.jsonl"
        _write_transcript(tx)
        agg = transcript.parse(tx)
        assert agg.input_tokens == 120
        assert agg.output_tokens == 60
        assert agg.cache_read_tokens == 800
        assert agg.cache_creation_tokens == 200
        assert agg.total_tokens == 1180
        assert agg.tool_calls == 2
        assert agg.turns == 2  # two assistant messages
        assert agg.models == ["claude-opus-4-8"]
        assert agg.claude_version == "2.1.181"
        assert agg.first_ts == "2026-06-23T10:00:00Z"
        assert agg.last_ts == "2026-06-23T10:00:09Z"

    def test_tolerates_garbage_lines(self, tmp_path: Path):
        tx = tmp_path / "t.jsonl"
        tx.write_text('not json\n{"type":"assistant","message":{"model":"m","usage":{}}}\n\n')
        agg = transcript.parse(tx)
        assert agg.turns == 1  # the one valid assistant line counted; garbage skipped


class TestRecord:
    def test_jsonl_round_trip(self, tmp_path: Path):
        rec = RunRecord(
            task="feat", target="bare", run_index=0, model="claude-opus-4-8",
            claude_version="2.1.181", session_id="s1", transcript_path="/t.jsonl",
            input_tokens=120, output_tokens=60, cache_read_tokens=800,
            cache_creation_tokens=200, total_tokens=1180, tool_calls=2, turns=2,
            wall_clock_s=9.0, first_ts="a", last_ts="b",
        )
        out = tmp_path / "records.jsonl"
        write_records([rec], out)
        loaded = read_records(out)
        assert len(loaded) == 1 and loaded[0] == rec
        # Placeholder fields default to None — owned by #272/#273.
        assert loaded[0].cost_usd is None
        assert loaded[0].success is None

    def test_from_dict_tolerant(self):
        # Unknown keys ignored, missing optional keys default — forward/backward compat.
        rec = RunRecord.from_dict({
            "task": "qa", "target": "bare", "run_index": 1, "model": "m",
            "claude_version": "v", "session_id": "", "transcript_path": "/t",
            "input_tokens": 1, "output_tokens": 2, "cache_read_tokens": 3,
            "cache_creation_tokens": 4, "total_tokens": 10, "tool_calls": 0, "turns": 1,
            "wall_clock_s": None, "first_ts": None, "last_ts": None,
            "future_field_from_a_later_issue": 123,  # ignored
        })
        assert rec.task == "qa" and rec.cost_usd is None

    def test_read_missing_file_is_empty(self, tmp_path: Path):
        assert read_records(tmp_path / "nope.jsonl") == []


class TestBuildRecord:
    def test_assembles_from_transcript(self, tmp_path: Path):
        tx = tmp_path / "t.jsonl"
        _write_transcript(tx)
        rec = harness.build_record(
            harness.RunContext(
                task="feat", target="obsidian-only", run_index=2,
                model="claude-opus-4-8", session_id="sess-1", wall_clock_s=12.3,
            ),
            tx,
        )
        assert rec.task == "feat" and rec.target == "obsidian-only" and rec.run_index == 2
        assert rec.total_tokens == 1180 and rec.tool_calls == 2 and rec.turns == 2
        assert rec.wall_clock_s == 12.3 and rec.claude_version == "2.1.181"
        assert rec.cost_usd is None and rec.success is None  # later issues

    def test_empty_model_falls_back_to_transcript(self, tmp_path: Path):
        """record-from defaults --model to '' so the transcript's own model wins
        instead of being overwritten by a CLI default (Codex review)."""
        tx = tmp_path / "t.jsonl"
        _write_transcript(tx)
        rec = harness.build_record(
            harness.RunContext(task="qa", target="bare", run_index=0, model=""),
            tx,
        )
        assert rec.model == "claude-opus-4-8"  # from the transcript, not a default


class TestTaskSpecs:
    @pytest.mark.parametrize("task_id", ["feat", "fix", "qa", "noop"])
    def test_all_tasks_load_with_prompt(self, task_id: str):
        spec = harness.load_task(task_id)
        assert spec["id"] == task_id
        assert spec["prompt"].strip()
        assert "check" in spec  # the #273 contract is authored

    def test_load_all(self):
        tasks = harness.load_all_tasks()
        assert set(tasks) == {"feat", "fix", "qa", "noop"}

    def test_unknown_task_raises(self):
        with pytest.raises(FileNotFoundError):
            harness.load_task("does-not-exist")


class TestProjectSlug:
    def test_slug_rule(self):
        assert harness.project_slug("/home/u/p_x.y") == "-home-u-p-x-y"

    def test_transcript_path_for(self, tmp_path: Path):
        p = harness.transcript_path_for(tmp_path / "cfg", Path("/proj/x"), "sess-9")
        assert p.name == "sess-9.jsonl"
        assert "projects" in p.parts


class TestTargetSetup:
    def test_bare_has_no_claude(self, tmp_path: Path):
        target = harness.setup_bare_target(tmp_path / "bare")
        assert (target / "pyproject.toml").is_file()
        assert not (target / ".claude").exists()

    def test_bare_target_has_pytest_for_checks(self, tmp_path: Path):
        """The deterministic check runner must be available on the bare arm too,
        so the comparison isolates the scaffold's contribution (Codex review)."""
        target = harness.setup_bare_target(tmp_path / "bare")
        assert "pytest" in (target / "pyproject.toml").read_text()

    def test_scaffolded_has_claude(self, tmp_path: Path):
        target = harness.setup_scaffolded_target(tmp_path / "scaf", "obsidian-only")
        assert (target / ".claude").is_dir()
        assert (target / ".claude" / "config.yaml").is_file()

    def test_fix_task_seeds_failing_fixture(self, tmp_path: Path):
        """The fix task must arrive with a real failing+passing baseline, not an
        empty project (Codex review P1)."""
        target = harness.prepare_target(
            tmp_path / "fix", "bare", harness.load_task("fix"), model="m"
        )
        calc = target / "calc.py"
        test = target / "test_calc.py"
        assert calc.is_file() and test.is_file()
        # No stray leading blank line from the TOML triple-quote.
        assert calc.read_text().startswith("def divide")
        assert "test_divide_by_zero" in test.read_text()

    def test_prepare_target_is_fresh_per_run(self, tmp_path: Path):
        """A prior run's writes must not leak into the next (Codex review P1)."""
        task = harness.load_task("feat")
        first = harness.prepare_target(tmp_path / "r0", "bare", task, model="m")
        (first / "leftover.py").write_text("# from a previous run\n")
        # A different run dir is a clean baseline.
        second = harness.prepare_target(tmp_path / "r1", "bare", task, model="m")
        assert not (second / "leftover.py").exists()

    def test_seed_task_noop_without_seed_files(self, tmp_path: Path):
        target = tmp_path / "t"
        target.mkdir()
        harness.seed_task(target, harness.load_task("feat"))  # feat has no seeds
        assert list(target.iterdir()) == []


class TestUnpricedWarning:
    def test_record_from_warns_on_unpriced_model(self, tmp_path: Path, capsys):
        """Both CLI paths must warn (not silently emit null cost) — Copilot review."""
        tx = tmp_path / "t.jsonl"
        tx.write_text(json.dumps(
            {"type": "assistant", "message": {"model": "gpt-4o", "usage": {}}}
        ) + "\n")
        rc = harness.main([
            "record-from", "--task", "qa", "--target", "bare",
            "--transcript", str(tx), "--out", str(tmp_path / "r.jsonl"),
        ])
        assert rc == 0
        assert "no price row for model 'gpt-4o'" in capsys.readouterr().err


class TestRunTaskGuard:
    def test_run_task_requires_claude_cli(self, tmp_path: Path, monkeypatch):
        # Deterministic regardless of whether claude is installed locally.
        monkeypatch.setattr(harness.shutil, "which", lambda _: None)
        with pytest.raises(RuntimeError, match="claude.*CLI"):
            harness.run_task(tmp_path, {"prompt": "x"}, model="m", config_dir=tmp_path)


class TestAuth:
    """Subscription-or-API-key auth for the manual `run` path (no agent driven)."""

    def test_default_config_dir_honors_env(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        assert harness.default_config_dir() == tmp_path / "cfg"
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        assert harness.default_config_dir() == Path.home() / ".claude"

    def test_seed_credentials_copies_subscription_token(self, tmp_path: Path):
        source = tmp_path / "real"
        source.mkdir()
        (source / ".credentials.json").write_text('{"token": "x"}', encoding="utf-8")
        config_dir = tmp_path / "iso"
        assert harness.seed_credentials(config_dir, source=source) is True
        dest = config_dir / ".credentials.json"
        assert dest.read_text() == '{"token": "x"}'
        assert dest.stat().st_mode & 0o777 == 0o600  # never widen token perms

    def test_seed_credentials_absent_returns_false(self, tmp_path: Path):
        assert harness.seed_credentials(tmp_path / "iso", source=tmp_path / "empty") is False

    def test_auth_available_prefers_api_key(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        assert harness.auth_available(tmp_path) is True  # no creds file needed

    def test_auth_available_via_seeded_creds(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert harness.auth_available(tmp_path) is False
        (tmp_path / ".credentials.json").write_text("{}", encoding="utf-8")
        assert harness.auth_available(tmp_path) is True

    def test_run_aborts_clearly_when_unauthenticated(self, tmp_path: Path, monkeypatch, capsys):
        """The silent per-task skip is replaced by an upfront precondition error."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(harness.shutil, "which", lambda _: "/usr/bin/claude")
        # Point cred discovery at an empty dir so no subscription token is found.
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty"))
        rc = harness.main(["run", "--task", "noop", "--repeats", "1"])
        assert rc == 1
        assert "not authenticated" in capsys.readouterr().err
