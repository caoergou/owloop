"""Tests for owloop metadata path resolution."""

from __future__ import annotations

from pathlib import Path

from owloop.paths import (
    resolve_logs_dir,
    resolve_owloop_dir,
    resolve_specs_dir,
    resolve_templates_dir,
)


def test_resolve_owloop_dir_prefers_dot_owloop(tmp_path: Path) -> None:
    (tmp_path / ".owloop").mkdir()
    assert resolve_owloop_dir(tmp_path) == tmp_path / ".owloop"


def test_resolve_owloop_dir_falls_back_to_project_root(tmp_path: Path) -> None:
    assert resolve_owloop_dir(tmp_path) == tmp_path


def test_resolve_specs_dir_prefers_dot_owloop(tmp_path: Path) -> None:
    (tmp_path / ".owloop" / "specs").mkdir(parents=True)
    assert resolve_specs_dir(tmp_path) == tmp_path / ".owloop" / "specs"


def test_resolve_specs_dir_falls_back_to_legacy_path(tmp_path: Path) -> None:
    assert resolve_specs_dir(tmp_path) == tmp_path / "specs"


def test_resolve_logs_dir_prefers_dot_owloop(tmp_path: Path) -> None:
    (tmp_path / ".owloop" / "logs").mkdir(parents=True)
    assert resolve_logs_dir(tmp_path) == tmp_path / ".owloop" / "logs"


def test_resolve_logs_dir_falls_back_to_legacy_path(tmp_path: Path) -> None:
    assert resolve_logs_dir(tmp_path) == tmp_path / "logs"


def test_resolve_templates_dir_prefers_dot_owloop(tmp_path: Path) -> None:
    (tmp_path / ".owloop" / "templates").mkdir(parents=True)
    assert resolve_templates_dir(tmp_path) == tmp_path / ".owloop" / "templates"


def test_resolve_templates_dir_falls_back_to_legacy_path(tmp_path: Path) -> None:
    assert resolve_templates_dir(tmp_path) == tmp_path / "templates"
