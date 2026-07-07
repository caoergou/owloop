"""Persistent run configuration loader for owloop."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore[assignment, misc]


_RUN_CONFIG_TYPES: dict[str, type[Any] | tuple[type[Any], ...]] = {
    "model": str,
    "notify_desktop": bool,
    "converge": int,
    "workers": int,
    "rollback": bool,
    "max_iterations": int,
    "max_duration": int,
    "max_tokens": int,
    "idle_timeout": (int, float),
    "max_tokens_per_iteration": int,
    "max_turns_per_iteration": int,
    "keep_retrying": bool,
    "notify_webhook": str,
    "no_tui": bool,
    "dry_run": bool,
}

# Boolean CLI flags default to False; config turns them on.
_BOOL_FLAG_KEYS: frozenset[str] = frozenset(
    {"notify_desktop", "rollback", "keep_retrying", "no_tui", "dry_run"}
)

# Numeric CLI options use 0 as the "not set" sentinel.
_NUMERIC_KEYS: frozenset[str] = frozenset(
    {
        "converge",
        "workers",
        "max_iterations",
        "max_duration",
        "max_tokens",
        "idle_timeout",
        "max_tokens_per_iteration",
        "max_turns_per_iteration",
    }
)


def _type_name(expected: type[Any] | tuple[type[Any], ...]) -> str:
    """Return a human-readable name for an expected type or type union."""
    if isinstance(expected, tuple):
        return " | ".join(t.__name__ for t in expected)
    return expected.__name__


def _is_valid_type(value: Any, expected: type[Any] | tuple[type[Any], ...]) -> bool:
    """Check whether ``value`` has exactly the expected type(s).

    ``bool`` is not accepted where ``int`` is expected, because TOML booleans
    and integers are distinct types.
    """
    if isinstance(expected, tuple):
        return type(value) in expected
    return type(value) is expected


def load_run_config(path: Path) -> dict[str, Any]:
    """Load the persistent ``[run]`` configuration from ``path``.

    Args:
        path: Path to the TOML configuration file.

    Returns:
        A flattened dictionary containing only the validated keys from the
        ``[run]`` section. Returns an empty dictionary when the file is missing,
        the TOML parser is unavailable, parsing fails, or the ``[run]`` section
        is invalid.
    """
    if not path.exists():
        return {}

    if tomllib is None:
        warnings.warn(
            "TOML parser not available. Install `tomli` for Python <3.11. "
            f"Skipping configuration file: {path}",
            RuntimeWarning,
            stacklevel=2,
        )
        return {}

    try:
        with path.open("rb") as file:
            data: dict[str, Any] = tomllib.load(file)
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"Failed to parse {path}: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return {}

    run_config = data.get("run", {})
    if not isinstance(run_config, dict):
        warnings.warn(
            f"Invalid `[run]` section in {path}: expected a table.",
            RuntimeWarning,
            stacklevel=2,
        )
        return {}

    unknown_keys = [key for key in run_config if key not in _RUN_CONFIG_TYPES]
    if unknown_keys:
        warnings.warn(
            f"Unknown keys in `[run]` section of {path}: {unknown_keys}",
            RuntimeWarning,
            stacklevel=2,
        )

    result: dict[str, Any] = {}
    for key, value in run_config.items():
        if key not in _RUN_CONFIG_TYPES:
            continue
        expected = _RUN_CONFIG_TYPES[key]
        if not _is_valid_type(value, expected):
            warnings.warn(
                f"Invalid type for `[run].{key}` in {path}: "
                f"expected {_type_name(expected)}, got {type(value).__name__}",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        result[key] = value

    return result


def apply_config_defaults(
    cli_kwargs: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    """Merge persistent config defaults into CLI kwargs.

    Only ``falsy-but-not-explicitly-set`` CLI values are replaced by config
    values, so explicitly provided CLI arguments always win.

    Args:
        cli_kwargs: Arguments received from the command line.
        config: Validated persistent configuration from :func:`load_run_config`.

    Returns:
        A new dictionary with config defaults applied.
    """
    merged = dict(cli_kwargs)

    for key, config_value in config.items():
        if key not in _RUN_CONFIG_TYPES:
            continue

        cli_value = merged.get(key)

        if key in {"model", "notify_webhook"}:
            if cli_value is None:
                merged[key] = config_value
        elif key in _BOOL_FLAG_KEYS:
            if cli_value is False:
                merged[key] = config_value
        elif key in _NUMERIC_KEYS:
            if cli_value in (0, None):
                merged[key] = config_value
        else:
            if cli_value in (None, 0, False, ""):
                merged[key] = config_value

    return merged
