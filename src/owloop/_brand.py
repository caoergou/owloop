"""Brand assets and theming for owloop.

Centralises the owl mascot (Ollie), colour palette, ASCII art, taglines and
state-aware messaging so every CLI/TUI/reporter surface stays consistent.
"""

from __future__ import annotations

import subprocess
from os import PathLike

# ── palette ──
NIGHT = "#0b1026"
DIM_BLUE = "#3a4270"
AMBER = "#d4a025"
MOON_WHITE = "#f2ecd8"
GREEN = "#8fd19e"
RED = "#e0777d"
GRAY = "#8890b3"
CYAN = "#8fb8de"
STAR_STYLE = "dim #6b74a8"

# ── mascot ──
OLLIE_NAME = "Ollie"
TAGLINE = "Your code evolves while you sleep."
OWL_EMOJI = "🦉"

# ── brand bar ──
BRAND_BAR = "✦  O W L O O P  ✦"
BRAND_BAR_ASCII = "  O W L O O P  "

# ── owl art (kept for --ascii compatibility) ──

def _normalize(art: list[str]) -> list[str]:
    width = max(len(row) for row in art)
    return [row.ljust(width) for row in art]


OWL_SMALL = _normalize([
    "   ▄▀▀▀▀▄   ",
    "  █ (o)(o)█ ",
    "  █   ▼   █ ",
    "   ▀▄▄▄▄▀   ",
    "   ▀▀▀▀▀▀   ",
])

OWL_MEDIUM = _normalize([
    "                                    ",
    "            ▄▀        ▀▄            ",
    "          ▄▀            ▀▄          ",
    "         █   (o)    (o)   █         ",
    "         █       ▼▼       █         ",
    "         █                █         ",
    "          ▀▄            ▄▀          ",
    "             ▀▄▄▄▄▄▄▄▄▀             ",
    "       ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄       ",
    "                                    ",
    "                                    ",
    "                                    ",
    "                                    ",
])

OWL_BLINK = _normalize([
    "                                    ",
    "            ▄▀        ▀▄            ",
    "          ▄▀            ▀▄          ",
    "         █   (-)    (-)   █         ",
    "         █       ▼▼       █         ",
    "         █                █         ",
    "          ▀▄            ▄▀          ",
    "             ▀▄▄▄▄▄▄▄▄▀             ",
    "       ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄       ",
    "                                    ",
    "                                    ",
    "                                    ",
    "                                    ",
])

OWL_SLEEP = _normalize([
    "                                z   ",
    "            ▄▀        ▀▄         Z  ",
    "          ▄▀            ▀▄          ",
    "         █   (-)    (-)   █         ",
    "         █       ▼▼       █         ",
    "         █                █         ",
    "          ▀▄            ▄▀          ",
    "             ▀▄▄▄▄▄▄▄▄▀             ",
    "       ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄       ",
    "                                    ",
    "                                    ",
    "                                    ",
    "                                    ",
])

OWL_FACE = _normalize([
    "  ▄▀▀▀▀▄  ",
    " █(o)(o)█ ",
    "  █ ▼ █   ",
])

# ── progress / status ──
MOON_PHASES = ["🌑", "🌒", "🌓", "🌔", "🌕"]
MOON_PHASES_FULL = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]


def moon_for_progress(done: int, total: int) -> str:
    if total <= 0:
        return MOON_PHASES[0]
    idx = min(len(MOON_PHASES) - 1, int(done / total * (len(MOON_PHASES) - 1)))
    return MOON_PHASES[idx]


SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# ── state-aware messaging ──

def status_message(phase: str, iteration: int = 0, spec_name: str = "") -> str:
    if phase == "complete":
        return f"🌅 {OLLIE_NAME} is done — time for coffee"
    if phase == "error":
        return f"✗ {OLLIE_NAME} hit a snag and stopped"
    if phase == "stuck":
        return f"💤 {OLLIE_NAME} is scratching his head, but still trying..."
    if phase == "done_signal":
        return f"🌙 Iteration {iteration} closed the loop"
    if iteration:
        base = f"{OLLIE_NAME} is hunting bugs on iteration {iteration}"
        if spec_name:
            return f"🦉 {base} · {spec_name}"
        return f"🦉 {base}..."
    return f"🦉 {OLLIE_NAME} is waking up..."


def wake_message() -> str:
    return f"{OLLIE_NAME} is waking up..."


# Stopped reasons where the user can resume work rather than merge.
_RESUME_REASONS = {
    "interrupted",
    "stalled",
    "exhausted",
    "blocked",
    "decide",
    "fix_loop_blocked",
    "max_iterations",
    "max_duration",
    "max_tokens",
}


def _default_branch(main_repo_dir: str | PathLike[str]) -> str:
    """Return the current branch of the main repo, falling back to ``main``."""
    try:
        result = subprocess.run(
            ["git", "-C", str(main_repo_dir), "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
        )
        branch = result.stdout.strip()
        if result.returncode == 0 and branch:
            return branch
    except Exception:
        pass
    return "main"


def exit_hints(
    branch: str,
    iterations: int,
    cwd: str | PathLike[str],
    main_repo_dir: str | PathLike[str],
    stopped_reason: str = "",
    report_path: str | None = None,
) -> list[str]:
    if str(cwd) == str(main_repo_dir):
        return [f"Branch: {branch}"]

    review_cmd = (
        "git log --oneline -1"
        if iterations <= 0
        else f"git log --oneline HEAD~{iterations}..HEAD"
    )

    base_branch = _default_branch(main_repo_dir)

    hints: list[str] = []
    if report_path:
        hints.append(f"Report:   {report_path}")
    hints.extend([
        f"Review:   {review_cmd}",
        f"Merge:    cd {main_repo_dir} && git checkout {base_branch} && git merge {branch}",
        f"Push:     git push origin {base_branch}",
        f"Cleanup:  git worktree remove {cwd} && git branch -d {branch}",
    ])
    if stopped_reason.lower() in _RESUME_REASONS:
        hints.append("Resume:   owloop run --resume")
    return hints


# ── ascii fallbacks ──

ASCII_OWL_SMALL = [
    "   .---.   ",
    "  /(o)(o)\\ ",
    " |   ▼   | ",
    " |  ===  | ",
    "  \\_____/ ",
]

ASCII_MOON_PHASES = ["(", "c", "C", "O", "@"]


def ascii_moon_for_progress(done: int, total: int) -> str:
    if total <= 0:
        return ASCII_MOON_PHASES[0]
    idx = min(len(ASCII_MOON_PHASES) - 1, int(done / total * (len(ASCII_MOON_PHASES) - 1)))
    return ASCII_MOON_PHASES[idx]
