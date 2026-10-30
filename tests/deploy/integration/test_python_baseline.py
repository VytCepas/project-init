from pathlib import Path


def test_poetry_python_floor_extracted_during_upgrade(tmp_path: Path):
    from project_init.upgrade import read_scaffold_record

    # Write a pyproject.toml with Poetry dependency format
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[tool.poetry.dependencies]
python = "^3.13"
""")

    # Write a config.yaml with no python_floor (pre-3.14 record)
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    config = agents_dir / "config.yaml"
    config.write_text("""
preset: core
agents: claude
""")

    preset, variables, manifest, migrated = read_scaffold_record(tmp_path)

    assert variables["python_floor"] == "3.13", "Should extract 3.13 from ^3.13"


def test_poetry_python_floor_extracted_during_build_variables(tmp_path: Path):

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[tool.poetry.dependencies]
python = "~=3.14"
""")

    import subprocess
    import sys

    subprocess.run(
        [
            sys.executable,
            "-m",
            "project_init",
            str(tmp_path),
            "--name",
            "foo",
            "--preset",
            "core",
            "--agents",
            "claude",
            "--description",
            "test",
            "--language",
            "python",
            "--non-interactive",
        ],
        check=True,
    )

    mypy = tmp_path / "mypy.ini"
    assert "python_version = 3.14" in mypy.read_text(), (
        "mypy.ini must use 3.14 extracted from ~=3.14"
    )


# Direct coverage for the shared extractor (PI-799). The upgrade/build paths
# above exercise it end-to-end, but only this asserts on the function the CLI's
# --python-version conflict check (#713) calls, and on each branch a mutation
# run flagged as unguarded: the file-exists gate, the [project] lookup, and the
# poetry fallback.


def test_python_floor_reads_project_requires_python(tmp_path: Path):
    from project_init.variables import _python_floor_from_pyproject

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nrequires-python = ">=3.12"\n')
    assert _python_floor_from_pyproject(tmp_path) == "3.12"


def test_python_floor_falls_back_to_poetry_python(tmp_path: Path):
    from project_init.variables import _python_floor_from_pyproject

    # No [project] requires-python — the poetry dependency spec is the source.
    (tmp_path / "pyproject.toml").write_text('[tool.poetry.dependencies]\npython = "^3.13"\n')
    assert _python_floor_from_pyproject(tmp_path) == "3.13"


def test_python_floor_none_when_no_pyproject(tmp_path: Path):
    from project_init.variables import _python_floor_from_pyproject

    # Greenfield scaffold (#628): the directory exists but declares nothing.
    assert _python_floor_from_pyproject(tmp_path) is None


def test_python_floor_none_when_target_is_none():
    from project_init.variables import _python_floor_from_pyproject

    assert _python_floor_from_pyproject(None) is None


def test_python_floor_none_when_requires_python_absent(tmp_path: Path):
    from project_init.variables import _python_floor_from_pyproject

    # A pyproject with neither [project] requires-python nor a poetry python pin.
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    assert _python_floor_from_pyproject(tmp_path) is None
