"""Rich full-screen TUI for `owloop run` — driven by OwloopEngine events.

Visual design based on prototypes/tui_concept.py, but wired to real engine
state instead of a scripted timeline.
"""

from __future__ import annotations

import itertools
import math
import random
import threading
import time
from dataclasses import dataclass, field

from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from owloop.engine import RunSummary

NIGHT = "#0b1026"
DIM_BLUE = "#3a4270"
AMBER = "#d4a025"
MOON_WHITE = "#f2ecd8"
GREEN = "#8fd19e"
RED = "#e0777d"
GRAY = "#8890b3"
STAR_STYLE = "dim #6b74a8"

MOON_PHASES = ["🌑", "🌒", "🌓", "🌔", "🌕"]


def _normalize(art: list[str]) -> list[str]:
    width = max(len(row) for row in art)
    return [row.ljust(width) for row in art]


OWL_OPEN = _normalize([
    "    ▄▄████▄▄   ",
    "   ██ ◉  ◉ ██  ",
    "  ███  ╰▽╯  ███",
    "   ██ ╭──╮ ██  ",
    "    ▀█ ║║║ █▀  ",
    "     ▀██▄▄██▀  ",
    "      ╱╲  ╱╲   ",
])

OWL_BLINK = _normalize([
    "    ▄▄████▄▄   ",
    "   ██ ─  ─ ██  ",
    "  ███  ╰▽╯  ███",
    "   ██ ╭──╮ ██  ",
    "    ▀█ ║║║ █▀  ",
    "     ▀██▄▄██▀  ",
    "      ╱╲  ╱╲   ",
])

