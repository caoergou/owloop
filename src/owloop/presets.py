"""Agent preset registry — per-tool knowledge as data, not code.

owloop integrates coding agents through exactly two code paths:

1. **Native adapters** (``ClaudeCodeAdapter``, ``KimiCodeAdapter``) — the
   original stream-json subprocess adapters, kept for backward compatibility.
2. **ACP** (Agent Client Protocol, https://agentclientprotocol.com) — one
   ``AcpAdapter`` speaks JSON-RPC over stdio to any ACP-capable agent.

Everything tool-specific lives here as an :class:`AgentPreset` row: the launch
command, extra environment variables (e.g. Anthropic-compatible endpoints for
GLM/DeepSeek), and which project config directories a worktree needs. Adding
support for a new agent means adding one row — never a new adapter class.

Users can add their own presets in ``.owloop/agents.toml``::

    [agents.mytool]
    cmd = ["mytool", "acp"]
    env = { MYTOOL_API_KEY = "${MYTOOL_API_KEY}" }
    default_model = "mytool-large"
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_ENV_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# The co-official (Anthropic/Zed/JetBrains) ACP adapter for Claude Code. Also
# the launch vehicle for vendors whose blessed integration path is an
# Anthropic-compatible endpoint (GLM, DeepSeek) rather than their own CLI.
_CLAUDE_ACP_CMD = ["npx", "-y", "@agentclientprotocol/claude-agent-acp"]


class UnknownPresetError(ValueError):
    """Raised when an agent key does not match any builtin or user preset."""

    def __init__(self, key: str, available: list[str]) -> None:
        super().__init__(
            f"unknown agent {key!r} — available agents: {', '.join(available)}"
        )
        self.key = key
        self.available = available


class MissingEnvError(RuntimeError):
    """Raised when a preset references environment variables that are unset."""

    def __init__(self, preset_key: str, missing: list[str]) -> None:
        super().__init__(
            f"agent preset {preset_key!r} requires environment variable(s) "
            f"{', '.join(missing)} to be set"
        )
        self.preset_key = preset_key
        self.missing = missing


@dataclass(frozen=True)
class AgentPreset:
    """One integrated coding agent, described entirely as data."""

    key: str
    cmd: tuple[str, ...]
    kind: str = "acp"  # "acp" | "native"
    label: str = ""
    # Extra environment for the agent process. Values may reference the
    # user's environment via ``${VAR}`` (resolved at spawn time, never stored)
    # and the resolved model via ``{model}``.
    env: dict[str, str] = field(default_factory=dict)
    default_model: str | None = None
    # Project-level config directories a worktree needs copies of.
    config_dirs: tuple[str, ...] = (".claude",)
    # True until the preset has been validated against the real agent.
    experimental: bool = True
    notes: str = ""

    def display_label(self) -> str:
        return self.label or self.key

    def resolve_env(self, model: str | None = None) -> dict[str, str]:
        """Expand ``${VAR}`` references and the ``{model}`` placeholder.

        Raises :class:`MissingEnvError` listing every unset variable at once,
        so preflight can report them all in one pass.
        """
        resolved_model = model or self.default_model or ""
        missing: list[str] = []
        resolved: dict[str, str] = {}
        for name, template in self.env.items():
            value = template.replace("{model}", resolved_model)

            def _sub(match: re.Match[str]) -> str:
                var = match.group(1)
                got = os.environ.get(var)
                if got is None:
                    missing.append(var)
                    return ""
                return got

            resolved[name] = _ENV_REF_RE.sub(_sub, value)
        if missing:
            raise MissingEnvError(self.key, sorted(set(missing)))
        return resolved

    def required_env_vars(self) -> list[str]:
        """Names of ``${VAR}`` references across all env templates."""
        names: list[str] = []
        for template in self.env.values():
            names.extend(_ENV_REF_RE.findall(template))
        return sorted(set(names))


_BUILTIN_PRESETS: tuple[AgentPreset, ...] = (
    # -- native stream-json adapters (pre-existing, non-experimental) --------
    AgentPreset(
        key="claude",
        kind="native",
        label="Claude Code",
        cmd=("claude",),
        default_model=None,  # cli.py supplies DEFAULT_MODEL
        config_dirs=(".claude",),
        experimental=False,
        notes="claude -p --output-format stream-json (native adapter)",
    ),
    AgentPreset(
        key="kimi",
        kind="native",
        label="Kimi Code CLI",
        cmd=("kimi",),
        default_model="kimi-code/kimi-for-coding",
        config_dirs=(".claude",),
        experimental=False,
        notes="kimi --prompt --output-format stream-json (native adapter)",
    ),
    # -- ACP presets ----------------------------------------------------------
    AgentPreset(
        key="claude-acp",
        label="Claude Code (ACP)",
        cmd=tuple(_CLAUDE_ACP_CMD),
        config_dirs=(".claude",),
        notes="Co-official Anthropic/Zed/JetBrains ACP adapter",
    ),
    AgentPreset(
        key="codex",
        label="OpenAI Codex",
        cmd=("npx", "-y", "@agentclientprotocol/codex-acp"),
        config_dirs=(".codex",),
    ),
    AgentPreset(
        key="opencode",
        label="OpenCode",
        cmd=("opencode", "acp"),
        config_dirs=(".opencode",),
    ),
    AgentPreset(
        key="qoder",
        label="Qoder CLI",
        cmd=("qodercli", "acp"),
        config_dirs=(".qoder",),
        notes="requires QODER_PERSONAL_ACCESS_TOKEN for headless auth",
    ),
    AgentPreset(
        key="kiro",
        label="Kiro CLI",
        cmd=("kiro-cli", "acp"),
        config_dirs=(".kiro",),
    ),
    AgentPreset(
        key="gemini",
        label="Gemini CLI",
        cmd=("npx", "-y", "@google/gemini-cli", "--acp"),
        config_dirs=(".gemini",),
    ),
    AgentPreset(
        key="qwen",
        label="Qwen Code",
        cmd=("npx", "-y", "@qwen-code/qwen-code", "--acp"),
        config_dirs=(".qwen",),
    ),
    # -- Anthropic-compatible endpoints through the Claude ACP adapter -------
    AgentPreset(
        key="glm",
        label="GLM (Z.ai)",
        cmd=tuple(_CLAUDE_ACP_CMD),
        env={
            "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "${ZAI_API_KEY}",
            "ANTHROPIC_MODEL": "{model}",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "{model}",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": "{model}",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.7",
        },
        default_model="glm-5.2",
        config_dirs=(".claude",),
        notes="GLM Coding Plan via Anthropic-compatible endpoint; "
        "mainland endpoint: https://open.bigmodel.cn/api/anthropic",
    ),
    AgentPreset(
        key="deepseek",
        label="DeepSeek",
        cmd=tuple(_CLAUDE_ACP_CMD),
        env={
            "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "${DEEPSEEK_API_KEY}",
            "ANTHROPIC_MODEL": "{model}",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "{model}",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": "{model}",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-v4-flash",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        },
        default_model="deepseek-v4-pro",
        config_dirs=(".claude",),
        notes="DeepSeek Anthropic-compatible endpoint "
        "(legacy deepseek-chat/deepseek-reasoner deprecated 2026-07)",
    ),
)


def _load_user_presets(project_dir: Path) -> list[AgentPreset]:
    """Read user presets from ``.owloop/agents.toml`` if it exists."""
    path = project_dir / ".owloop" / "agents.toml"
    if not path.is_file():
        return []
    try:
        import tomllib
    except ImportError:  # Python 3.10: tomli is the tomllib backport
        import tomli as tomllib  # type: ignore[no-redef]
    with path.open("rb") as f:
        data = tomllib.load(f)
    presets: list[AgentPreset] = []
    for key, entry in data.get("agents", {}).items():
        if not isinstance(entry, dict) or "cmd" not in entry:
            raise ValueError(f"{path}: agent {key!r} must be a table with a 'cmd' list")
        presets.append(
            AgentPreset(
                key=key,
                kind="acp",
                label=str(entry.get("label", "")),
                cmd=tuple(str(part) for part in entry["cmd"]),
                env={str(k): str(v) for k, v in entry.get("env", {}).items()},
                default_model=entry.get("default_model"),
                config_dirs=tuple(entry.get("config_dirs", (".claude",))),
                experimental=True,
                notes=str(entry.get("notes", "user preset (.owloop/agents.toml)")),
            )
        )
    return presets


def all_presets(project_dir: Path | None = None) -> dict[str, AgentPreset]:
    """Builtin presets, with user presets from ``.owloop/agents.toml`` overriding."""
    registry = {p.key: p for p in _BUILTIN_PRESETS}
    if project_dir is not None:
        for preset in _load_user_presets(project_dir):
            registry[preset.key] = preset
    return registry


def get_preset(key: str, project_dir: Path | None = None) -> AgentPreset:
    """Look up one preset by key, raising :class:`UnknownPresetError` if absent."""
    registry = all_presets(project_dir)
    if key not in registry:
        raise UnknownPresetError(key, sorted(registry))
    return registry[key]
