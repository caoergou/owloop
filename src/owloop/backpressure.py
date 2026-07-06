"""Discover and persist project verification (backpressure) commands.

Backpressure commands are the tests, lints, type checks, and builds that
reject invalid work. This module scans common project configuration files
and stores the discovered commands so owloop specs can reference them
without manual configuration.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, cast


class BackpressureCommand:
    """A single verification command discovered from a project config."""

    def __init__(self, name: str, command: str, source: str) -> None:
        self.name = name
        self.command = command
        self.source = source

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "command": self.command, "source": self.source}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> BackpressureCommand:
        return cls(
            name=data["name"],
            command=data["command"],
            source=data["source"],
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BackpressureCommand):
            return NotImplemented
        return (
            self.name == other.name
            and self.command == other.command
            and self.source == other.source
        )

    def __repr__(self) -> str:
        return f"BackpressureCommand(name={self.name!r}, command={self.command!r}, source={self.source!r})"


class BackpressureDiscovery:
    """Scan a project for verification commands."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)

    def discover(self) -> list[BackpressureCommand]:
        """Return all discovered verification commands."""
        commands: list[BackpressureCommand] = []
        commands.extend(self._from_pyproject())
        commands.extend(self._from_package_json())
        commands.extend(self._from_makefile())
        commands.extend(self._from_cargo_toml())
        commands.extend(self._from_github_workflows())
        return commands

    def _from_pyproject(self) -> list[BackpressureCommand]:
        path = self.project_dir / "pyproject.toml"
        if not path.is_file():
            return []

        try:
            data = self._read_toml(path)
        except Exception:
            return []

        commands: list[BackpressureCommand] = []
        tool = data.get("tool", {})

        if "pytest" in tool or self._has_dev_dependency(data, "pytest"):
            testpaths = self._extract_pytest_paths(tool.get("pytest", {}))
            commands.append(
                BackpressureCommand(
                    name="pytest",
                    command=f"pytest {testpaths}".strip(),
                    source="pyproject.toml",
                )
            )

        if "ruff" in tool or self._has_dev_dependency(data, "ruff"):
            src_dirs = self._guess_source_dirs()
            commands.append(
                BackpressureCommand(
                    name="ruff check",
                    command=f"ruff check {' '.join(src_dirs)}",
                    source="pyproject.toml",
                )
            )

        if "mypy" in tool or self._has_dev_dependency(data, "mypy"):
            src_dirs = self._guess_source_dirs()
            commands.append(
                BackpressureCommand(
                    name="mypy",
                    command=f"mypy {' '.join(src_dirs)}",
                    source="pyproject.toml",
                )
            )

        return commands

    def _extract_pytest_paths(self, pytest_cfg: dict[str, Any]) -> str:
        testpaths = pytest_cfg.get("testpaths")
        if isinstance(testpaths, list):
            return " ".join(testpaths)
        if isinstance(testpaths, str):
            return testpaths
        return "tests/"

    def _has_dev_dependency(self, data: dict[str, Any], package: str) -> bool:
        dep_groups = data.get("dependency-groups", {})
        dev = dep_groups.get("dev", [])
        return any(
            isinstance(item, str) and item.lower().startswith(package)
            for item in dev
        )

    def _guess_source_dirs(self) -> list[str]:
        candidates = ["src", "."]
        found: list[str] = []
        for cand in candidates:
            path = self.project_dir / cand
            if path.is_dir():
                found.append(cand)
        return found or ["."]

    def _from_package_json(self) -> list[BackpressureCommand]:
        path = self.project_dir / "package.json"
        if not path.is_file():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

        scripts = data.get("scripts", {})
        commands: list[BackpressureCommand] = []

        if "test" in scripts:
            commands.append(
                BackpressureCommand(
                    name="npm test",
                    command="npm test",
                    source="package.json",
                )
            )
        if "lint" in scripts:
            commands.append(
                BackpressureCommand(
                    name="npm lint",
                    command="npm run lint",
                    source="package.json",
                )
            )
        if "build" in scripts:
            commands.append(
                BackpressureCommand(
                    name="npm build",
                    command="npm run build",
                    source="package.json",
                )
            )

        return commands

    def _from_makefile(self) -> list[BackpressureCommand]:
        path = self.project_dir / "Makefile"
        if not path.is_file():
            return []

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return []

        commands: list[BackpressureCommand] = []
        targets = {"test": "make test", "lint": "make lint", "check": "make check"}
        for target, command in targets.items():
            if re.search(rf"^{re.escape(target)}\s*:", text, re.MULTILINE):
                commands.append(
                    BackpressureCommand(
                        name=f"make {target}",
                        command=command,
                        source="Makefile",
                    )
                )

        return commands

    def _from_cargo_toml(self) -> list[BackpressureCommand]:
        path = self.project_dir / "Cargo.toml"
        if not path.is_file():
            return []

        commands: list[BackpressureCommand] = []
        commands.append(
            BackpressureCommand(
                name="cargo test",
                command="cargo test",
                source="Cargo.toml",
            )
        )
        commands.append(
            BackpressureCommand(
                name="cargo clippy",
                command="cargo clippy",
                source="Cargo.toml",
            )
        )
        return commands

    def _from_github_workflows(self) -> list[BackpressureCommand]:
        workflows_dir = self.project_dir / ".github" / "workflows"
        if not workflows_dir.is_dir():
            return []

        known_patterns = [
            (r"pytest?\s+(-q\s+)?(.*)", "pytest"),
            (r"ruff check\s+(.*)", "ruff check"),
            (r"mypy\s+(.*)", "mypy"),
            (r"npm test", "npm test"),
            (r"npm run lint", "npm lint"),
            (r"cargo test", "cargo test"),
            (r"cargo clippy", "cargo clippy"),
            (r"make (test|lint|check)", "make"),
        ]

        commands: list[BackpressureCommand] = []
        seen: set[str] = set()

        for file_path in workflows_dir.glob("*.yml"):
            try:
                text = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            for pattern, label in known_patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    command = match.group(0).strip()
                    if command and command not in seen:
                        seen.add(command)
                        commands.append(
                            BackpressureCommand(
                                name=label,
                                command=command,
                                source=f".github/workflows/{file_path.name}",
                            )
                        )

        return commands

    def _read_toml(self, path: Path) -> dict[str, Any]:
        try:
            import tomllib

            return cast(dict[str, Any], tomllib.loads(path.read_text(encoding="utf-8")))
        except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback
            import tomli

            return cast(dict[str, Any], tomli.loads(path.read_text(encoding="utf-8")))


