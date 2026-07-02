#!/usr/bin/env python3
"""owloop TUI concept prototype (rich) — run to see the look & feel."""

import itertools
import math
import random
import time
from dataclasses import dataclass, field

from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

FPS = 4

# ── palette ──
NIGHT = "#0b1026"
DIM_BLUE = "#3a4270"
AMBER = "#d4a025"
MOON_WHITE = "#f2ecd8"
GREEN = "#8fd19e"
GRAY = "#8890b3"
STAR_STYLE = "dim #6b74a8"

MOON_PHASES = ["🌑", "🌒", "🌓", "🌔", "🌕"]


def normalize_art(art: list[str]) -> list[str]:
    width = max(len(row) for row in art)
    return [row.ljust(width) for row in art]


OWL_OPEN = normalize_art([
    " ╭─────╮ ",
    "╱ ◉   ◉ ╲",
    "│  ╰▽╯  │",
    "╰╮     ╭╯",
    " │ ║║║ │ ",
    " ╰─────╯ ",
])

OWL_BLINK = normalize_art([
    " ╭─────╮ ",
    "╱ ─   ─ ╲",
    "│  ╰▽╯  │",
    "╰╮     ╭╯",
    " │ ║║║ │ ",
    " ╰─────╯ ",
])

OWL_SLEEP = normalize_art([
    " ╭─────╮    ",
    "╱ ─   ─ ╲ z ",
    "│  ╰▽╯  │z  ",
    "╰╮     ╭╯   ",
    " │ ║║║ │    ",
    " ╰─────╯    ",
])

SCENE_W, SCENE_H = 28, 9
_star_rng = random.Random(7)
STAR_CHARS = "·∗✦⋆˙"
STAR_FIELD = [
    (
        _star_rng.randint(0, SCENE_W - 1),
        _star_rng.randint(0, SCENE_H - 1),
        _star_rng.choice(STAR_CHARS),
        _star_rng.uniform(0, math.tau),
    )
    for _ in range(18)
]


@dataclass
class AppState:
    frame: int = 0
    iteration: int = 9
    commits: int = 9
    tokens: int = 612_400
    elapsed_min: int = 182
    branch: str = "owloop/20260702"
    blink: bool = False
    next_blink: int = 10
    flash: tuple[str, str, int] | None = None
    specs: list[list[str]] = field(default_factory=lambda: [
        ["01-global-cleanup", "done"],
        ["02-service-extraction", "active"],
        ["03-type-annotations", "pending"],
        ["04-pydantic-pilot", "pending"],
    ])
    logs: list[str] = field(default_factory=lambda: [
        "owloop started — resuming from IMPLEMENTATION_PLAN.md",
        "Picked spec 02-service-extraction (priority 1, incomplete)",
        "Reading backend/app/api/ml_model.py (932 lines)",
    ])


def format_elapsed(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60:02d}m"


def add_log(state: AppState, line: str) -> None:
    state.logs.append(line)


def complete_spec(state: AppState, index: int) -> None:
    state.specs[index][1] = "done"
    if index + 1 < len(state.specs):
        state.specs[index + 1][1] = "active"
    state.commits += 1
    state.iteration += 1
    state.flash = (f"🌙 {state.specs[index][0]} complete!", f"bold {MOON_WHITE}", state.frame + 6)


def status_text(state: AppState) -> Text:
    if state.flash and state.frame < state.flash[2]:
        text, style, _ = state.flash
        return Text(text, style=style)
    done = sum(1 for _, status in state.specs if status == "done")
    if done == len(state.specs):
        return Text("🌅 All specs complete", style=f"bold {AMBER}")
    active = next((name for name, status in state.specs if status == "active"), None)
    if active:
        return Text(f"🦉 Working on {active}...", style=f"bold {AMBER}")
    return Text("🦉 Working...", style=f"bold {AMBER}")


def render_header(state: AppState) -> Panel:
    done = sum(1 for _, status in state.specs if status == "done")
    fraction = done / len(state.specs)
    moon = MOON_PHASES[min(len(MOON_PHASES) - 1, int(fraction * (len(MOON_PHASES) - 1)))]
    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(justify="right")
    grid.add_row(
        Text("Your code evolves while you sleep.", style=f"italic {GRAY}"),
        Text(f"{format_elapsed(state.elapsed_min)} elapsed", style=DIM_BLUE),
    )
    return Panel(grid, title=f"{moon} owloop", title_align="left", border_style=AMBER, style=f"on {NIGHT}")


def render_status(state: AppState) -> Panel:
    done = sum(1 for _, status in state.specs if status == "done")
    table = Table.grid(padding=(0, 1))
    table.add_column(style=f"dim {GRAY}")
    table.add_column()
    table.add_row("Iteration", Text(f"#{state.iteration}", style=f"bold {MOON_WHITE}"))
    table.add_row("Tokens", Text(f"~{state.tokens:,}", style="#8fb8de"))
    table.add_row("Specs", Text(f"{done}/{len(state.specs)} done", style=GREEN))
    table.add_row("Status", status_text(state))
    return Panel(table, title="Status", title_align="left", border_style=DIM_BLUE, style=f"on {NIGHT}")


