"""Brand assets and theming for owloop.

Centralises the owl mascot (Ollie), colour palette, ASCII art, taglines and
state-aware messaging so every CLI/TUI/reporter surface stays consistent.
"""

from __future__ import annotations

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

# ── owl art (normalised to consistent width) ──

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

BRAND_BAR = "✦  O W L O O P  ✦"

# ── progress / status ──
MOON_PHASES = ["🌑", "🌒", "🌓", "🌔", "🌕"]


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


def exit_hints(branch: str, iterations: int, cwd: str | PathLike[str], main_repo_dir: str | PathLike[str]) -> list[str]:
    hints = [f"Branch: {branch}"]
    if str(cwd) != str(main_repo_dir):
        hints = [
            f"Review:  git log --oneline HEAD~{iterations}..HEAD",
            f"Merge:   cd {main_repo_dir} && git merge {branch}",
            f"Discard: git worktree remove {cwd}",
        ]
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