def resolve_backpressure_path(project_dir: Path) -> Path:
    """Return the path to the persisted backpressure file."""
    return project_dir / ".owloop" / "backpressure.json"


def load_backpressure(project_dir: Path) -> list[BackpressureCommand]:
    """Load discovered commands from disk."""
    path = resolve_backpressure_path(project_dir)
    if not path.is_file():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    commands = data.get("commands", [])
    if not isinstance(commands, list):
        return []

    result: list[BackpressureCommand] = []
    for item in commands:
        if isinstance(item, dict) and "name" in item and "command" in item:
            result.append(
                BackpressureCommand(
                    name=item["name"],
                    command=item["command"],
                    source=item.get("source", "unknown"),
                )
            )
    return result


def save_backpressure(
    project_dir: Path, commands: list[BackpressureCommand]
) -> Path:
    """Save discovered commands to disk."""
    path = resolve_backpressure_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"commands": [cmd.to_dict() for cmd in commands]}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def discover_and_save(project_dir: Path) -> tuple[list[BackpressureCommand], Path]:
    """Discover commands and persist them."""
    commands = BackpressureDiscovery(project_dir).discover()
    path = save_backpressure(project_dir, commands)
    return commands, path


def command_exists(command: str) -> bool:
    """Check whether the first token of a command is available on PATH."""
    first = command.split()[0]
    return shutil.which(first) is not None
