"""Tests for owloop configuration loading."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any

import pytest

from owloop.config import apply_config_defaults, load_run_config


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Return a temporary path for a config file."""
    return tmp_path / ".owloop" / "config.toml"


def write_config(path: Path, content: str) -> None:
    """Write ``content`` to ``path``, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestLoadRunConfig:
    """Tests for :func:`load_run_config`."""

    def test_missing_file_returns_empty_config(self, config_path: Path) -> None:
        """A missing config file yields an empty dictionary."""
        result = load_run_config(config_path)
        assert result == {}

    def test_valid_run_section_loads(self, config_path: Path) -> None:
        """All supported ``[run]`` keys are loaded with correct types."""
        write_config(
            config_path,
            """
[run]
model = "gpt-4o"
notify_desktop = true
converge = 3
workers = 2
rollback = false
max_iterations = 10
max_duration = 300
max_tokens = 100000
idle_timeout = 1.5
max_tokens_per_iteration = 4000
max_turns_per_iteration = 5
keep_retrying = true
notify_webhook = "https://example.com/hook"
no_tui = true
dry_run = true
""",
        )
        result = load_run_config(config_path)
        assert result == {
            "model": "gpt-4o",
            "notify_desktop": True,
            "converge": 3,
            "workers": 2,
            "rollback": False,
            "max_iterations": 10,
            "max_duration": 300,
            "max_tokens": 100000,
            "idle_timeout": 1.5,
            "max_tokens_per_iteration": 4000,
            "max_turns_per_iteration": 5,
            "keep_retrying": True,
            "notify_webhook": "https://example.com/hook",
            "no_tui": True,
            "dry_run": True,
        }

    def test_other_sections_ignored(self, config_path: Path) -> None:
        """Sections other than ``[run]`` are not returned."""
        write_config(
            config_path,
            """
[other]
model = "ignored"

[run]
model = "claude-sonnet-4"
""",
        )
        result = load_run_config(config_path)
        assert result == {"model": "claude-sonnet-4"}

    def test_unknown_keys_warn_but_are_ignored(self, config_path: Path) -> None:
        """Unknown keys under ``[run]`` trigger a warning and are skipped."""
        write_config(
            config_path,
            """
[run]
model = "gpt-4o"
unknown_option = 123
another_bad_key = "value"
""",
        )
        with pytest.warns(RuntimeWarning, match="Unknown keys") as warning_info:
            result = load_run_config(config_path)

        assert result == {"model": "gpt-4o"}
        warning_message = str(warning_info[0].message)
        assert "unknown_option" in warning_message
        assert "another_bad_key" in warning_message

    def test_wrong_type_warns_and_skips_key(self, config_path: Path) -> None:
        """Keys with wrong types trigger a warning and are not loaded."""
        write_config(
            config_path,
            """
[run]
model = "gpt-4o"
converge = "not-a-number"
notify_desktop = "yes"
""",
        )
        with warnings.catch_warnings(record=True) as warning_list:
            warnings.simplefilter("always")
            result = load_run_config(config_path)

        assert result == {"model": "gpt-4o"}
        messages = [str(w.message) for w in warning_list]
        assert any("converge" in m and "expected int" in m for m in messages)
        assert any("notify_desktop" in m and "expected bool" in m for m in messages)

    def test_bool_not_accepted_as_int(self, config_path: Path) -> None:
        """A boolean must not be accepted where an integer is expected."""
        write_config(
            config_path,
            """
