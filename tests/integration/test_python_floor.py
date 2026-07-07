from pathlib import Path
from project_init.upgrade import _migrate_semantic_config, _migrate_agents

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
    from project_init.__main__ import _build_variables, ScaffoldInputs
    
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[tool.poetry.dependencies]
python = "~=3.14"
""")
    
    import subprocess
    import sys
    
    subprocess.run([sys.executable, "-m", "project_init", str(tmp_path), "--name", "foo", "--preset", "core", "--agents", "claude", "--description", "test", "--language", "python", "--non-interactive"], check=True)
    
    mypy = tmp_path / "mypy.ini"
    assert "python_version = 3.14" in mypy.read_text(), "mypy.ini must use 3.14 extracted from ~=3.14"