def render_specs(state: AppState) -> Panel:
    rows = []
    for name, status in state.specs:
        if status == "done":
            rows.append(Text(f"✓ {name}", style=GREEN))
        elif status == "active":
            rows.append(Text(f"🦉 {name}", style=f"bold {AMBER}"))
        else:
            rows.append(Text(f"○ {name}", style=f"dim {GRAY}"))
    return Panel(Group(*rows), title="Specs", title_align="left", border_style=DIM_BLUE, style=f"on {NIGHT}")


def render_owl_scene(state: AppState) -> Panel:
    grid = [[" "] * SCENE_W for _ in range(SCENE_H)]
    styles = [[""] * SCENE_W for _ in range(SCENE_H)]

    for x, y, ch, phase in STAR_FIELD:
        brightness = (math.sin(state.frame * 0.5 + phase) + 1) / 2
        if brightness > 0.6:
            grid[y][x] = ch
            styles[y][x] = STAR_STYLE

    art = OWL_BLINK if state.blink else OWL_OPEN
    top = (SCENE_H - len(art)) // 2
    left = (SCENE_W - len(art[0])) // 2
    for dy, row in enumerate(art):
        for dx, ch in enumerate(row):
            if ch != " ":
                grid[top + dy][left + dx] = ch
                styles[top + dy][left + dx] = f"bold {AMBER}"

    text = Text(justify="center")
    for y in range(SCENE_H):
        for style, group in itertools.groupby(range(SCENE_W), key=lambda x: styles[y][x]):
            chars = "".join(grid[y][x] for x in group)
            text.append(chars, style=style or None)
        if y < SCENE_H - 1:
            text.append("\n")

    return Panel(
        Align.center(text, vertical="middle"),
        title="🦉",
        border_style=DIM_BLUE,
        style=f"on {NIGHT}",
        height=SCENE_H + 2,
    )


def render_activity(state: AppState) -> Panel:
    recent = state.logs[-7:]
    rows = []
    for i, line in enumerate(recent):
        is_latest = i == len(recent) - 1
        prefix = "▸" if is_latest else " "
        style = f"bold {MOON_WHITE}" if is_latest else GRAY
        rows.append(Text(f"{prefix} {line}", style=style, no_wrap=True, overflow="ellipsis"))
    return Panel(Group(*rows), title="Activity", title_align="left", border_style=DIM_BLUE, style=f"on {NIGHT}")


def render_footer(state: AppState) -> Panel:
    done = sum(1 for _, status in state.specs if status == "done")
    total = len(state.specs)
    width = 30
    filled = int(width * done / total)
    bar = Text()
    bar.append("█" * filled, style=AMBER)
    bar.append("░" * (width - filled), style=DIM_BLUE)
    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(justify="right")
    grid.add_row(bar, Text("ctrl+c to stop", style=f"dim {GRAY}"))
    return Panel(grid, border_style=DIM_BLUE, style=f"on {NIGHT}")


def build_layout() -> Layout:
    layout = Layout(name="root")
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )
    layout["left"].split(
        Layout(name="status", size=8),
        Layout(name="specs", ratio=1),
    )
    layout["right"].split(
        Layout(name="owl", size=SCENE_H + 2),
        Layout(name="activity", ratio=1),
    )
    return layout


def render_wake_frame(elapsed: float) -> Panel:
    if elapsed < 0.9:
        art, caption, border = OWL_SLEEP, "owloop awakening", DIM_BLUE
    elif elapsed < 1.6:
        art, caption, border = OWL_BLINK, "owloop awakening", DIM_BLUE
    else:
        art, caption, border = OWL_OPEN, "owloop is awake", AMBER
    dots = "." * (1 + int(elapsed * 2) % 3)
    owl_text = Text("\n".join(art), style=f"bold {AMBER}", justify="center")
    caption_text = Text(f"{caption}{dots}", style=f"italic {MOON_WHITE}", justify="center")
    body = Group(Text(""), owl_text, Text(""), caption_text)
    return Panel(body, border_style=border, style=f"on {NIGHT}", width=40, padding=(1, 2))


def run_wake_phase(live: Live, console: Console) -> None:
    console.set_window_title("owloop — awakening…")
    frame_count = int(2.6 * FPS)
    for i in range(frame_count):
        panel = render_wake_frame(i / FPS)
        live.update(Align.center(panel, vertical="middle"), refresh=True)
        time.sleep(1 / FPS)


