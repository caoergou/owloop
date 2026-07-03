(function () {
  "use strict";

  const output = document.getElementById("terminal-output");
  const inputLine = document.getElementById("terminal-input-line");
  const typed = document.getElementById("terminal-typed");
  const status = document.getElementById("terminal-status");
  const copyBtn = document.querySelector(".copy-btn");

  if (!output || !inputLine || !typed) return;

  // Rich terminal frames: each frame is either a string (typed line) or an object
  // { html: "...", delay: ms } for lines rendered instantly with markup.
  const frames = [
    { type: "input", text: "owloop run --max-tokens 200000" },
    { type: "output", text: "🦉 Ollie is waking up...", delay: 300 },
    { type: "output", text: "→ worktree: /project-owloop-wt/owloop-2026-07-03", delay: 180 },
    { type: "output", text: "→ model: claude-sonnet-5", delay: 180 },
    { type: "output", text: "→ specs: 3 incomplete", delay: 180 },
    { type: "blank" },
    { type: "output", text: "Iteration 1 · 001-fix-lint.md", className: "iteration" },
    { type: "cmd", text: "uv run ruff check src/ tests/" },
    { type: "output", text: "All checks passed.", className: "success" },
    { type: "cmd", text: "uv run pytest -q" },
    { type: "output", text: "14 passed in 0.12s", className: "success" },
    { type: "promise", text: "<promise>DONE</promise>" },
    { type: "output", text: "✓ committed 6 files", className: "success" },
    { type: "blank" },
    { type: "output", text: "Iteration 2 · 002-add-types.md", className: "iteration" },
    { type: "cmd", text: "uv run pyright src/owloop" },
    { type: "output", text: "0 errors, 0 warnings", className: "success" },
    { type: "cmd", text: "uv run pytest -q" },
    { type: "output", text: "14 passed in 0.11s", className: "success" },
    { type: "promise", text: "<promise>DONE</promise>" },
    { type: "output", text: "✓ committed 12 files", className: "success" },
    { type: "blank" },
    { type: "output", text: "Iteration 3 · 003-unify-errors.md", className: "iteration" },
    { type: "cmd", text: "uv run pytest tests/test_errors.py -q" },
    { type: "output", text: "8 passed in 0.08s", className: "success" },
    { type: "promise", text: "<promise>DONE</promise>" },
    { type: "output", text: "✓ committed 4 files", className: "success" },
    { type: "blank" },
    { type: "dawn", text: "🌅 Complete. 3 specs done · 0 failures · 12.4k tokens" },
    { type: "output", text: "→ report: logs/owloop_report.html", delay: 180 },
    { type: "output", text: "→ branch: owloop/2026-07-03", delay: 180 },
  ];

  const typeSpeed = 22;
  const linePause = 420;
  const fastPause = 160;

  let timeoutId = null;
  let running = false;

  function clearTerminal() {
    output.innerHTML = "";
    typed.textContent = "";
    inputLine.style.display = "none";
    if (status) {
      status.textContent = "● running";
      status.style.color = "var(--success)";
    }
  }

  function sleep(ms) {
    return new Promise((resolve) => {
      timeoutId = window.setTimeout(resolve, ms);
    });
  }

  function makeLine(content, className) {
    const line = document.createElement("span");
    line.className = "line" + (className ? " " + className : "");
    line.innerHTML = content;
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
    const line = makeLine(
      `<span class="prompt">$</span> <span class="cmd">${escapeHtml(cmd)}</span>`,
      "cmd-line"
    );
    output.appendChild(line);
    scrollToBottom();
  }

  function appendPromise(text) {
    const line = makeLine(
      `<span class="code">${escapeHtml(text)}</span>`,
      "promise-line"
    );
    output.appendChild(line);
    scrollToBottom();
  }

  function appendDawn(text) {
    const line = makeLine(escapeHtml(text), "dawn");
    output.appendChild(line);
    scrollToBottom();
  }

  function scrollToBottom() {
    const body = output.closest(".terminal-body");
    if (body) body.scrollTop = body.scrollHeight;
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
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

  async function runAnimation() {
    if (running) {
      if (timeoutId) window.clearTimeout(timeoutId);
      timeoutId = null;
    }
    running = true;
    clearTerminal();

    for (const frame of frames) {
      if (frame.type === "blank") {
        const spacer = document.createElement("span");
        spacer.className = "line";
        spacer.innerHTML = "&nbsp;";
        output.appendChild(spacer);
        scrollToBottom();
        await sleep(fastPause);
        continue;
      }

      if (frame.type === "input") {
        await typeCommand(frame.text);
        await sleep(linePause);
        continue;
      }

      if (frame.type === "cmd") {
        appendPrompt(frame.text);
        await sleep(fastPause);
        continue;
      }

      if (frame.type === "promise") {
        appendPromise(frame.text);
        await sleep(linePause);
        continue;
      }

      if (frame.type === "dawn") {
        appendDawn(frame.text);
        if (status) {
          status.textContent = "● complete";
          status.style.color = "var(--amber-bright)";
        }
        await sleep(linePause * 1.5);
        continue;
      }

      // default output
      appendPlain(frame.text, frame.className);
      await sleep(frame.delay ?? linePause);
    }

    running = false;
  }

  // Replay when user clicks the terminal area (if they want)
  const terminal = document.querySelector(".terminal");
  if (terminal) {
    terminal.addEventListener("click", () => {
      if (!running) runAnimation();
    });
  }

  // Copy install command
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      const text = copyBtn.dataset.copy;
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.classList.add("copied");
        setTimeout(() => copyBtn.classList.remove("copied"), 1500);
      } catch {
        // ignore
      }
    });
  }

  // Start on first idle so content is visible without JS, then enhanced.
  if ("requestIdleCallback" in window) {
    requestIdleCallback(runAnimation, { timeout: 500 });
  } else {
    window.setTimeout(runAnimation, 100);
  }
})();
