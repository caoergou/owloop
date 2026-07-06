"""Tests for backpressure command discovery."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from owloop.backpressure import (
    BackpressureCommand,
    BackpressureDiscovery,
    discover_and_save,
    load_backpressure,
    resolve_backpressure_path,
    save_backpressure,
)
from owloop.cli import main


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


def test_discovery_from_pyproject(temp_project: Path) -> None:
    pyproject = temp_project / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "demo"

[dependency-groups]
dev = ["pytest", "ruff", "mypy"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.10"
""",
        encoding="utf-8",
    )
    (temp_project / "src").mkdir()

    commands = BackpressureDiscovery(temp_project).discover()
    names = {cmd.name for cmd in commands}

    assert "pytest" in names
    assert "ruff check" in names
    assert "mypy" in names


def test_discovery_from_package_json(temp_project: Path) -> None:
    package = temp_project / "package.json"
    package.write_text(
        json.dumps({"scripts": {"test": "jest", "lint": "eslint .", "build": "tsc"}}),
        encoding="utf-8",
    )

    commands = BackpressureDiscovery(temp_project).discover()
    names = {cmd.name for cmd in commands}

    assert "npm test" in names
    assert "npm lint" in names
    assert "npm build" in names


def test_discovery_from_makefile(temp_project: Path) -> None:
    makefile = temp_project / "Makefile"
    makefile.write_text(
        """
.PHONY: test lint check

test:
	pytest

lint:
	ruff check .
""",
        encoding="utf-8",
    )

    commands = BackpressureDiscovery(temp_project).discover()
    names = {cmd.name for cmd in commands}

    assert "make test" in names
    assert "make lint" in names
    assert "make check" not in names


def test_discovery_from_cargo_toml(temp_project: Path) -> None:
    cargo = temp_project / "Cargo.toml"
    cargo.write_text(
        """
[package]
name = "demo"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    commands = BackpressureDiscovery(temp_project).discover()
    names = {cmd.name for cmd in commands}

    assert "cargo test" in names
    assert "cargo clippy" in names


def test_discovery_from_github_workflows(temp_project: Path) -> None:
    workflows = temp_project / ".github" / "workflows"
    workflows.mkdir(parents=True)
    workflow = workflows / "ci.yml"
    workflow.write_text(
        """
name: CI
jobs:
  test:
    steps:
      - run: pytest -q
      - run: ruff check src tests
      - run: mypy src
""",
        encoding="utf-8",
    )

    commands = BackpressureDiscovery(temp_project).discover()
    names = {cmd.name for cmd in commands}

    assert "pytest" in names
    assert "ruff check" in names
    assert "mypy" in names


def test_save_and_load(temp_project: Path) -> None:
    commands = [
        BackpressureCommand(name="pytest", command="pytest tests/", source="pyproject.toml"),
    ]
    path = save_backpressure(temp_project, commands)

    assert path.is_file()
    loaded = load_backpressure(temp_project)

    assert loaded == commands


def test_discover_and_save(temp_project: Path) -> None:
    pyproject = temp_project / "pyproject.toml"
    pyproject.write_text(
        """
[tool.pytest.ini_options]
testpaths = ["tests"]
""",
        encoding="utf-8",
    )
    (temp_project / "tests").mkdir()

    commands, path = discover_and_save(temp_project)

    assert path.is_file()
    assert len(commands) == 1
    assert commands[0].name == "pytest"


def test_resolve_backpressure_path_prefers_owloop_dir(temp_project: Path) -> None:
    (temp_project / ".owloop").mkdir()
    path = resolve_backpressure_path(temp_project)
    assert path == temp_project / ".owloop" / "backpressure.json"


def test_cli_discover() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as fs:
        fs_path = Path(fs)
        pyproject = fs_path / "pyproject.toml"
        pyproject.write_text(
            """
[tool.pytest.ini_options]
testpaths = ["tests"]
""",
            encoding="utf-8",
        )
        (fs_path / "tests").mkdir()
        result = runner.invoke(main, ["discover"])
        assert result.exit_code == 0
        assert "pytest" in result.output
        assert (fs_path / ".owloop" / "backpressure.json").is_file()


def test_cli_init_creates_backpressure() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as fs:
        fs_path = Path(fs)
        pyproject = fs_path / "pyproject.toml"
        pyproject.write_text(
            """
[tool.pytest.ini_options]
testpaths = ["tests"]
""",
            encoding="utf-8",
        )
        (fs_path / "tests").mkdir()
        import subprocess

        subprocess.run(["git", "init"], check=True, capture_output=True)
        result = runner.invoke(main, ["init", "--example"])
        assert result.exit_code == 0
        assert (fs_path / ".owloop" / "backpressure.json").is_file()