[run]
converge = true
""",
        )
        with pytest.warns(RuntimeWarning, match="converge"):
            result = load_run_config(config_path)
        assert result == {}

    def test_invalid_toml_warns_and_returns_empty(self, config_path: Path) -> None:
        """A malformed TOML file triggers a warning and yields an empty dict."""
        write_config(config_path, "[run\nmodel = \"broken\"")
        with pytest.warns(RuntimeWarning, match="Failed to parse"):
            result = load_run_config(config_path)
        assert result == {}

    def test_run_section_not_a_table(self, config_path: Path) -> None:
        """A non-table ``run`` value triggers a warning and yields an empty dict."""
        write_config(config_path, 'run = "not-a-table"')
        with pytest.warns(RuntimeWarning, match="expected a table"):
            result = load_run_config(config_path)
        assert result == {}

    @pytest.mark.skipif(sys.version_info >= (3, 11), reason="tomli only used on Python <3.11")
    def test_missing_tomli_warns_and_returns_empty(self, config_path: Path, monkeypatch: Any) -> None:
        """On Python <3.11, missing ``tomli`` triggers a warning and yields empty config."""
        write_config(config_path, '[run]\nmodel = "gpt-4o"')
        monkeypatch.setattr("owloop.config.tomllib", None)
        with pytest.warns(RuntimeWarning, match="TOML parser not available"):
            result = load_run_config(config_path)
        assert result == {}


class TestApplyConfigDefaults:
    """Tests for :func:`apply_config_defaults`."""

    def test_returns_copy(self) -> None:
        """The returned dict is a copy; the input is not mutated."""
        cli_kwargs: dict[str, Any] = {"model": None}
        config: dict[str, Any] = {"model": "gpt-4o"}
        merged = apply_config_defaults(cli_kwargs, config)
        assert merged is not cli_kwargs
        assert cli_kwargs == {"model": None}

    def test_model_only_overrides_none(self) -> None:
        """``model`` from config is applied only when CLI value is ``None``."""
        config: dict[str, Any] = {"model": "config-model"}
        assert apply_config_defaults({"model": None}, config) == {"model": "config-model"}
        assert apply_config_defaults({"model": "cli-model"}, config) == {"model": "cli-model"}
        assert apply_config_defaults({"model": ""}, config) == {"model": ""}

    def test_notify_webhook_only_overrides_none(self) -> None:
        """``notify_webhook`` from config is applied only when CLI value is ``None``."""
        config: dict[str, Any] = {"notify_webhook": "https://config.example.com"}
        assert apply_config_defaults({"notify_webhook": None}, config) == {
            "notify_webhook": "https://config.example.com"
        }
        assert apply_config_defaults({"notify_webhook": "https://cli.example.com"}, config) == {
            "notify_webhook": "https://cli.example.com"
        }

    def test_boolean_flags_only_override_false(self) -> None:
        """Boolean flags from config turn on only when CLI value is ``False``."""
        config: dict[str, Any] = {
            "notify_desktop": True,
            "rollback": True,
            "keep_retrying": True,
            "no_tui": True,
            "dry_run": True,
        }
        cli_kwargs: dict[str, Any] = {
            "notify_desktop": False,
            "rollback": False,
            "keep_retrying": False,
            "no_tui": False,
            "dry_run": False,
        }
        assert apply_config_defaults(cli_kwargs, config) == {
            "notify_desktop": True,
            "rollback": True,
            "keep_retrying": True,
            "no_tui": True,
            "dry_run": True,
        }

    def test_boolean_flags_preserve_explicit_true(self) -> None:
        """Explicit ``True`` boolean CLI flags are not overridden."""
        config: dict[str, Any] = {"notify_desktop": False}
        assert apply_config_defaults({"notify_desktop": True}, config) == {
            "notify_desktop": True
        }

    def test_numeric_options_override_zero_or_none(self) -> None:
        """Numeric config options replace ``0`` or ``None`` CLI values."""
        config: dict[str, Any] = {
            "converge": 3,
            "workers": 2,
            "max_iterations": 10,
            "max_duration": 300,
            "max_tokens": 100000,
            "idle_timeout": 1.5,
            "max_tokens_per_iteration": 4000,
            "max_turns_per_iteration": 5,
        }
        cli_kwargs: dict[str, Any] = {
            "converge": 0,
            "workers": None,
            "max_iterations": 0,
            "max_duration": None,
            "max_tokens": 0,
            "idle_timeout": 0,
            "max_tokens_per_iteration": None,
            "max_turns_per_iteration": 0,
        }
        assert apply_config_defaults(cli_kwargs, config) == config

    def test_numeric_options_preserve_explicit_values(self) -> None:
        """Explicitly provided numeric CLI values are not overridden."""
        config: dict[str, Any] = {"converge": 3, "idle_timeout": 1.5}
        cli_kwargs: dict[str, Any] = {"converge": 5, "idle_timeout": 2.0}
        assert apply_config_defaults(cli_kwargs, config) == cli_kwargs

    def test_full_merge(self) -> None:
        """A realistic merge combines explicit CLI values with config defaults."""
        cli_kwargs: dict[str, Any] = {
            "model": "cli-model",
            "notify_desktop": False,
            "rollback": False,
            "keep_retrying": False,
            "no_tui": False,
            "dry_run": False,
            "converge": 0,
            "workers": 4,
            "max_iterations": None,
            "max_duration": 600,
            "max_tokens": 0,
            "idle_timeout": None,
            "max_tokens_per_iteration": 0,
            "max_turns_per_iteration": 0,
            "notify_webhook": None,
        }
        config: dict[str, Any] = {
            "model": "config-model",
            "notify_desktop": True,
            "rollback": True,
            "keep_retrying": True,
            "no_tui": True,
            "dry_run": True,
            "converge": 3,
            "workers": 2,
            "max_iterations": 10,
            "max_duration": 300,
            "max_tokens": 100000,
            "idle_timeout": 1.5,
            "max_tokens_per_iteration": 4000,
            "max_turns_per_iteration": 5,
            "notify_webhook": "https://config.example.com",
        }
        expected: dict[str, Any] = {
            "model": "cli-model",
            "notify_desktop": True,
            "rollback": True,
            "keep_retrying": True,
            "no_tui": True,
            "dry_run": True,
            "converge": 3,
            "workers": 4,
            "max_iterations": 10,
            "max_duration": 600,
            "max_tokens": 100000,
            "idle_timeout": 1.5,
            "max_tokens_per_iteration": 4000,
            "max_turns_per_iteration": 5,
            "notify_webhook": "https://config.example.com",
        }
        assert apply_config_defaults(cli_kwargs, config) == expected
