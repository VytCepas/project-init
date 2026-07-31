"""A non-editable install renders a frozen copy of `templates/` (PI-903 follow-up).

`templates/` is the product, and a non-editable `uv pip install` copies it *into*
the package. Reinstall once, keep committing to the checkout, and the two
diverge — after which `project-init upgrade` renders the frozen copy while the
user reasonably believes it is applying the checkout in front of them, and
reports success.

That is not hypothetical. Downstream of PI-903 (the symlinked-marker prod_guard
fix), an upgrade run from a stale install re-applied the *pre-fix* prod_guard
template and reported success — reintroducing the vulnerability the upgrade was
performed to obtain.

These tests drive `stale_install` against real on-disk fixtures rather than
asserting on the warning's prose: the point is the detection, and it must not
fire when there is nothing wrong.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from project_init.scaffold import stale_install, templates_dir

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _fake_checkout(root: Path, *, templates_from: Path, name: str = "project-init") -> Path:
    """A minimal project-init source checkout: pyproject + templates/."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    shutil.copytree(templates_from, root / "templates")
    return root


class TestStaleInstallDetection:
    def test_no_warning_from_an_unrelated_directory(self, tmp_path: Path):
        """The overwhelmingly common case: not inside any checkout at all."""
        assert stale_install(tmp_path) is None

    def test_no_warning_when_standing_in_this_checkout(self):
        """Running the suite from this repo must never warn.

        Note the suite renders from the session-scoped frozen snapshot of
        ``templates/`` (conftest ``_frozen_templates``), not the live tree — so
        this is the different-path-same-content case, which is precisely the one
        that must stay silent. An editable install is the same case with the
        paths equal.
        """
        assert stale_install(_REPO_ROOT) is None
        # Also from a subdirectory — the walk goes up.
        assert stale_install(_REPO_ROOT / "src" / "project_init") is None

    def test_no_warning_when_a_separate_copy_is_byte_identical(self, tmp_path: Path):
        """Different path, same content — nothing is stale.

        A fresh install rewrites mtimes without changing a byte. Warning here
        would be a false positive, and a guard that cries wolf gets ignored.
        """
        checkout = _fake_checkout(tmp_path / "clone", templates_from=templates_dir())
        assert stale_install(checkout) is None

    def test_warns_when_the_checkout_has_moved_on(self, tmp_path: Path):
        """The real failure: checkout carries a fix the rendered templates lack."""
        checkout = _fake_checkout(tmp_path / "clone", templates_from=templates_dir())
        # Simulate a commit landing in the checkout after the install froze.
        target = checkout / "templates" / "base" / "dot_agents" / "hooks" / "prod_guard.py"
        assert target.is_file(), "fixture expectation: prod_guard template exists"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n# a fix the installed copy lacks\n",
            encoding="utf-8",
        )
        assert stale_install(checkout) == checkout

    def test_warns_on_a_deleted_template_too(self, tmp_path: Path):
        """Drift is not only added bytes — a removed file must count."""
        checkout = _fake_checkout(tmp_path / "clone", templates_from=templates_dir())
        victim = next((checkout / "templates").rglob("*.tmpl"))
        victim.unlink()
        assert stale_install(checkout) == checkout

    def test_ignores_a_directory_that_merely_looks_like_a_checkout(self, tmp_path: Path):
        """Some other project with a templates/ dir is not a project-init checkout."""
        other = _fake_checkout(
            tmp_path / "other", templates_from=templates_dir(), name="something-else"
        )
        (other / "templates" / "STRAY.txt").write_text("drift", encoding="utf-8")
        assert stale_install(other) is None

    def test_a_pyproject_without_templates_is_not_a_checkout(self, tmp_path: Path):
        root = tmp_path / "bare"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "project-init"\nversion = "0.0.0"\n', encoding="utf-8"
        )
        assert stale_install(root) is None

    def test_a_malformed_pyproject_does_not_raise(self, tmp_path: Path):
        """A broken TOML somewhere above cwd must not crash an upgrade."""
        root = tmp_path / "broken"
        (root / "templates").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project\nname = ", encoding="utf-8")
        assert stale_install(root) is None

    @pytest.mark.parametrize(
        "pyproject",
        [
            pytest.param('project = "invalid"\n', id="project-is-a-string"),
            pytest.param("project = 42\n", id="project-is-an-int"),
            pytest.param("project = []\n", id="project-is-an-array"),
            pytest.param("[project]\nname = 42\n", id="name-is-not-a-string"),
            pytest.param('[tool.poetry]\nname = "x"\n', id="no-project-table"),
        ],
    )
    def test_a_valid_toml_with_an_unexpected_project_value_is_not_a_checkout(
        self, tmp_path: Path, pyproject: str
    ):
        """PR #910 review (P2): syntactically valid TOML, wrong shape.

        `project = "invalid"` decodes fine, so the TOMLDecodeError guard does not
        catch it and a chained .get() raised AttributeError. Because the check
        runs before `upgrade` validates its target, that traceback aborted EVERY
        upgrade invoked from such a directory — an advisory warning hardened into
        a crash. Reproduced before fixing.
        """
        root = tmp_path / "oddly-shaped"
        (root / "templates").mkdir(parents=True)
        (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        assert stale_install(root) is None

    def test_nearest_checkout_wins(self, tmp_path: Path):
        """An inner checkout shadows an outer one; the walk stops at the first."""
        outer = _fake_checkout(tmp_path / "outer", templates_from=templates_dir())
        (outer / "templates" / "OUTER.txt").write_text("drift", encoding="utf-8")
        inner = _fake_checkout(outer / "nested" / "inner", templates_from=templates_dir())
        # inner is byte-identical to what we render, so the answer is None even
        # though the outer one has drifted.
        assert stale_install(inner) is None


class TestUpgradeEmitsTheWarning:
    def test_upgrade_warns_via_stderr(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Wiring check: the detection reaches the user on `upgrade`."""
        from project_init import subcommands

        checkout = _fake_checkout(tmp_path / "clone", templates_from=templates_dir())
        (checkout / "templates" / "DRIFT.txt").write_text("x", encoding="utf-8")

        monkey_root = checkout

        def _fake_stale(cwd: Path | None = None) -> Path | None:
            return monkey_root

        original = subcommands.__dict__.get("_warn_if_stale_install")
        assert original is not None
        # Exercise the real writer, with only the detector stubbed — so the
        # message and the stream it goes to are the ones users see.
        import project_init.scaffold as scaffold_mod

        saved = scaffold_mod.stale_install
        scaffold_mod.stale_install = _fake_stale  # type: ignore[assignment]
        try:
            subcommands._warn_if_stale_install()
        finally:
            scaffold_mod.stale_install = saved  # type: ignore[assignment]

        err = capsys.readouterr().err
        assert "warning:" in err
        assert str(checkout) in err
        assert "uv pip install -e ." in err

    def test_a_raising_detector_cannot_break_upgrade(self, capsys: pytest.CaptureFixture[str]):
        """The class behind the #910 P2, not just that instance.

        This runs before `upgrade` validates its target, and the detection walks
        parent directories, parses arbitrary TOML and reads several hundred
        files. An unreadable file or a deleted cwd must cost a warning, never the
        run — so the caller swallows anything the detector raises.
        """
        import project_init.scaffold as scaffold_mod
        from project_init import subcommands

        def boom(cwd: Path | None = None) -> Path | None:
            raise OSError("simulated: templates file vanished mid-walk")

        saved = scaffold_mod.stale_install
        scaffold_mod.stale_install = boom  # type: ignore[assignment]
        try:
            subcommands._warn_if_stale_install()  # must not raise
        finally:
            scaffold_mod.stale_install = saved  # type: ignore[assignment]

        # Silent: a failed diagnostic is not worth alarming the user about.
        assert capsys.readouterr().err == ""

    def test_silent_when_nothing_is_stale(self, capsys: pytest.CaptureFixture[str]):
        import project_init.scaffold as scaffold_mod
        from project_init import subcommands

        saved = scaffold_mod.stale_install
        scaffold_mod.stale_install = lambda cwd=None: None  # type: ignore[assignment]
        try:
            subcommands._warn_if_stale_install()
        finally:
            scaffold_mod.stale_install = saved  # type: ignore[assignment]

        assert capsys.readouterr().err == ""
