"""#577: scan the built container image with Trivy (delivery=service only).

The build-image job builds the Dockerfile to warm the cache; this adds a Trivy
scan of that same image, failing on CRITICAL/HIGH so a vulnerable base image is
never promoted, with SARIF uploaded to code scanning. Scoped to delivery_service
— the build-image job does not exist for other delivery modes.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


def _service(target: Path) -> Path:
    return _scaffold(
        target,
        delivery="service",
        delivery_service="true",
        language="python",
    )


def _ci(target: Path) -> str:
    return (target / ".github" / "workflows" / "ci.yml").read_text()


class TestTrivyImageScanPresent:
    def test_trivy_step_scoped_to_build_image(self, tmp_path: Path):
        ci = _ci(_service(tmp_path / "svc"))
        assert "build-image:" in ci
        assert "aquasecurity/trivy-action" in ci

    def test_fails_on_critical_high(self, tmp_path: Path):
        ci = _ci(_service(tmp_path / "svc"))
        assert "severity: CRITICAL,HIGH" in ci
        assert 'exit-code: "1"' in ci

    def test_scans_the_built_image_not_a_repull(self, tmp_path: Path):
        ci = _ci(_service(tmp_path / "svc"))
        # load: true makes the built image available to the daemon for Trivy.
        assert "load: true" in ci
        assert "image-ref: app:${{ github.sha }}" in ci

    def test_sarif_uploaded_to_code_scanning(self, tmp_path: Path):
        ci = _ci(_service(tmp_path / "svc"))
        assert "github/codeql-action/upload-sarif" in ci
        assert "trivy-results.sarif" in ci
        # Uploaded even when the scan step fails on a finding.
        assert "if: always()" in ci

    def test_security_events_permission_granted(self, tmp_path: Path):
        ci = _ci(_service(tmp_path / "svc"))
        assert "security-events: write" in ci

    def test_renders_cleanly(self, tmp_path: Path):
        ci = _ci(_service(tmp_path / "svc"))
        assert "{{#if" not in ci
        assert "{{/if" not in ci


class TestTrivyImageScanAbsent:
    def test_absent_for_prototype(self, tmp_path: Path):
        ci = _ci(_scaffold(tmp_path / "proto", delivery="prototype"))
        assert "build-image:" not in ci
        assert "aquasecurity/trivy-action" not in ci

    def test_absent_for_library(self, tmp_path: Path):
        ci = _ci(_scaffold(tmp_path / "lib", delivery="library", delivery_library="true"))
        assert "aquasecurity/trivy-action" not in ci


class TestFindingsSurviveCodeScanningBeingOff:
    """Code scanning is not universally available, and the job must not go red
    because of that.

    On a PRIVATE repo without GitHub Advanced Security, upload-sarif fails with
    "Code scanning is not enabled for this repository". That turned a CLEAN
    Trivy result into a failed build — observed on a private scaffolded service
    whose image had no CRITICAL/HIGH findings at all. A job that is red for a
    reason unrelated to what it checks is the false-positive failure: people
    stop reading it, and then a real CVE lands in the same silence.

    Two properties, and the second is what stops this from being a downgrade:
    the upload is best-effort, AND the SARIF is kept as an artifact so the
    findings still exist somewhere when the upload is refused. The GATE itself
    is the scan step's `exit-code: "1"`, which is asserted separately in
    TestTrivyImageScanPresent and is deliberately untouched here.
    """

    @staticmethod
    def _step(target: Path, name: str) -> dict:
        from tests.workflow import job, load_workflow

        for step in job(load_workflow(target), "build-image").get("steps", []):
            if step.get("name") == name:
                return step
        raise AssertionError(f"no step named {name!r} in build-image")

    def test_sarif_upload_is_best_effort(self, tmp_path: Path):
        step = self._step(_service(tmp_path / "svc"), "Upload Trivy SARIF to code scanning")
        assert step.get("continue-on-error") is True

    def test_sarif_kept_as_an_artifact(self, tmp_path: Path):
        step = self._step(_service(tmp_path / "svc"), "Keep the Trivy SARIF as an artifact")
        assert "actions/upload-artifact@" in step["uses"]
        assert step["with"]["path"] == "trivy-results.sarif"
        assert step["if"] == "always()", "must run even when the scan failed on a finding"

    def test_the_scan_itself_still_gates(self, tmp_path: Path):
        """The tolerance above must not have leaked onto the step that decides."""
        step = self._step(
            _service(tmp_path / "svc"), "Scan image for CRITICAL/HIGH vulnerabilities (Trivy)"
        )
        assert step.get("continue-on-error") is not True
        assert step["with"]["exit-code"] == "1"
