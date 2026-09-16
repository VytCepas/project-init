"""PI-965: a systematic fuzz over DENY_RULES x wrapping shape.

The prose exemption was shipped twice on a hand-written corpus, and both times
the corpus read clean while being incomplete — the failure mode is not thinking
of a category, which no amount of re-reading the same list fixes. This crosses
EVERY deny rule with every wrapping shape and separates the two error classes:

    fail-open       a shape that runs or stages the payload, allowed  -> REGRESSION
    false positive  an inert shape, asked                             -> friction

Only the fail-open count is asserted. The false-positive count is reported, not
gated: it is a friction measurement, and a gate on it would be a gate that fails
whenever someone legitimately tightens a rule.

Two things keep this honest, and they matter more than the numbers:

1. Every payload is checked to fire BARE. A payload that no longer matches its
   rule would otherwise sit in the corpus contributing a silent pass forever.
2. `test_the_fuzz_can_actually_see_a_fail_open` plants a hole and requires the
   fuzz to find it. Without that, a harness that had quietly stopped working
   would report the same clean result as one that works.

The `kind` of each shape below was MEASURED, not reasoned — each was run with a
benign `touch` payload and classified by what actually happened. Six entries
were wrong when first written from reasoning alone: `>`/`>>`/`tee` stage rather
than execute, and `env echo` only prints.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

_GUARD = (
    Path(__file__).resolve().parents[2]
    / "templates"
    / "base"
    / "dot_agents"
    / "hooks"
    / "prod_guard.py"
)

PIPE = "|"
REDIR = ">"
SH = "sh"

#: (id, template, kind) — kind is one of executes / stages / inert, measured.
SHAPES: list[tuple[str, str, str]] = [
    ("echo_dq", 'echo "{P}"', "inert"),
    ("echo_sq", "echo '{P}'", "inert"),
    ("printf", "printf '%s' '{P}'", "inert"),
    ("echo_abs", '/bin/echo "{P}"', "inert"),
    ("grep_pattern", "grep -rn '{P}' docs/", "inert"),
    ("grep_count", "grep -c '{P}' runbook.md", "inert"),
    ("cat_pipe_grep", "cat runbook.md " + PIPE + " grep -c '{P}'", "inert"),
    ("commit_msg", 'git commit -m "{P}"', "inert"),
    ("commit_msg_sq", "git commit -m '{P}'", "inert"),
    ("tag_msg", 'git tag -am "{P}" v1', "inert"),
    ("nested_quotes", "echo 'a \"{P}\" b'", "inert"),
    ("rg_pattern", "rg '{P}' .", "inert"),
    ("ack_pattern", "ack '{P}'", "inert"),
    ("env_prefix", 'env echo "{P}"', "inert"),
    ("pipe_sh", 'echo "{P}" ' + PIPE + " " + SH, "executes"),
    ("pipe_bash", 'echo "{P}" ' + PIPE + " bash", "executes"),
    ("pipe_sh_nospace", 'echo "{P}"' + PIPE + SH, "executes"),
    ("pipe_abs_sh", 'echo "{P}" ' + PIPE + " /bin/" + SH, "executes"),
    ("printf_pipe_sh", "printf '%s' '{P}' " + PIPE + " " + SH, "executes"),
    ("grep_pipe_sh", "grep -h '{P}' script.txt " + PIPE + " " + SH, "executes"),
    ("pipe_xargs", 'echo "{P}" ' + PIPE + " xargs -0 " + SH + " -c", "executes"),
    ("cmdsub_dollar", 'echo "$({P})"', "executes"),
    ("cmdsub_backtick", 'echo "`{P}`"', "executes"),
    ("sh_c", SH + ' -c "{P}"', "executes"),
    ("bash_c", "bash -c '{P}'", "executes"),
    ("eval", 'eval "{P}"', "executes"),
    ("command_sh_c", "command " + SH + ' -c "{P}"', "executes"),
    ("dollar_shell", '$SHELL -c "{P}"', "executes"),
    ("heredoc", SH + " <<EOF\n{P}\nEOF", "executes"),
    ("awk_system", "awk 'BEGIN{{system(\"{P}\")}}'", "executes"),
    ("python_c", "python3 -c \"import os; os.system('{P}')\"", "executes"),
    ("nice_sh", "nice " + SH + ' -c "{P}"', "executes"),
    ("and_then", 'echo "safe" && {P}', "executes"),
    ("semicolon", 'echo "safe"; {P}', "executes"),
    ("before_prose", '{P}; echo "done"', "executes"),
    ("newline", 'echo "safe"\n{P}', "executes"),
    ("backslash_cont", 'echo "safe" \\\n && {P}', "executes"),
    ("after_term_pipe", 'echo "safe"; echo "{P}" ' + PIPE + " " + SH, "executes"),
    ("redirect", 'echo "{P}" ' + REDIR + " run." + SH, "stages"),
    ("append", 'echo "{P}" ' + REDIR + REDIR + " run." + SH, "stages"),
    ("tee", 'echo "{P}" ' + PIPE + " tee run." + SH, "stages"),
]

#: One representative destructive command per DENY_RULES entry. Quote characters
#: are avoided so a payload embeds in single- and double-quoted shapes alike.
PAYLOADS: list[tuple[str, str]] = [
    ("terraform_destroy", "terraform destroy"),
    ("kubectl_delete", "kubectl delete namespace prod"),
    ("helm_uninstall", "helm uninstall myrelease"),
    ("aws_terminate", "aws ec2 terminate-instances --instance-ids i-123"),
    ("aws_s3_rb", "aws s3 rb s3://mybucket"),
    ("gcloud_delete", "gcloud compute instances delete vm-1"),
    ("gsutil_rm_r", "gsutil rm -r gs://mybucket"),
    ("gcloud_storage_rm", "gcloud storage rm --recursive gs://mybucket"),
    ("bq_rm", "bq rm -t proj:ds.table"),
    ("bq_truncate", "bq truncate proj:ds.table"),
    ("bq_load_replace", "bq load --replace ds.table gs://f.csv"),
    ("bq_query_replace", "bq query --destination_table ds.t --replace select 1"),
    ("az_delete", "az group delete --name rg1"),
    ("dbt_full_refresh", "dbt run --full-refresh --target prod"),
    ("dbt_write_prod", "dbt build --target prod"),
    ("gcloud_iam_grant", "gcloud projects add-iam-policy-binding p --role=roles/owner"),
    ("gcloud_iam_remove", "gcloud projects remove-iam-policy-binding p --member=m --role=r"),
    ("gcloud_set_iam", "gcloud projects set-iam-policy p policy.json"),
    ("gcloud_sa_key", "gcloud iam service-accounts keys create k.json --iam-account=a@b.c"),
    ("gsutil_iam_ch", "gsutil iam ch user:x:admin gs://mybucket"),
    ("bq_set_iam", "bq set-iam-policy ds.t policy.json"),
    ("bq_update_source", "bq update --source s.json ds"),
    ("sql_drop", "drop table users"),
    ("sql_truncate", "truncate table users"),
    ("sql_delete_from", "delete from users where id=1"),
    ("sql_merge", "merge into target t using src s on t.id=s.id when matched then delete"),
    ("rm_rf_outside", "rm -rf /etc/someplace"),
    (
        "gtm_publish",
        "curl -X POST https://tagmanager.googleapis.com/tagmanager/v2"
        "/accounts/1/containers/2/versions/3:publish",
    ),
    ("gh_repo_delete", "gh repo delete owner/repo"),
    ("docker_prune", "docker system prune"),
]


def _load_guard():
    spec = importlib.util.spec_from_file_location("prod_guard_fuzz", _GUARD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def guard():
    return _load_guard()


def _verdict(mod, command: str) -> str:
    """The guard's decision, through the stdin entrypoint the hook really uses."""
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    buf = io.StringIO()
    original_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(json.dumps(payload))
        with contextlib.redirect_stdout(buf), contextlib.suppress(SystemExit):
            mod.main()
    finally:
        sys.stdin = original_stdin
    raw = buf.getvalue().strip()
    if not raw:
        return "allow"
    return json.loads(raw)["hookSpecificOutput"]["permissionDecision"]


