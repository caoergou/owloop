(function () {
  "use strict";

  const output = document.getElementById("terminal-output");
  const inputLine = document.getElementById("terminal-input-line");
  const typed = document.getElementById("terminal-typed");
  const status = document.getElementById("terminal-status");
  const copyBtn = document.querySelector(".copy-btn");

  if (!output || !inputLine || !typed) return;

  const typeSpeed = 20;
  const linePause = 380;
  const fastPause = 120;

  let timeoutId = null;
  let running = false;

  function sleep(ms) {
    return new Promise((resolve) => {
      timeoutId = window.setTimeout(resolve, ms);
    });
  }

  function clearTerminal() {
    output.innerHTML = "";
    typed.textContent = "";
    inputLine.style.display = "none";
    if (status) {
      status.textContent = "● running";
      status.style.color = "var(--success)";
    }
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function appendLine(content, className) {
    const line = document.createElement("span");
    line.className = "line" + (className ? " " + className : "");
    line.innerHTML = content;
    output.appendChild(line);
    scrollToBottom();
    return line;
  }

  function appendPlain(text, className) {
    const line = document.createElement("span");
    line.className = "line" + (className ? " " + className : "");
    line.textContent = text;
    output.appendChild(line);
    scrollToBottom();
  }

  function appendPrompt(cmd) {
    appendLine(
      `<span class="prompt">$</span> <span class="cmd">${escapeHtml(cmd)}</span>`,
      "cmd-line"
    );
  }

  function appendBlock(text, className) {
    const block = document.createElement("pre");
    block.className = "tui-block" + (className ? " " + className : "");
    block.textContent = text;
    output.appendChild(block);
    scrollToBottom();
  }

  function scrollToBottom() {
    const body = output.closest(".terminal-body");
    if (body) body.scrollTop = body.scrollHeight;
  }

  async function typeCommand(cmd) {
    inputLine.style.display = "flex";
    typed.textContent = "";
    for (let i = 0; i < cmd.length; i++) {
      typed.textContent += cmd[i];
      await sleep(typeSpeed);
    }
    await sleep(fastPause);
    inputLine.style.display = "none";
    appendPrompt(cmd);
  }

  const tuiFrames = [
`┌─────────────────────────────────────────────┐
│  🦉 owloop  ·  build mode                   │
│                                             │
│     ▄▄████▄▄                                │
│    ██ ◉  ◉ ██  ∞                            │
│   ███  ╰▽╯  ███                             │
│                                             │
│  Specs: 3      Done: 0      Iteration: 1    │
│  Current: 001-fix-lint.md                   │
│  [⠋] running acceptance criteria...         │
└─────────────────────────────────────────────┘`,
`┌─────────────────────────────────────────────┐
│  🦉 owloop  ·  build mode                   │
│                                             │
│     ▄▄████▄▄                                │
│    ██ ◉  ◉ ██  ∞                            │
│   ███  ╰▽╯  ███                             │
│                                             │
│  Specs: 3      Done: 1      Iteration: 2    │
│  Current: 002-add-types.md                  │
│  [⠙] running acceptance criteria...         │
└─────────────────────────────────────────────┘`,
`┌─────────────────────────────────────────────┐
│  🦉 owloop  ·  build mode                   │
│                                             │
│     ▄▄████▄▄                                │
│    ██ ◉  ◉ ██  ∞                            │
│   ███  ╰▽╯  ███                             │
│                                             │
│  Specs: 3      Done: 2      Iteration: 3    │
│  Current: 003-unify-errors.md               │
│  [⠹] running acceptance criteria...         │
└─────────────────────────────────────────────┘`,
`┌─────────────────────────────────────────────┐
│  🦉 owloop  ·  build mode                   │
│                                             │
│     ▄▄████▄▄                                │
│    ██ ◉  ◉ ██  ∞                            │
│   ███  ╰▽╯  ███                             │
│                                             │
│  Specs: 3      Done: 3      Iteration: 3    │
│                                             │
│  🌅 Complete. 3 specs done · 0 failures     │
└─────────────────────────────────────────────┘`,
  ];

  async function showTuiFrame(idx) {
    const existing = output.querySelectorAll(".tui-block");
    existing.forEach((el) => el.remove());
    appendBlock(tuiFrames[idx], "tui-frame");
  }

  async function runAnimation() {
    if (running && timeoutId) {
      window.clearTimeout(timeoutId);
      timeoutId = null;
    }
    running = true;
    clearTerminal();

    // 1. Project context
    await typeCommand("cd ~/projects/legacy-api");
    await sleep(linePause);

    await typeCommand("ls specs/");
    appendPlain("001-fix-lint.md      002-add-types.md     003-unify-errors.md", "output");
    await sleep(linePause);

    // 2. Start the loop
    await typeCommand("owloop run");
    await sleep(fastPause);

    appendPlain("🦉 Ollie is waking up...", "dim");
    appendPlain("→ worktree: /project-owloop-wt/owloop-2026-07-03", "dim");
    appendPlain("→ model: claude-sonnet-5", "dim");
    await sleep(linePause);

    // 3. TUI frames with iteration detail
    await showTuiFrame(0);
    await sleep(900);
    appendLine(
      `<span class="success">✓</span> <span class="dim">001-fix-lint.md</span> · ruff + pytest passed · committed`,
      "output"
    );
    await sleep(linePause);

    await showTuiFrame(1);
    await sleep(900);
    appendLine(
      `<span class="success">✓</span> <span class="dim">002-add-types.md</span> · pyright + pytest passed · committed`,
      "output"
    );
    await sleep(linePause);

    await showTuiFrame(2);
    await sleep(900);
    appendLine(
      `<span class="success">✓</span> <span class="dim">003-unify-errors.md</span> · pytest passed · committed`,
      "output"
    );
    await sleep(linePause);

    await showTuiFrame(3);
    await sleep(linePause * 1.5);

    // 4. Morning review
    appendPlain("", "blank");
    await typeCommand("git diff --stat HEAD~3..HEAD");
    appendBlock(
` src/owloop/errors.py   |  42 +++++++
 src/owloop/handlers.py |  88 +++++++++++
 src/owloop/types.py    | 156 ++++++++++++++++++
 tests/test_errors.py   |  34 +++++
 4 files changed, 320 insertions(+), 0 deletions(-)`,
      "diff"
    );
    await sleep(linePause);

    await typeCommand("owloop report");
    appendPlain("🌅 Report generated: logs/owloop_report.html", "dawn");

    if (status) {
      status.textContent = "● complete";
      status.style.color = "var(--amber-bright)";
    }

    running = false;
  }

  const terminal = document.querySelector(".terminal");
  if (terminal) {
    terminal.addEventListener("click", () => {
      if (!running) runAnimation();
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const text = copyBtn.dataset.copy;
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.classList.add("copied");
        window.setTimeout(() => copyBtn.classList.remove("copied"), 1500);
      } catch {
        // ignore
      }
    });
  }

  if ("requestIdleCallback" in window) {
    requestIdleCallback(runAnimation, { timeout: 500 });
  } else {
    window.setTimeout(runAnimation, 100);
  }
})();