OWL_SLEEP = _normalize([
    "    ▄▄████▄▄  z ",
    "   ██ ─  ─ ██ Z ",
    "  ███  ╰▽╯  ███ ",
    "   ██ ╭──╮ ██   ",
    "    ▀█ ║║║ █▀   ",
    "     ▀██▄▄██▀   ",
    "      ╱╲  ╱╲    ",
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


def _format_elapsed(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


@dataclass
class AppState:
    mode: str = "build"
    model: str = ""
    branch: str = ""
    cwd: str = ""
    main_repo_dir: str = ""
    max_iterations: int = 0
    iteration: int = 0
    specs: list[dict] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    start_time: float = 0.0
    blink: bool = False
    next_blink: float = 0.0
    phase: str = "starting"  # starting|working|stuck|done_signal|complete|error
    flash: tuple[str, str, float] | None = None
    done: bool = False
    stopped_reason: str = ""
    _spinner: str = "⠋"


class OwloopTUI:
    """Full-screen Live TUI. Use as a context manager around engine.run()."""

    def __init__(self) -> None:
        self.console = Console()
        self.state = AppState(start_time=time.monotonic(), next_blink=time.monotonic() + 5)
        self.layout = self._build_layout()
        self.live = Live(
            self.layout, console=self.console, screen=True, auto_refresh=False
        )
        self._lock = threading.Lock()
        self._stop_ticker = threading.Event()
        self._ticker: threading.Thread | None = None
        self._live_started = False
        self._paused = False

    # ── lifecycle ──

    def __enter__(self) -> "OwloopTUI":
        self.live.__enter__()
        self._live_started = True
        self._render()
        self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
        self._ticker.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop_ticker.set()
        if self._ticker:
            self._ticker.join(timeout=1)
        if self._live_started:
            self.live.__exit__(*exc)
            self._live_started = False

    def _tick_loop(self) -> None:
        spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        frame_idx = 0
        while not self._stop_ticker.wait(0.25):
            with self._lock:
                now = time.monotonic()
                # owl blink animation
                if now >= self.state.next_blink:
                    self.state.blink = not self.state.blink
                    self.state.next_blink = now + (0.3 if self.state.blink else random.uniform(3, 7))
                # working spinner — show elapsed time so user knows it's alive
                if self.state.phase == "working":
                    frame_idx = (frame_idx + 1) % len(spinner_frames)
                    self.state._spinner = spinner_frames[frame_idx]
                self._render()

    # ── engine event handling ──

    # Events after which the engine may call the blocking input() — the Live
    # full-screen display must be torn down first or the prompt is invisible
    # (and its echo fights the next screen refresh).
    PROMPT_MESSAGES = {
        "worktree_prompt": "建议在独立 worktree 中运行以保护主仓库。是否自动创建？(Y/n)",
        "dirty_workspace_warning": (
            "⚠ 工作区有未提交的修改，这些修改不会出现在 worktree 中。\n"
            "   建议先 commit 或 stash 后再运行 owloop。\n"
            "   继续运行？(y/N)"
        ),
    }

    def on_event(self, kind: str, data: dict) -> None:
        if self._paused:
            self.live.start()
            self._paused = False

        with self._lock:
            self._handle(kind, data)
            self._render()

        if kind in self.PROMPT_MESSAGES:
            self.live.stop()
            self._paused = True
            self.console.print(self.PROMPT_MESSAGES[kind])

    def _log(self, line: str) -> None:
        self.state.logs.append(line)
        if len(self.state.logs) > 300:
            self.state.logs = self.state.logs[-300:]

    def _flash(self, text: str, style: str, seconds: float = 3.0) -> None:
        self.state.flash = (text, style, time.monotonic() + seconds)

    def _handle(self, kind: str, data: dict) -> None:
        s = self.state

        if kind == "session_info":
            s.mode = data["mode"]
            s.model = data["model"]
            s.branch = data["branch"]
            s.cwd = data["cwd"]
            s.main_repo_dir = data["main_repo_dir"]
            s.max_iterations = data["max_iterations"]
            s.specs = data["specs"]
            self._log(f"owloop 启动 — 模式 {s.mode} · 模型 {s.model} · 分支 {s.branch}")
            if data["has_plan"]:
                self._log("发现 IMPLEMENTATION_PLAN.md，将优先使用")
            elif data["first_incomplete"]:
                self._log(f"下一个未完成 spec: {data['first_incomplete']}")
        elif kind == "worktree_already_active":
            self._log(f"已在独立 worktree 中运行: {data['path']}")
        elif kind == "worktree_skipped":
            self._log("未使用 worktree 隔离，直接在当前目录运行")
        elif kind == "worktree_prompt":
            self._log("建议创建独立 worktree（等待终端输入...）")
        elif kind == "worktree_auto_created":
            self._log("非交互环境，自动创建独立 worktree 以保护主仓库")
        elif kind == "worktree_created" or kind == "worktree_branch_reused":
            s.cwd = data["path"]
            self._log(f"✓ 已创建并切换到 worktree: {data['path']}")
        elif kind == "worktree_reused":
            s.cwd = data["path"]
            self._log(f"目录已存在，直接进入: {data['path']}")
        elif kind == "worktree_declined":
            self._log("继续在当前目录运行（未使用 worktree）")
        elif kind == "worktree_failed":
            self._log("✗ 创建 worktree 失败，继续在当前目录运行")
        elif kind == "all_specs_complete":
            s.phase = "complete"
            s.done = True
            self._log(f"全部 {data['spec_count']} 个 spec 均已完成，无事可做")
        elif kind == "iteration_start":
            s.iteration = data["iteration"]
            s.phase = "working"
            self._log(f"── 第 {s.iteration} 轮迭代开始 ──")
        elif kind == "output_line":
            line = data["line"].strip()
            if line:
                self._log(line)
        elif kind == "done_signal":
            s.phase = "done_signal"
            self._log(f"✓ 检测到完成信号: {data['signal']}")
            self._flash(f"🌙 第 {s.iteration} 轮完成！", f"bold {MOON_WHITE}")
        elif kind == "no_done_signal":
            self._log("⚠ 未检测到完成信号，将在下一轮重试")
        elif kind == "agent_failed":
            self._log(f"✗ Agent 执行失败（returncode={data['returncode']}）")
        elif kind == "agent_timeout":
            self._log(f"⏱ 第 {data['iteration']} 轮空闲超时，Agent 可能挂起，已终止")
        elif kind == "preflight_failed":
            s.phase = "error"
            for issue in data["issues"]:
                self._log(f"✗ {issue}")
        elif kind == "dirty_workspace_warning":
            self._log("⚠ 工作区有未提交的修改，这些修改不会出现在 worktree 中")
        elif kind == "dirty_workspace_declined":
            s.phase = "error"
            self._log("已取消 — 请先 commit 或 stash 后再运行 owloop")
        elif kind == "dirty_workspace_noninteractive_continue":
            self._log("非交互环境，忽略未提交修改警告，继续运行")
        elif kind == "claude_config_copied":
            self._log(f"已复制 .claude/ 配置到 worktree: {data['path']}")
        elif kind == "stuck_warning":
            s.phase = "stuck"
            self._log(f"💤 已连续 {data['consecutive_failures']} 轮未完成，Agent 可能卡住了")
            self._flash("💤 卡住了，继续重试...", f"bold {GRAY}")
        elif kind == "push_retry":
            self._log(f"推送失败，创建远程分支 {data['branch']}...")
        elif kind == "iteration_end":
            if "specs" in data:
                s.specs = data["specs"]
            s.phase = "working"
        elif kind == "plan_complete":
            s.done = True
            s.phase = "complete"
            self._log("规划完成！运行 'owloop run' 开始构建")
            self._flash("🌅 规划完成", f"bold {AMBER}")
        elif kind == "interrupted":
            s.phase = "error"
            self._log("已停止（Ctrl+C）")

    # ── rendering ──

    def _status_text(self) -> Text:
        s = self.state
        if s.flash and time.monotonic() < s.flash[2]:
            text, style, _ = s.flash
            return Text(text, style=style)
        if s.phase == "complete":
            return Text("🌅 运行完成", style=f"bold {AMBER}")
        if s.phase == "error":
            return Text("✗ 已停止", style=f"bold {RED}")
        if s.phase == "stuck":
            return Text("💤 可能卡住了...", style=f"bold {GRAY}")
        if s.phase == "done_signal":
            return Text(f"🌙 第 {s.iteration} 轮完成", style=f"bold {MOON_WHITE}")
        if s.iteration:
            elapsed = time.monotonic() - s.start_time
            iter_elapsed = _format_elapsed(elapsed)
            spinner = getattr(s, '_spinner', '⠋')
            return Text(f"{spinner} 第 {s.iteration} 轮进行中... ({iter_elapsed})", style=f"bold {AMBER}")
        return Text("🦉 启动中...", style=f"bold {AMBER}")

    def _render_header(self) -> Panel:
        s = self.state
        done = sum(1 for spec in s.specs if spec.get("done"))
        total = len(s.specs) or 1
        moon = MOON_PHASES[min(len(MOON_PHASES) - 1, int(done / total * (len(MOON_PHASES) - 1)))]
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(justify="right")
        grid.add_row(
            Text("Your code evolves while you sleep.", style=f"italic {GRAY}"),
            Text(f"{_format_elapsed(time.monotonic() - s.start_time)} elapsed", style=DIM_BLUE),
        )
        return Panel(grid, title=f"{moon} owloop", title_align="left", border_style=AMBER, style=f"on {NIGHT}")

    def _render_status(self) -> Panel:
        s = self.state
        done = sum(1 for spec in s.specs if spec.get("done"))
        table = Table.grid(padding=(0, 1))
        table.add_column(style=f"dim {GRAY}")
        table.add_column()
        table.add_row("模式", Text(s.mode, style=f"bold {MOON_WHITE}"))
        table.add_row("模型", Text(s.model or "—", style="#8fb8de"))
        table.add_row("迭代", Text(f"#{s.iteration}" + (f" / {s.max_iterations}" if s.max_iterations else ""), style=f"bold {MOON_WHITE}"))
        table.add_row("分支", Text(s.branch or "—", style=GREEN))
        if s.specs:
            table.add_row("Specs", Text(f"{done}/{len(s.specs)} done", style=GREEN))
        table.add_row("状态", self._status_text())
        return Panel(table, title="Status", title_align="left", border_style=DIM_BLUE, style=f"on {NIGHT}")

    def _render_specs(self) -> Panel:
        s = self.state
        if not s.specs:
            body = Text("(无 spec)", style=f"dim {GRAY}")
        else:
            rows = []
            first_pending_marked = False
            for spec in s.specs:
                if spec.get("done"):
                    rows.append(Text(f"✓ {spec['name']}", style=GREEN))
                elif not first_pending_marked:
                    first_pending_marked = True
                    rows.append(Text(f"🦉 {spec['name']}", style=f"bold {AMBER}"))
                else:
                    rows.append(Text(f"○ {spec['name']}", style=f"dim {GRAY}"))
            body = Group(*rows)
        return Panel(body, title="Specs", title_align="left", border_style=DIM_BLUE, style=f"on {NIGHT}")

    def _render_owl_scene(self) -> Panel:
        s = self.state
        grid = [[" "] * SCENE_W for _ in range(SCENE_H)]
        styles = [[""] * SCENE_W for _ in range(SCENE_H)]
        t = time.monotonic() - s.start_time

        for x, y, ch, phase in STAR_FIELD:
            brightness = (math.sin(t * 0.5 + phase) + 1) / 2
            if brightness > 0.6:
                grid[y][x] = ch
                styles[y][x] = STAR_STYLE

        if s.phase == "complete" or s.phase == "error":
            art = OWL_SLEEP
        else:
            art = OWL_BLINK if s.blink else OWL_OPEN
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

    def _render_activity(self) -> Panel:
        recent = self.state.logs[-7:]
        rows = []
        for i, line in enumerate(recent):
            is_latest = i == len(recent) - 1
            prefix = "▸" if is_latest else " "
            style = f"bold {MOON_WHITE}" if is_latest else GRAY
            rows.append(Text(f"{prefix} {line}", style=style, no_wrap=True, overflow="ellipsis"))
        # When working but no recent output, show a reassuring message
        if self.state.phase == "working" and self.state.iteration > 0:
            elapsed = time.monotonic() - self.state.start_time
            spinner = getattr(self.state, '_spinner', '⠋')
            rows.append(Text(
                f"  {spinner} claude -p 运行中，输出将在本轮结束时显示...",
                style=f"dim italic {GRAY}", no_wrap=True
            ))
        return Panel(Group(*rows) if rows else Text(""), title="Activity", title_align="left", border_style=DIM_BLUE, style=f"on {NIGHT}")

    def _render_footer(self) -> Panel:
        s = self.state
        done = sum(1 for spec in s.specs if spec.get("done"))
        total = len(s.specs) or 1
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

    def _build_layout(self) -> Layout:
        layout = Layout(name="root")
        layout.split(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )
        layout["body"].split_row(Layout(name="left"), Layout(name="right"))
        layout["left"].split(Layout(name="status", size=9), Layout(name="specs", ratio=1))
        layout["right"].split(Layout(name="owl", size=SCENE_H + 2), Layout(name="activity", ratio=1))
        return layout

    def _render(self) -> None:
        if self._paused:
            return
        self.layout["header"].update(self._render_header())
        self.layout["status"].update(self._render_status())
        self.layout["specs"].update(self._render_specs())
        self.layout["owl"].update(self._render_owl_scene())
        self.layout["activity"].update(self._render_activity())
        self.layout["footer"].update(self._render_footer())
        self.live.refresh()

    # ── exit summary (printed to normal scrollback, after Live has closed) ──

    FAILED_REASONS = {"preflight_failed", "dirty_workspace_declined"}

    def print_exit_summary(self, summary: RunSummary) -> None:
        s = self.state
        failed = summary.stopped_reason in self.FAILED_REASONS

        if failed:
            owl = Text("\n".join(OWL_SLEEP), style=f"dim {RED}", justify="center")
            lines = [Align.center(Text("✗ owloop 未启动", style=f"bold {RED}")), Text("")]
            for issue in summary.issues or []:
                lines.append(Align.center(Text(f"· {issue}", style=f"dim {GRAY}")))
            body = Group(owl, Text(""), *lines)
            self.console.print(Panel(body, border_style=RED, style=f"on {NIGHT}", padding=(1, 4), width=56))
            return

        elapsed = time.monotonic() - s.start_time
        owl = Text("\n".join(OWL_SLEEP), style=f"dim {AMBER}", justify="center")

        facts = Table.grid(padding=(0, 2))
        facts.add_column(style=f"dim {GRAY}", justify="right")
        facts.add_column(style=MOON_WHITE)
        facts.add_row("分支", summary.branch)
        if s.specs:
            done = sum(1 for spec in s.specs if spec.get("done"))
            facts.add_row("Specs", Text(f"{done}/{len(s.specs)} done", style=f"bold {GREEN}"))
        facts.add_row("迭代", str(summary.iterations))
        facts.add_row("耗时", _format_elapsed(elapsed))

        hints_lines = [Text(f"分支: {summary.branch}", style=f"dim {GRAY}")]
        if summary.cwd != summary.main_repo_dir:
            hints_lines = [
                Text(f"审查: git log --oneline HEAD~{summary.iterations}..HEAD", style=f"dim {GRAY}"),
                Text(f"合并: cd {summary.main_repo_dir} && git merge {summary.branch}", style=f"dim {GRAY}"),
                Text(f"丢弃: git worktree remove {summary.cwd}", style=f"dim {GRAY}"),
            ]

        body = Group(
            owl,
            Text(""),
            Align.center(Text("🌅 owloop complete", style=f"bold {AMBER}")),
            Text(""),
            Align.center(facts),
            Text(""),
            Align.center(Group(*hints_lines)),
        )
        self.console.print(Panel(body, border_style=AMBER, style=f"on {NIGHT}", padding=(1, 4), width=56))
