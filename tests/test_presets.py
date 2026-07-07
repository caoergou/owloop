"""Preset registry tests — builtin table, env expansion, user agents.toml."""

from __future__ import annotations

from pathlib import Path

import pytest

from owloop.adapters import ClaudeCodeAdapter, KimiCodeAdapter, get_adapter
from owloop.presets import (
    AgentPreset,
    MissingEnvError,
    UnknownPresetError,
    all_presets,
    get_preset,
)

REQUESTED_AGENTS = ["claude", "codex", "opencode", "qoder", "kimi", "glm", "deepseek", "kiro"]


def test_builtin_registry_covers_requested_agents() -> None:
    registry = all_presets()
    for key in REQUESTED_AGENTS:
        assert key in registry, f"missing builtin preset: {key}"


def test_native_presets_are_marked_native_and_stable() -> None:
    registry = all_presets()
    for key in ("claude", "kimi"):
        assert registry[key].kind == "native"
        assert not registry[key].experimental


def test_get_preset_unknown_key_lists_available() -> None:
    with pytest.raises(UnknownPresetError, match="unknown agent 'nope'.*claude"):
        get_preset("nope")


def test_resolve_env_expands_var_references(monkeypatch) -> None:
    monkeypatch.setenv("OWLOOP_TEST_KEY", "sk-123")
    preset = AgentPreset(key="t", cmd=("x",), env={"AUTH": "${OWLOOP_TEST_KEY}"})
    assert preset.resolve_env() == {"AUTH": "sk-123"}


def test_resolve_env_reports_all_missing_vars(monkeypatch) -> None:
    monkeypatch.delenv("OWLOOP_TEST_A", raising=False)
    monkeypatch.delenv("OWLOOP_TEST_B", raising=False)
    preset = AgentPreset(
        key="t", cmd=("x",), env={"A": "${OWLOOP_TEST_A}", "B": "${OWLOOP_TEST_B}"}
    )
    with pytest.raises(MissingEnvError) as exc_info:
        preset.resolve_env()
    assert exc_info.value.missing == ["OWLOOP_TEST_A", "OWLOOP_TEST_B"]


def test_resolve_env_substitutes_model_placeholder() -> None:
    preset = AgentPreset(
        key="t", cmd=("x",), env={"MODEL": "{model}"}, default_model="default-model"
    )
    assert preset.resolve_env() == {"MODEL": "default-model"}
    assert preset.resolve_env(model="override") == {"MODEL": "override"}


def test_glm_and_deepseek_presets_point_at_official_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("ZAI_API_KEY", "zai-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")

    glm = get_preset("glm").resolve_env()
    assert glm["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
    assert glm["ANTHROPIC_AUTH_TOKEN"] == "zai-key"
    assert glm["ANTHROPIC_MODEL"] == "glm-5.2"

    deepseek = get_preset("deepseek").resolve_env()
    assert deepseek["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert deepseek["ANTHROPIC_AUTH_TOKEN"] == "ds-key"
    assert deepseek["ANTHROPIC_MODEL"] == "deepseek-v4-pro"
    # Legacy model ids are deprecated as of 2026-07; make sure they never creep back.
    assert "deepseek-chat" not in deepseek.values()
    assert "deepseek-reasoner" not in deepseek.values()


def test_required_env_vars_lists_references() -> None:
    assert get_preset("glm").required_env_vars() == ["ZAI_API_KEY"]
    assert get_preset("claude").required_env_vars() == []


def test_user_presets_load_and_override(tmp_path: Path) -> None:
    owloop_dir = tmp_path / ".owloop"
    owloop_dir.mkdir()
    (owloop_dir / "agents.toml").write_text(
        """
[agents.mytool]
cmd = ["mytool", "acp"]
label = "My Tool"
default_model = "mytool-large"
env = { MYTOOL_KEY = "${MYTOOL_KEY}" }
config_dirs = [".mytool"]

[agents.glm]
cmd = ["glm-custom", "acp"]
""",
        encoding="utf-8",
    )

    registry = all_presets(tmp_path)
    assert registry["mytool"].cmd == ("mytool", "acp")
    assert registry["mytool"].default_model == "mytool-large"
    assert registry["mytool"].config_dirs == (".mytool",)
    assert registry["mytool"].experimental
    # User presets override builtins with the same key.
    assert registry["glm"].cmd == ("glm-custom", "acp")


def test_user_preset_without_cmd_is_rejected(tmp_path: Path) -> None:
    owloop_dir = tmp_path / ".owloop"
    owloop_dir.mkdir()
    (owloop_dir / "agents.toml").write_text("[agents.broken]\nlabel = 'x'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="broken"):
        all_presets(tmp_path)


def test_get_adapter_resolves_native_and_acp() -> None:
    from owloop.acp import AcpAdapter

    assert isinstance(get_adapter("claude"), ClaudeCodeAdapter)
    assert isinstance(get_adapter("kimi"), KimiCodeAdapter)

    adapter = get_adapter("codex")
    assert isinstance(adapter, AcpAdapter)
    assert adapter.preset.key == "codex"


@pytest.mark.parametrize(
    ("agent", "model", "expected"),
    [
        ("claude", "claude-opus-4-8", "claude-opus-4-8"),
        ("glm", None, "glm-5.2"),
        ("glm", "glm-4.7", "glm-4.7"),
    ],
)
def test_get_adapter_model_defaults(agent: str, model: str | None, expected: str) -> None:
    adapter = get_adapter(agent, model=model)
    assert getattr(adapter, "model", None) == expected


def test_get_adapter_claude_falls_back_to_default_model() -> None:
    assert getattr(get_adapter("claude", model=None), "model", None)
