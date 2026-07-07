"""Persistent CLI configuration helpers."""

from pathlib import Path
from typing import Any

from owloop.config import apply_config_defaults, load_run_config
from owloop.report import ReportGenerator


def _run_config_path() -> Path:
    """Return the persistent run configuration file path."""
    return Path.cwd() / ".owloop" / "config.toml"


def _load_and_apply_run_config(**cli_kwargs: Any) -> dict[str, Any]:
    """Load ``.owloop/config.toml`` and merge its ``[run]`` defaults into CLI kwargs."""
    config = load_run_config(_run_config_path())
    return apply_config_defaults(cli_kwargs, config)


def _default_report_path() -> Path:
    """Return the default quick-report output path."""
    return Path.cwd() / ".owloop" / "reports" / "owloop_report_latest.html"


def _generate_quick_report(summary: Any) -> Path | None:
    """Generate a fast, no-AI HTML report and return its path, or None on failure."""
    try:
        report_path = _default_report_path()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        generator = ReportGenerator(summary.main_repo_dir)
        generator.generate(report_path, insights=None, use_tailwind=False)
        return report_path
    except Exception:
        return None
