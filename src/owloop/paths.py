"""Path resolution for owloop metadata directories.

The owloop CLI and engine keep their working files in a single metadata
directory named ``.owloop/`` inside the project root. For backwards
compatibility, if that directory does not exist we fall back to the legacy
layout where ``specs/`` and ``logs/`` live directly in the project root.
"""

from __future__ import annotations

from pathlib import Path

OWLOOP_DIR_NAME = ".owloop"
SPECS_DIR_NAME = "specs"
LOGS_DIR_NAME = "logs"
TEMPLATES_DIR_NAME = "templates"


def resolve_owloop_dir(project_dir: Path) -> Path:
    """Return the owloop metadata directory for a project.

    Prefer ``.owloop/`` when it exists; otherwise fall back to the project
    root for legacy projects initialized before the metadata directory was
    introduced.
    """
    modern = project_dir / OWLOOP_DIR_NAME
    if modern.exists():
        return modern
    return project_dir


def resolve_specs_dir(project_dir: Path) -> Path:
    """Return the specs directory for a project."""
    return resolve_owloop_dir(project_dir) / SPECS_DIR_NAME


def resolve_logs_dir(project_dir: Path) -> Path:
    """Return the logs directory for a project."""
    return resolve_owloop_dir(project_dir) / LOGS_DIR_NAME


def resolve_templates_dir(project_dir: Path) -> Path:
    """Return the templates directory for a project."""
    return resolve_owloop_dir(project_dir) / TEMPLATES_DIR_NAME
