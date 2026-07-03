(function () {
  "use strict";

  const output = document.getElementById("terminal-output");
  const inputLine = document.getElementById("terminal-input-line");
  const typed = document.getElementById("terminal-typed");
  const statusEl = document.getElementById("terminal-status");
  const copyBtn = document.querySelector(".copy-btn");
  const replayBtn = document.getElementById("terminal-replay");

  if (!output || !inputLine || !typed) return;

  const TYPE_SPEED = 22;
  const LINE_PAUSE = 420;
  const FAST_PAUSE = 120;
  const TUI_FRAME_MS = 1600;

  let abortController = null;
  let running = false;

  function sleep(ms) {
    return new Promise((resolve, reject) => {
      const id = setTimeout(resolve, ms);
      if (abortController) {
        abortController.signal.addEventListener("abort", () => {
          clearTimeout(id);
          reject(new DOMException("Aborted", "AbortError"));
        });
      }
    });
  }

  function clearTerminal() {
    output.innerHTML = "";
    typed.textContent = "";
    inputLine.style.display = "none";
    setStatus("idle", "● ready");
  }

  function setStatus(color, text) {
    if (!statusEl) return;
    statusEl.textContent = text;
    const colors = {
      idle: "var(--moon-dim)",
      working: "var(--amber-bright)",
      success: "var(--success)",
      done: "var(--amber-bright)",
    };
    statusEl.style.color = colors[color] || colors.idle;
  }

  function esc(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function scrollToBottom() {
    const body = output.closest(".terminal-body");
    if (body) body.scrollTop = body.scrollHeight;
  }

  function appendLine(html, className) {
    const el = document.createElement("span");
    el.className = "line" + (className ? " " + className : "");
    el.innerHTML = html;
    output.appendChild(el);
    scrollToBottom();
  }

  function appendPlain(text, className) {
    const el = document.createElement("span");
    el.className = "line" + (className ? " " + className : "");
    el.textContent = text;
    output.appendChild(el);
    scrollToBottom();
  }

  function appendPrompt(cmd) {
    appendLine(
      '<span class="prompt">$</span> <span class="cmd">' + esc(cmd) + "</span>",
      "cmd-line"
    );
  }

  function appendBlock(text, className) {
    const block = document.createElement("pre");
    block.className = "tui-block" + (className ? " " + className : "");
    block.textContent = text;
    output.appendChild(block);
    scrollToBottom();
    return block;
  }

  async function typeCommand(cmd) {
    inputLine.style.display = "flex";
    typed.textContent = "";
    for (let i = 0; i < cmd.length; i++) {
      typed.textContent += cmd[i];
      await sleep(TYPE_SPEED);
    }
    await sleep(FAST_PAUSE);
    inputLine.style.display = "none";
    appendPrompt(cmd);
  }

  async function typeAnswer(text) {
    inputLine.style.display = "flex";
    typed.textContent = "";
    await sleep(FAST_PAUSE);
    for (let i = 0; i < text.length; i++) {
      typed.textContent += text[i];
      await sleep(TYPE_SPEED);
    }
    await sleep(FAST_PAUSE);
    inputLine.style.display = "none";
    appendLine(
      '<span class="prompt">&gt;</span> ' + esc(text),
      "answer-line"
    );
  }

  async function printSlow(lines, pause) {
    for (const [text, cls] of lines) {
      appendPlain(text, cls);
      await sleep(pause || LINE_PAUSE * 0.6);
    }
  }

  // TUI frames that mirror the real owloop TUI layout
  // Based on src/owloop/tui.py panel structure
  function renderTuiFrame(frame) {
    const W = 62;
    const bar = frame.progress;
    const filled = Math.round(bar * 20);
    const progressBar = "█".repeat(filled) + "░".repeat(20 - filled);
    const tokenStr = frame.tokens;
    const specLines = frame.specs.map(function (s) {
      if (s[0] === "done") return "  ✓ " + s[1];
      if (s[0] === "active") return "  🦉 " + s[1];
      return "  ○ " + s[1];
    });

    const lines = [
      "┌─ " + frame.moon + " owloop ───────────────────────── " + frame.elapsed + " elapsed ─┐",
      "│  Your code evolves while you sleep.                        │",
      "├─ Status ──────────────────────────────────────────────────┤",
      "│  Model       claude-sonnet-4                              │",
      "│  Iteration   #" + String(frame.iter).padEnd(4) + (frame.maxIter ? " / " + frame.maxIter : "    ") + "                                     │",
      "│  Branch      " + frame.branch.padEnd(44) + "│",
      "│  Tokens      " + tokenStr.padEnd(44) + "│",
      "│  Specs       " + frame.specsSummary.padEnd(44) + "│",
      "│  Current     " + frame.currentSpec.padEnd(44) + "│",
      "│  Status      " + frame.status.padEnd(44) + "│",
      "├─ Specs ───────────────────────────────────────────────────┤",
    ];
    for (const sl of specLines) {
      lines.push("│" + sl.padEnd(W) + "│");
    }
    lines.push("├─ What Ollie is doing ────────────────────────────────────┤");
    lines.push("│  " + frame.action.padEnd(W - 2) + "│");
    if (frame.actionDetail) {
      lines.push("│    · " + frame.actionDetail.padEnd(W - 6) + "│");
    }
    lines.push("├──────────────────────────────────────────────────────────┤");
    lines.push("│  " + progressBar + "  " + String(Math.round(bar * 100)).padStart(3) + "%          ctrl+c to stop │");
    lines.push("└──────────────────────────────────────────────────────────┘");
    return lines.join("\n");
  }

  var TUI_FRAMES = [
    {
      moon: "🌒", elapsed: "0:42", iter: 1, maxIter: "", branch: "owloop/refactor-errors",
      tokens: "2,140 / 200,000", specsSummary: "0/3 done", progress: 0.0,
      currentSpec: "001-refactor-error-handling.md",
      status: "⠋ Working on spec",
      specs: [["active", "001-refactor-error-handling.md"], ["", "002-add-type-annotations.md"], ["", "003-unify-error-codes.md"]],
      action: "⠋ Running acceptance criteria",
      actionDetail: 'grep -c "except ValidationError" backend/app/api/*.py',
    },
    {
      moon: "🌓", elapsed: "1:23", iter: 2, maxIter: "", branch: "owloop/refactor-errors",
      tokens: "6,820 / 200,000", specsSummary: "1/3 done", progress: 0.33,
      currentSpec: "002-add-type-annotations.md",
      status: "⠹ Working on spec",
      specs: [["done", "001-refactor-error-handling.md"], ["active", "002-add-type-annotations.md"], ["", "003-unify-error-codes.md"]],
      action: "⠹ Running verification commands",
      actionDetail: "uv run pyright src/ --outputjson",
    },
    {
      moon: "🌔", elapsed: "2:07", iter: 3, maxIter: "", branch: "owloop/refactor-errors",
      tokens: "10,540 / 200,000", specsSummary: "2/3 done", progress: 0.66,
      currentSpec: "003-unify-error-codes.md",
      status: "⠴ Working on spec",
      specs: [["done", "001-refactor-error-handling.md"], ["done", "002-add-type-annotations.md"], ["active", "003-unify-error-codes.md"]],
      action: "⠴ Running acceptance criteria",
      actionDetail: "uv run pytest tests/ -q --tb=short",
    },
    {
      moon: "🌕", elapsed: "2:34", iter: 3, maxIter: "", branch: "owloop/refactor-errors",
      tokens: "12,380 / 200,000", specsSummary: "3/3 done", progress: 1.0,
      currentSpec: "—",
      status: "🌅 All specs complete",
      specs: [["done", "001-refactor-error-handling.md"], ["done", "002-add-type-annotations.md"], ["done", "003-unify-error-codes.md"]],
      action: "✓ 3 commits pushed to owloop/refactor-errors",
      actionDetail: "",
    },
  ];

  async function showTuiFrame(idx) {
    const existing = output.querySelector(".tui-frame");
    const text = renderTuiFrame(TUI_FRAMES[idx]);
    if (existing) {
      existing.textContent = text;
    } else {
      appendBlock(text, "tui-frame");
    }
    scrollToBottom();
  }

  async function runAnimation() {
    if (running) return;
    running = true;
    abortController = new AbortController();
    if (replayBtn) replayBtn.style.display = "none";

    try {
      clearTerminal();
      setStatus("working", "● spec generation");

      // Phase 1: owloop spec — generate spec from a vague goal
      await typeCommand('owloop spec "refactor error handling in the Flask API"');
      await sleep(LINE_PAUSE);

      await printSlow([
        ["Scanning codebase (214 files, 28k lines)...", "dim"],
        ["Found 69 repeated except ValidationError blocks in backend/app/api/", "dim"],
        ["Calibrating baseline: ruff check → 0 errors, pytest → 142 passed", "dim"],
      ]);
      await sleep(LINE_PAUSE * 0.5);

      appendLine(
        '<span class="code">⟨clarify⟩</span> <span class="dim">2 questions before I draft the spec:</span>'
      );
      await sleep(LINE_PAUSE * 0.5);

      await printSlow([
        ["1. Should public API response formats stay unchanged?", ""],
        ["2. Which test command proves the refactor is correct?", ""],
      ], LINE_PAUSE * 0.4);

      await typeAnswer("yes, keep API stable | uv run pytest tests/ -q");
      await sleep(LINE_PAUSE);

      appendPlain("Drafting spec with exclusions and acceptance criteria...", "dim");
      await sleep(LINE_PAUSE);

      appendLine(
        '<span class="success">✓</span> Spec saved: <span class="path">.owloop/specs/001-refactor-error-handling.md</span>'
      );
      appendLine(
        '<span class="dim">  Requirements: extract 69 ValidationError blocks → @app.errorhandler</span>'
      );
      appendLine(
        '<span class="dim">  Acceptance:   grep -c ≤ 5 · ruff 0 errors · pytest pass</span>'
      );
      appendLine(
        '<span class="dim">  Exclusions:   no API format changes · no models/schemas/services</span>'
      );
      await sleep(LINE_PAUSE);

      // Phase 2: owloop run — start the overnight loop
      appendPlain("", "blank");
      setStatus("working", "● loop running");
      await typeCommand("owloop run --max-tokens 200000");
      await sleep(FAST_PAUSE);

      await printSlow([
        ["Ollie is waking up...", "dim"],
        ["→ worktree: .worktrees/owloop-refactor-errors", "dim"],
        ["→ model: claude-sonnet-4    budget: 200k tokens", "dim"],
        ["→ specs: 3 queued (001-refactor-error-handling, 002-add-type-annotations, 003-unify-error-codes)", "dim"],
      ], LINE_PAUSE * 0.35);
      await sleep(LINE_PAUSE * 0.5);

      // Phase 3: TUI iteration frames — show the real panel layout
      await showTuiFrame(0);
      await sleep(TUI_FRAME_MS);

      appendLine(
        '<span class="success">✓</span> <span class="dim">001-refactor-error-handling.md</span> · grep -c → 3 (≤5 ✓) · ruff ✓ · pytest 142 passed · <span class="success">committed</span>'
      );
      await showTuiFrame(1);
      await sleep(TUI_FRAME_MS);

      appendLine(
        '<span class="success">✓</span> <span class="dim">002-add-type-annotations.md</span> · pyright 0 errors · pytest 142 passed · <span class="success">committed</span>'
      );
      await showTuiFrame(2);
      await sleep(TUI_FRAME_MS);

      appendLine(
        '<span class="success">✓</span> <span class="dim">003-unify-error-codes.md</span> · pytest 148 passed (+6 new) · <span class="success">committed</span>'
      );
      await showTuiFrame(3);
      await sleep(LINE_PAUSE);

      // Phase 4: time skip — Ollie works overnight
      setStatus("idle", "● sleeping");
      appendPlain("", "blank");
      appendPlain("⋯  you slept — Ollie didn't  ⋯", "time-skip");
      await sleep(LINE_PAUSE * 2.5);

      // Phase 5: morning review — check the results
      setStatus("done", "● morning review");
      appendPlain("", "blank");
      await typeCommand("git log --oneline HEAD~3..HEAD");
      await sleep(FAST_PAUSE);

      await printSlow([
        ["a1b2c3d  refactor: extract ValidationError → @app.errorhandler", ""],
        ["e4f5g6h  feat: add type annotations to api/ handlers", ""],
        ["i7j8k9l  refactor: unify error codes with ErrorCode enum", ""],
      ], LINE_PAUSE * 0.3);
      await sleep(LINE_PAUSE * 0.5);

      await typeCommand("git diff --stat HEAD~3..HEAD");
      appendBlock(
        " backend/app/__init__.py    |  18 ++++++\n" +
        " backend/app/api/orders.py  |  42 ++++-------\n" +
        " backend/app/api/users.py   |  38 ++++------\n" +
        " backend/app/api/items.py   |  56 +++++---------\n" +
        " backend/app/errors.py      |  64 +++++++++++++++++\n" +
        " backend/app/types.py       | 156 ++++++++++++++++++++++++++\n" +
        " tests/test_errors.py       |  34 +++++++++\n" +
        " tests/test_error_codes.py  |  28 ++++++++\n" +
        " 8 files changed, 328 insertions(+), 108 deletions(-)",
        "diff"
      );
      await sleep(LINE_PAUSE);

      await typeCommand("owloop report --open");
      await sleep(FAST_PAUSE);
      appendLine(
        '<span class="dawn">🌅 Report generated → .owloop/logs/owloop_report.html</span>'
      );
      appendLine(
        '<span class="dim">   3 specs completed · 3 commits · 12,380 tokens used · 0 failures</span>'
      );

      setStatus("done", "● complete — 3 specs, 12.4k tokens");

    } catch (e) {
      if (e.name !== "AbortError") throw e;
    } finally {
      running = false;
      abortController = null;
      if (replayBtn) replayBtn.style.display = "";
    }
  }

  // Replay button
  if (replayBtn) {
    replayBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      if (abortController) abortController.abort();
      running = false;
      setTimeout(runAnimation, 50);
    });
  }

  // Copy button
  if (copyBtn) {
    copyBtn.addEventListener("click", async function (e) {
      e.stopPropagation();
      var text = copyBtn.dataset.copy;
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.classList.add("copied");
        setTimeout(function () { copyBtn.classList.remove("copied"); }, 1500);
      } catch (err) {
        // ignore
      }
    });
  }

  // Auto-play when section scrolls into view
  var section = document.getElementById("demo");
  if (section && "IntersectionObserver" in window) {
    var hasPlayed = false;
    var observer = new IntersectionObserver(
      function (entries) {
        if (entries[0].isIntersecting && !hasPlayed && !running) {
          hasPlayed = true;
          runAnimation();
        }
      },
      { threshold: 0.3 }
    );
    observer.observe(section);
  }
})();