def apply_timeline(state: AppState, frame: int) -> None:
    if frame == 4:
        add_log(state, "Extracted MLModelService.create_model()")
    elif frame == 8:
        add_log(state, "uv run ruff check backend/ → 0 errors")
    elif frame == 12:
        add_log(state, "Committed: refactor(ml_model): extract CRUD to service")
        complete_spec(state, 1)
        add_log(state, "✓ 02-service-extraction complete — <promise>DONE</promise>")
        add_log(state, "Starting spec 03: type-annotations...")
    elif frame == 16:
        add_log(state, "Reading backend/app/services/user_service.py (211 lines)")
    elif frame == 24:
        add_log(state, "⚠ No <promise>DONE</promise> found — retrying (1/3)")
        state.flash = ("💤 retrying spec 03 (1/3)", f"bold {GRAY}", frame + 6)
    elif frame == 30:
        add_log(state, "Added return types to 14 functions in user_service.py")
    elif frame == 34:
        add_log(state, "uv run mypy backend/ → 0 errors")
    elif frame == 38:
        add_log(state, "Committed: types(user_service): add return annotations")
        complete_spec(state, 2)
        add_log(state, "✓ 03-type-annotations complete — <promise>DONE</promise>")
        add_log(state, "Starting spec 04: pydantic-pilot...")
    elif frame == 46:
        add_log(state, "Migrated UserCreate schema to Pydantic v2")
    elif frame == 52:
        add_log(state, "uv run pytest backend/tests/schemas -q → 18 passed")
    elif frame == 56:
        add_log(state, "Committed: feat(schemas): pydantic v2 migration pilot")
        complete_spec(state, 3)
        add_log(state, "✓ 04-pydantic-pilot complete — <promise>DONE</promise>")
        state.flash = ("🌅 All specs complete", f"bold {AMBER}", frame + 1000)


def run_working_phase(live: Live, console: Console, layout: Layout, state: AppState) -> None:
    total_frames = 60
    for frame in range(total_frames):
        state.frame = frame
        apply_timeline(state, frame)

        progress = frame / (total_frames - 1)
        state.tokens = int(612_400 + 234_800 * progress)
        state.elapsed_min = int(182 + 25 * progress)

        if frame >= state.next_blink:
            state.blink = True
            state.next_blink = frame + random.randint(12, 16)
        else:
            state.blink = False

        layout["header"].update(render_header(state))
        layout["status"].update(render_status(state))
        layout["specs"].update(render_specs(state))
        layout["owl"].update(render_owl_scene(state))
        layout["activity"].update(render_activity(state))
        layout["footer"].update(render_footer(state))

        done = sum(1 for _, status in state.specs if status == "done")
        console.set_window_title(f"owloop — iter #{state.iteration} · {done}/{len(state.specs)} specs")

        live.update(layout, refresh=True)
        time.sleep(1 / FPS)


def render_exit_summary(state: AppState) -> Panel:
    owl = Text("\n".join(OWL_SLEEP), style=f"dim {AMBER}", justify="center")

    facts = Table.grid(padding=(0, 2))
    facts.add_column(style=f"dim {GRAY}", justify="right")
    facts.add_column(style=MOON_WHITE)
    facts.add_row("Branch", state.branch)
    facts.add_row("Specs", Text(f"{len(state.specs)}/{len(state.specs)} done", style=f"bold {GREEN}"))
    facts.add_row("Commits", str(state.commits))
    facts.add_row("Tokens", Text(f"~{state.tokens:,}", style="#8fb8de"))
    facts.add_row("Time", format_elapsed(state.elapsed_min))

    hints = Group(
        Text(f"Review:   git log --oneline HEAD~{state.commits}..", style=f"dim {GRAY}"),
        Text(f"Merge:    git merge {state.branch}", style=f"dim {GRAY}"),
        Text("Discard:  git worktree remove ../owloop-wt", style=f"dim {GRAY}"),
    )

    body = Group(
        owl,
        Text(""),
        Align.center(Text("🌅 owloop complete", style=f"bold {AMBER}")),
        Text(""),
        Align.center(facts),
        Text(""),
        Align.center(hints),
    )
    return Panel(body, border_style=AMBER, style=f"on {NIGHT}", padding=(1, 4), width=56)


def run_exit_phase(live: Live, console: Console, state: AppState) -> None:
    console.set_window_title("owloop — complete 🌅")
    panel = render_exit_summary(state)
    frame_count = int(3.5 * FPS)
    for i in range(frame_count):
        panel.border_style = f"dim {AMBER}" if i < 2 else AMBER
        live.update(Align.center(panel, vertical="middle"), refresh=True)
        time.sleep(1 / FPS)


def main() -> None:
    console = Console()
    state = AppState()
    layout = build_layout()

    try:
        with Live(Text(""), console=console, screen=True, auto_refresh=False) as live:
            run_wake_phase(live, console)
            run_working_phase(live, console, layout, state)
            run_exit_phase(live, console, state)
    except KeyboardInterrupt:
        pass

    console.print(f"[bold {AMBER}]owloop[/] stopped — concept prototype, no real work was performed.")


if __name__ == "__main__":
    main()
