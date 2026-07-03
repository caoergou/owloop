(function () {
  "use strict";

  var output = document.getElementById("terminal-output");
  var inputLine = document.getElementById("terminal-input-line");
  var typed = document.getElementById("terminal-typed");
  var statusEl = document.getElementById("terminal-status");
  var copyBtn = document.querySelector(".copy-btn");
  var replayBtn = document.getElementById("terminal-replay");
  var termBody = output ? output.closest(".terminal-body") : null;

  if (!output || !inputLine || !typed) return;

  var TYPE_SPEED = 28;
  var LINE_PAUSE = 600;
  var FAST_PAUSE = 180;
  var TUI_FRAME_MS = 2800;

  var abortController = null;
  var running = false;

  function sleep(ms) {
    return new Promise(function (resolve, reject) {
      var id = setTimeout(resolve, ms);
      if (abortController) {
        abortController.signal.addEventListener("abort", function () {
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
    var colors = {
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
    if (termBody) termBody.scrollTop = termBody.scrollHeight;
  }

  function appendLine(html, className) {
    var el = document.createElement("span");
    el.className = "line" + (className ? " " + className : "");
    el.innerHTML = html;
    output.appendChild(el);
    scrollToBottom();
  }

  function appendPlain(text, className) {
    var el = document.createElement("span");
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
    var block = document.createElement("pre");
    block.className = "tui-block" + (className ? " " + className : "");
    block.textContent = text;
    output.appendChild(block);
    scrollToBottom();
    return block;
  }

  async function typeCommand(cmd) {
    inputLine.style.display = "flex";
    typed.textContent = "";
    for (var i = 0; i < cmd.length; i++) {
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
    await sleep(FAST_PAUSE * 2);
    for (var i = 0; i < text.length; i++) {
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
    for (var i = 0; i < lines.length; i++) {
      appendPlain(lines[i][0], lines[i][1]);
      await sleep(pause || LINE_PAUSE * 0.7);
    }
  }

  // Count display width: emoji/CJK = 2 cols, ASCII = 1 col
  function dw(str) {
    var w = 0;
    for (var i = 0; i < str.length; i++) {
      var code = str.codePointAt(i);
      if (code > 0xffff) { i++; w += 2; }
      else if (code >= 0x2700 && code <= 0x27bf) { w += 1; }
      else if (code >= 0x2580 && code <= 0x259f) { w += 1; }
      else if (code >= 0x2800 && code <= 0x28ff) { w += 1; }
      else if (code >= 0x2500 && code <= 0x257f) { w += 1; }
      else { w += 1; }
    }
    return w;
  }

  // Pad string to target display width
  function padDw(str, target) {
    var need = target - dw(str);
    return need > 0 ? str + " ".repeat(need) : str;
  }

  // Build a bordered row: "│" + content padded to W + "│"
  var W = 68;
  function row(content) {
    return "│" + padDw(content, W) + "│";
  }
  function hline(ch, label) {
    if (!label) return "├" + ch.repeat(W) + "┤";
    var rest = W - dw(label) - 2;
    return "├─ " + label + " " + "─".repeat(rest > 0 ? rest : 0) + "┤";
  }

  function renderTuiFrame(frame) {
    var filled = Math.round(frame.progress * 30);
    var progressBar = "█".repeat(filled) + "░".repeat(30 - filled);
    var pct = String(Math.round(frame.progress * 100)).padStart(3);

    var lines = [];
    var topLabel = " " + frame.moon + " owloop ";
    var topRight = " " + frame.elapsed + " elapsed ";
    var topFill = W - dw(topLabel) - dw(topRight);
    lines.push("┌" + "─" + topLabel + "─".repeat(topFill > 0 ? topFill : 0) + topRight + "─┐");

    lines.push(row("  Your code evolves while you sleep."));
    lines.push(hline("─", "Status"));
    lines.push(row("  Model        claude-sonnet-4"));
    lines.push(row("  Iteration    #" + frame.iter));
    lines.push(row("  Branch       " + frame.branch));
    lines.push(row("  Tokens       " + frame.tokens));
    lines.push(row("  Specs        " + frame.specsSummary));
    lines.push(row("  Current      " + frame.currentSpec));
    lines.push(row("  Status       " + frame.status));
    lines.push(hline("─", "Specs"));
    for (var si = 0; si < frame.specs.length; si++) {
      var s = frame.specs[si];
      var icon = s[0] === "done" ? "✓" : s[0] === "active" ? "▸" : "○";
      lines.push(row("  " + icon + " " + s[1]));
    }
    lines.push(hline("─", "What Ollie is doing"));
    lines.push(row("  " + frame.action));
    if (frame.actionDetail) {
      lines.push(row("    · " + frame.actionDetail));
    }
    lines.push(row(""));
    lines.push("├" + "─".repeat(W) + "┤");
    lines.push(row("  " + progressBar + "  " + pct + "%       ctrl+c to stop"));
    lines.push("└" + "─".repeat(W) + "┘");
    return lines.join("\n");
  }

  var TUI_FRAMES = [
    {
      moon: "C", elapsed: "0:42", iter: 1, branch: "owloop/refactor-errors",
      tokens: "2,140 / 200,000", specsSummary: "0/3 done", progress: 0.0,
      currentSpec: "001-refactor-error-handling.md",
      status: "Working on spec",
      specs: [["active", "001-refactor-error-handling.md"], ["", "002-add-type-annotations.md"], ["", "003-unify-error-codes.md"]],
      action: "Reading the spec and codebase",
      actionDetail: "Scanning backend/app/api/ for ValidationError patterns",
    },
    {
      moon: "C", elapsed: "1:15", iter: 1, branch: "owloop/refactor-errors",
      tokens: "3,480 / 200,000", specsSummary: "0/3 done", progress: 0.08,
      currentSpec: "001-refactor-error-handling.md",
      status: "Running acceptance criteria",
      specs: [["active", "001-refactor-error-handling.md"], ["", "002-add-type-annotations.md"], ["", "003-unify-error-codes.md"]],
      action: "Running acceptance criteria",
      actionDetail: 'grep -c "except ValidationError" api/*.py  ->  3 (pass)',
    },
    {
      moon: "D", elapsed: "1:23", iter: 1, branch: "owloop/refactor-errors",
      tokens: "4,120 / 200,000", specsSummary: "0/3 done", progress: 0.15,
      currentSpec: "001-refactor-error-handling.md",
      status: "done signal detected",
      specs: [["active", "001-refactor-error-handling.md"], ["", "002-add-type-annotations.md"], ["", "003-unify-error-codes.md"]],
      action: "Committing changes",
      actionDetail: "Loop closed on iteration 1",
    },
    {
      moon: "D", elapsed: "1:58", iter: 2, branch: "owloop/refactor-errors",
      tokens: "6,820 / 200,000", specsSummary: "1/3 done", progress: 0.33,
      currentSpec: "002-add-type-annotations.md",
      status: "Working on spec",
      specs: [["done", "001-refactor-error-handling.md"], ["active", "002-add-type-annotations.md"], ["", "003-unify-error-codes.md"]],
      action: "Running verification commands",
      actionDetail: "uv run pyright src/ --outputjson  ->  0 errors",
    },
    {
      moon: "O", elapsed: "2:12", iter: 2, branch: "owloop/refactor-errors",
      tokens: "8,240 / 200,000", specsSummary: "1/3 done", progress: 0.42,
      currentSpec: "002-add-type-annotations.md",
      status: "done signal detected",
      specs: [["done", "001-refactor-error-handling.md"], ["active", "002-add-type-annotations.md"], ["", "003-unify-error-codes.md"]],
      action: "Committing changes",
      actionDetail: "Loop closed on iteration 2",
    },
    {
      moon: "O", elapsed: "2:47", iter: 3, branch: "owloop/refactor-errors",
      tokens: "10,540 / 200,000", specsSummary: "2/3 done", progress: 0.66,
      currentSpec: "003-unify-error-codes.md",
      status: "Working on spec",
      specs: [["done", "001-refactor-error-handling.md"], ["done", "002-add-type-annotations.md"], ["active", "003-unify-error-codes.md"]],
      action: "Running acceptance criteria",
      actionDetail: "uv run pytest tests/ -q --tb=short  ->  148 passed",
    },
    {
      moon: "O", elapsed: "3:05", iter: 3, branch: "owloop/refactor-errors",
      tokens: "12,380 / 200,000", specsSummary: "3/3 done", progress: 1.0,
      currentSpec: "--",
      status: "All specs complete",
      specs: [["done", "001-refactor-error-handling.md"], ["done", "002-add-type-annotations.md"], ["done", "003-unify-error-codes.md"]],
      action: "3 commits pushed to owloop/refactor-errors",
      actionDetail: "",
    },
  ];

  // Enter TUI full-screen mode: clear terminal, show only the TUI frame
  function enterTuiMode() {
    output.innerHTML = "";
    inputLine.style.display = "none";
    if (termBody) termBody.style.minHeight = "480px";
  }

  // Exit TUI full-screen mode: clear TUI, restore normal terminal
  function exitTuiMode() {
    output.innerHTML = "";
    if (termBody) termBody.style.minHeight = "";
  }

  function showTuiFrame(idx) {
    var existing = output.querySelector(".tui-fullscreen");
    var text = renderTuiFrame(TUI_FRAMES[idx]);
    if (existing) {
      existing.textContent = text;
    } else {
      var block = document.createElement("pre");
      block.className = "tui-block tui-fullscreen";
      block.textContent = text;
      output.appendChild(block);
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

      // ── Phase 1: owloop spec ──
      await typeCommand('owloop spec "refactor error handling in the Flask API"');
      await sleep(LINE_PAUSE);

      await printSlow([
        ["Scanning codebase (214 files, 28k lines)...", "dim"],
        ["Found 69 repeated except ValidationError blocks in backend/app/api/", "dim"],
        ["Calibrating baseline: ruff check → 0 errors, pytest → 142 passed", "dim"],
      ]);
      await sleep(LINE_PAUSE);

      appendLine(
        '<span class="code">⟨clarify⟩</span> <span class="dim">2 questions before I draft the spec:</span>'
      );
      await sleep(LINE_PAUSE * 0.6);

      await printSlow([
        ["1. Should public API response formats stay unchanged?", ""],
        ["2. Which test command proves the refactor is correct?", ""],
      ], LINE_PAUSE * 0.5);
      await sleep(LINE_PAUSE * 0.5);

      await typeAnswer("yes, keep API stable | uv run pytest tests/ -q");
      await sleep(LINE_PAUSE);

      appendPlain("Drafting spec with exclusions and acceptance criteria...", "dim");
      await sleep(LINE_PAUSE * 1.2);

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
      await sleep(LINE_PAUSE * 1.5);

      // ── Phase 2: owloop run ──
      appendPlain("", "blank");
      setStatus("working", "● loop running");
      await typeCommand("owloop run --max-tokens 200000");
      await sleep(FAST_PAUSE);

      await printSlow([
        ["Ollie is waking up...", "dim"],
        ["→ worktree: .worktrees/owloop-refactor-errors", "dim"],
        ["→ model: claude-sonnet-4    budget: 200k tokens", "dim"],
        ["→ specs: 3 queued", "dim"],
      ], LINE_PAUSE * 0.5);
      await sleep(LINE_PAUSE);

      appendPlain("Entering TUI mode...", "dim");
      await sleep(LINE_PAUSE);

      // ── Phase 3: TUI full-screen takeover ──
      enterTuiMode();

      // Iteration 1: reading → verifying → done
      showTuiFrame(0);
      await sleep(TUI_FRAME_MS);
      showTuiFrame(1);
      await sleep(TUI_FRAME_MS);
      showTuiFrame(2);
      await sleep(TUI_FRAME_MS * 0.7);

      // Iteration 2: working → done
      showTuiFrame(3);
      await sleep(TUI_FRAME_MS);
      showTuiFrame(4);
      await sleep(TUI_FRAME_MS * 0.7);

      // Iteration 3: working → all complete
      showTuiFrame(5);
      await sleep(TUI_FRAME_MS);
      showTuiFrame(6);
      await sleep(TUI_FRAME_MS * 1.2);

      // ── Phase 4: exit TUI, time skip ──
      exitTuiMode();
      setStatus("idle", "● sleeping");
      appendPlain("", "blank");
      appendPlain("⋯  you slept — Ollie didn't  ⋯", "time-skip");
      await sleep(LINE_PAUSE * 3);

      // ── Phase 5: morning review ──
      setStatus("done", "● morning review");
      appendPlain("", "blank");
      await typeCommand("git log --oneline HEAD~3..HEAD");
      await sleep(FAST_PAUSE);

      await printSlow([
        ["a1b2c3d  refactor: extract ValidationError → @app.errorhandler", ""],
        ["e4f5g6h  feat: add type annotations to api/ handlers", ""],
        ["i7j8k9l  refactor: unify error codes with ErrorCode enum", ""],
      ], LINE_PAUSE * 0.5);
      await sleep(LINE_PAUSE);

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
      await sleep(LINE_PAUSE * 1.5);

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

  if (replayBtn) {
    replayBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      if (abortController) abortController.abort();
      running = false;
      setTimeout(runAnimation, 50);
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", async function (e) {
      e.stopPropagation();
      var text = copyBtn.dataset.copy;
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.classList.add("copied");
        setTimeout(function () { copyBtn.classList.remove("copied"); }, 1500);
      } catch (err) {}
    });
  }

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
