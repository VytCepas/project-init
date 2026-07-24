"""Deploy identity capture (PI-899, harbor J1): app/region/health_url.

The contract: the descriptor deploy block carries a real, captured identity —
app (default: the project slug, fixing the raw-project_name schema-pattern
hole), region (default: us-central1, the old static literal), health_url
(default: empty = no probe). The orchestrator's doctor/orphans/cloud verbs
dispatch on app+region and probe health_url only when non-empty, so defaults
must reproduce the pre-capture rendering byte-for-byte.
"""

from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest
import yaml

import project_init.__main__ as __main__
import project_init.wizard_prompts as _wiz
from project_init.__main__ import ScaffoldInputs, _build_variables
from project_init.scaffold import load_preset, scaffold
from project_init.schema import load_descriptor_schema
from project_init.variables import deploy_identity_error


def _service_config(tmp_path: Path, **identity) -> dict:
    inputs = ScaffoldInputs(
        project_name="conformance-service",
        project_description="deploy identity conformance",
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
        delivery="service",
        deploy="cloud-run",
        **identity,
    )
    preset = load_preset("core")
    variables = _build_variables(preset, inputs)
    scaffold(tmp_path, preset, variables, strict=True)
    return yaml.safe_load((tmp_path / ".agents" / "config.yaml").read_text(encoding="utf-8"))


class TestRendering:
    def test_defaults_reproduce_the_pre_capture_block(self, tmp_path: Path):
        """No identity given: app = slug, region = us-central1, health_url = ''
        — exactly what the static pre-capture template rendered (and what the
        orchestrator's golden fixture carries)."""
        deploy = _service_config(tmp_path)["deploy"]
        assert deploy["target"] == "cloud-run"
        assert deploy["app"] == "conformance-service"
        assert deploy["region"] == "us-central1"
        assert deploy["health_url"] == ""

    def test_captured_values_render_and_validate(self, tmp_path: Path):
        deploy = _service_config(
            tmp_path,
            deploy_app="billing-api",
            deploy_region="europe-west1",
            deploy_health_url="https://billing.example.com/healthz",
        )["deploy"]
        assert deploy["app"] == "billing-api"
        assert deploy["region"] == "europe-west1"
        assert deploy["health_url"] == "https://billing.example.com/healthz"
        config = yaml.safe_load((tmp_path / ".agents" / "config.yaml").read_text(encoding="utf-8"))
        jsonschema.validate(config, load_descriptor_schema())

    def test_app_default_is_the_slug_not_the_raw_name(self, tmp_path: Path):
        """A project name with spaces used to render into deploy.app verbatim,
        violating the schema's own ^[A-Za-z0-9._-]+$ pattern — the slug default
        closes that latent hole."""
        inputs = ScaffoldInputs(
            project_name="My Cool Service",
            project_description="latent-bug regression",
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
            delivery="service",
            deploy="cloud-run",
        )
        variables = _build_variables(load_preset("core"), inputs)
        assert variables["deploy_app"] == "my-cool-service"

    def test_deploy_workflow_stub_carries_the_region(self, tmp_path: Path):
        _service_config(tmp_path, deploy_region="europe-west1")
        workflow = (tmp_path / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
        assert '--region "europe-west1"' in workflow
        assert "$REGION" not in workflow


class TestValidation:
    @pytest.mark.parametrize("bad", ["has space", "sla/sh", "q!uote"])
    def test_schema_pattern_rejected(self, bad: str):
        assert deploy_identity_error("app", bad) is not None

    @pytest.mark.parametrize("good", ["", "billing-api", "eu.west_1", "A1"])
    def test_schema_pattern_accepted(self, good: str):
        assert deploy_identity_error("app", good) is None

    def test_non_interactive_bad_app_aborts_before_writes(self, tmp_path: Path, capsys):
        with pytest.raises(SystemExit):
            __main__.main(
                [
                    str(tmp_path / "proj"),
                    "--non-interactive",
                    "--preset",
                    "core",
                    "--name",
                    "proj",
                    "--description",
                    "d",
                    "--language",
                    "python",
                    "--delivery",
                    "service",
                    "--deploy",
                    "cloud-run",
                    "--deploy-app",
                    "has space",
                    "--agents",
                    "claude",
                ]
            )
        assert not (tmp_path / "proj" / ".agents").exists()
        assert "deploy-app" in capsys.readouterr().err


class TestWizardCapture:
    def test_opened_delivery_group_captures_the_identity(self, monkeypatch):
        """Service + cloud-run inside the opened delivery group asks for the
        three identity values (schema-validated, re-asking on a bad app)."""
        labels: list[str] = []
        answers = iter(
            [
                "proj",
                "desc",
                "python",
                "3.11",
                "bad app!",
                "billing-api",
                "europe-west1",
                "https://x/healthz",
            ]
        )

        def fake_prompt(label, *a, **k):
            labels.append(str(label))
            return next(answers)

        monkeypatch.setattr(_wiz, "_prompt", fake_prompt)
        monkeypatch.setattr(_wiz, "_choose_gateway_interactive", lambda pinned: {"delivery"})
        monkeypatch.setattr(_wiz, "_choose_delivery_interactive", lambda language: "service")
        monkeypatch.setattr(_wiz, "_choose_deploy_interactive", lambda: "cloud-run")
        monkeypatch.setattr(_wiz, "_choose_iac_interactive", lambda: "none")
        monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)
        inputs = __main__._gather_inputs_interactive(
            default_name="proj", no_plugin=False, profile="individual"
        )
        assert inputs.deploy_app == "billing-api"  # re-asked after "bad app!"
        assert inputs.deploy_region == "europe-west1"
        assert inputs.deploy_health_url == "https://x/healthz"
        assert any("Deploy app name" in label for label in labels)

    def test_no_deploy_means_no_identity_prompts(self, monkeypatch):
        labels: list[str] = []
        answers = iter(["proj", "desc", "go", "", "none"])

        def fake_prompt(label, *a, **k):
            labels.append(str(label))
            return next(answers)

        monkeypatch.setattr(_wiz, "_prompt", fake_prompt)
        monkeypatch.setattr(_wiz, "_choose_gateway_interactive", lambda pinned: {"delivery"})
        monkeypatch.setattr(_wiz, "_choose_delivery_interactive", lambda language: "prototype")
        monkeypatch.setattr(_wiz, "_choose_iac_interactive", lambda: "none")
        monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)
        inputs = __main__._gather_inputs_interactive(
            default_name="proj", no_plugin=False, profile="individual"
        )
        assert inputs.deploy_app == ""
        assert not any("Deploy" in label for label in labels)