def _fail_opens(mod) -> list[str]:
    found = []
    for _sid, template, kind in SHAPES:
        if kind == "inert":
            continue
        for _pid, payload in PAYLOADS:
            command = template.format(P=payload)
            if _verdict(mod, command) == "allow":
                found.append(command)
    return found


class TestCorpusIntegrity:
    """A corpus that has stopped exercising the guard must say so."""

    @pytest.mark.parametrize(("pid", "payload"), PAYLOADS, ids=[p[0] for p in PAYLOADS])
    def test_every_payload_fires_bare(self, guard, pid: str, payload: str):
        assert _verdict(guard, payload) != "allow", (
            f"{pid} no longer trips the guard on its own, so every wrapped case "
            "built from it is a silent pass. Fix the payload or drop the rule."
        )

    def test_one_payload_per_deny_rule(self, guard):
        assert len(PAYLOADS) == len(guard.DENY_RULES), (
            f"{len(guard.DENY_RULES)} deny rules but {len(PAYLOADS)} payloads — "
            "a rule added without a payload is a rule this fuzz never exercises."
        )


class TestNoFailOpens:
    def test_no_shape_talks_the_guard_out_of_a_real_verb(self, guard):
        leaked = _fail_opens(guard)
        assert not leaked, "prose exemption allowed a live destructive command:\n" + "\n".join(
            f"  {c!r}" for c in leaked[:20]
        )

    def test_the_fuzz_can_actually_see_a_fail_open(self, guard, monkeypatch):
        """Plant a hole and require the fuzz to find it.

        Without this, a harness that had silently stopped working would report
        exactly the same clean result as one that works — which is the whole
        reason the earlier hand-written passes were not evidence.
        """
        if not hasattr(guard, "_flows_onward"):
            pytest.skip("no prose exemption in this build — nothing to hole")
        monkeypatch.setattr(guard, "_flows_onward", lambda *a, **k: False)
        assert _fail_opens(guard), (
            "disabling the pipe/redirect check produced no fail-opens, so this "
            "fuzz is not capable of detecting one and its clean runs mean nothing"
        )


def test_report_false_positive_rate(guard, capsys):
    """Reported, never gated — this is friction, not a regression."""
    asked = [
        template.format(P=payload)
        for _sid, template, kind in SHAPES
        if kind == "inert"
        for _pid, payload in PAYLOADS
    ]
    total = len(asked)
    hits = sum(1 for command in asked if _verdict(guard, command) != "allow")
    with capsys.disabled():
        print(f"\n[PI-965] inert cases asked: {hits}/{total}")
    assert total  # the population must not silently empty out
