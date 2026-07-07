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

  function clearOutput() {
    output.innerHTML = "";
    typed.textContent = "";
    inputLine.style.display = "none";
    setStatus("idle", "● ready");
    hideReportPreview();
  }

  function hideReportPreview() {
    var el = document.getElementById("report-browser");
    if (el) { el.classList.remove("open"); el.style.display = "none"; }
  }

  function setStatus(color, text) {
    if (!statusEl) return;
    statusEl.textContent = text;
    var colors = { idle: "var(--moon-dim)", working: "var(--amber-bright)", success: "var(--success)", done: "var(--amber-bright)" };
    statusEl.style.color = colors[color] || colors.idle;
  }

  function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  function scroll() { if (termBody) termBody.scrollTop = termBody.scrollHeight; }

  function addLine(html, cls) {
    var el = document.createElement("span");
    el.className = "line" + (cls ? " " + cls : "");
    el.innerHTML = html;
    output.appendChild(el);
    scroll();
  }

  function addText(text, cls) {
    var el = document.createElement("span");
    el.className = "line" + (cls ? " " + cls : "");
    el.textContent = text;
    output.appendChild(el);
    scroll();
  }

  function addPrompt(cmd) {
    addLine('<span class="prompt">$</span> <span class="cmd">' + esc(cmd) + "</span>", "cmd-line");
  }

  function addBlock(text, cls) {
    var b = document.createElement("pre");
    b.className = "tui-block" + (cls ? " " + cls : "");
    b.textContent = text;
    output.appendChild(b);
    scroll();
  }

  async function typeCmd(cmd) {
    inputLine.style.display = "flex";
    typed.textContent = "";
    for (var i = 0; i < cmd.length; i++) { typed.textContent += cmd[i]; await sleep(TYPE_SPEED); }
    await sleep(FAST_PAUSE);
    inputLine.style.display = "none";
    addPrompt(cmd);
  }

  async function typeAns(text) {
    inputLine.style.display = "flex";
    typed.textContent = "";
    await sleep(FAST_PAUSE * 2);
    for (var i = 0; i < text.length; i++) { typed.textContent += text[i]; await sleep(TYPE_SPEED); }
    await sleep(FAST_PAUSE);
    inputLine.style.display = "none";
    addLine('<span class="prompt">   &gt;</span> ' + esc(text), "answer-line");
  }

  async function printLines(lines, pause) {
    for (var i = 0; i < lines.length; i++) {
      addText(lines[i][0], lines[i][1]);
      await sleep(pause || LINE_PAUSE * 0.7);
    }
  }

  // ── Rich-style TUI rendered as HTML panels ──

  var TUI_FRAMES = [
    { moon: "🌒", elapsed: "0:42", iter: "#1", branch: "owloop/20250707-refactor-errors-a1b2c3d4", tokens: "2,140 / 200,000", specsDone: "0/3 done", progress: 0, current: "001-refactor-error-handling.md", status: "Working on spec", statusStyle: "amber",
      specs: [["active","001-refactor-error-handling.md"],["pending","002-add-type-annotations.md"],["pending","003-unify-error-codes.md"]],
      action: "Reading the spec and codebase", detail: "Scanning backend/app/api/ for ValidationError patterns" },
    { moon: "🌒", elapsed: "1:15", iter: "#1", branch: "owloop/20250707-refactor-errors-a1b2c3d4", tokens: "3,480 / 200,000", specsDone: "0/3 done", progress: 8, current: "001-refactor-error-handling.md", status: "Running acceptance criteria", statusStyle: "amber",
      specs: [["active","001-refactor-error-handling.md"],["pending","002-add-type-annotations.md"],["pending","003-unify-error-codes.md"]],
      action: "Running acceptance criteria", detail: 'grep -c "except ValidationError" backend/app/api/*.py → 3 (≤5 ✓)' },
    { moon: "🌓", elapsed: "1:23", iter: "#1", branch: "owloop/20250707-refactor-errors-a1b2c3d4", tokens: "4,120 / 200,000", specsDone: "0/3 done", progress: 15, current: "001-refactor-error-handling.md", status: "✓ done signal detected", statusStyle: "green",
      specs: [["active","001-refactor-error-handling.md"],["pending","002-add-type-annotations.md"],["pending","003-unify-error-codes.md"]],
      action: "Committing changes", detail: "🌙 Loop closed on iteration 1" },
    { moon: "🌓", elapsed: "1:58", iter: "#2", branch: "owloop/20250707-refactor-errors-a1b2c3d4", tokens: "6,820 / 200,000", specsDone: "1/3 done", progress: 33, current: "002-add-type-annotations.md", status: "Working on spec", statusStyle: "amber",
      specs: [["done","001-refactor-error-handling.md"],["active","002-add-type-annotations.md"],["pending","003-unify-error-codes.md"]],
      action: "Running verification commands", detail: "uv run pyright src/ --outputjson → 0 errors" },
    { moon: "🌔", elapsed: "2:12", iter: "#2", branch: "owloop/20250707-refactor-errors-a1b2c3d4", tokens: "8,240 / 200,000", specsDone: "1/3 done", progress: 42, current: "002-add-type-annotations.md", status: "✓ done signal detected", statusStyle: "green",
      specs: [["done","001-refactor-error-handling.md"],["active","002-add-type-annotations.md"],["pending","003-unify-error-codes.md"]],
      action: "Committing changes", detail: "🌙 Loop closed on iteration 2" },
    { moon: "🌔", elapsed: "2:47", iter: "#3", branch: "owloop/20250707-refactor-errors-a1b2c3d4", tokens: "10,540 / 200,000", specsDone: "2/3 done", progress: 66, current: "003-unify-error-codes.md", status: "Working on spec", statusStyle: "amber",
      specs: [["done","001-refactor-error-handling.md"],["done","002-add-type-annotations.md"],["active","003-unify-error-codes.md"]],
      action: "Running acceptance criteria", detail: "uv run pytest tests/ -q --tb=short → 148 passed" },
    { moon: "🌕", elapsed: "3:05", iter: "#3", branch: "owloop/20250707-refactor-errors-a1b2c3d4", tokens: "12,380 / 200,000", specsDone: "3/3 done", progress: 100, current: "—", status: "🌅 All specs complete", statusStyle: "green",
      specs: [["done","001-refactor-error-handling.md"],["done","002-add-type-annotations.md"],["done","003-unify-error-codes.md"]],
      action: "3 commits pushed to owloop/20250707-refactor-errors-a1b2c3d4", detail: "" },
  ];

  function specIcon(state) {
    if (state === "done") return '<span class="tui-icon tui-done">✓</span>';
    if (state === "active") return '<span class="tui-icon tui-active">🦉</span>';
    return '<span class="tui-icon tui-pending">○</span>';
  }

  function renderTuiHtml(f) {
    var pctWidth = f.progress;
    var statusCls = f.statusStyle === "green" ? "tui-val-green" : "tui-val-amber";

    var specRows = "";
    for (var i = 0; i < f.specs.length; i++) {
      specRows += '<div class="tui-spec-row">' + specIcon(f.specs[i][0]) + ' <span>' + esc(f.specs[i][1]) + '</span></div>';
    }

    var detailRow = f.detail ? '<div class="tui-detail">· ' + esc(f.detail) + '</div>' : '';

    return '<div class="tui-rich">' +
      '<div class="tui-panel tui-header-panel">' +
        '<div class="tui-header-row"><span class="tui-moon">' + f.moon + ' owloop</span><span class="tui-elapsed">' + f.elapsed + ' elapsed</span></div>' +
        '<div class="tui-tagline">Your code evolves while you sleep.</div>' +
      '</div>' +
      '<div class="tui-body">' +
        '<div class="tui-left">' +
          '<div class="tui-panel"><div class="tui-panel-title">Status</div>' +
            '<div class="tui-kv"><span class="tui-key">Model</span><span class="tui-val tui-val-cyan">claude-sonnet-5</span></div>' +
            '<div class="tui-kv"><span class="tui-key">Iteration</span><span class="tui-val">' + f.iter + '</span></div>' +
            '<div class="tui-kv"><span class="tui-key">Branch</span><span class="tui-val tui-val-green">' + esc(f.branch) + '</span></div>' +
            '<div class="tui-kv"><span class="tui-key">Tokens</span><span class="tui-val tui-val-cyan">' + f.tokens + '</span></div>' +
            '<div class="tui-kv"><span class="tui-key">Specs</span><span class="tui-val tui-val-green">' + f.specsDone + '</span></div>' +
            '<div class="tui-kv"><span class="tui-key">Current</span><span class="tui-val tui-val-amber">' + esc(f.current) + '</span></div>' +
            '<div class="tui-kv"><span class="tui-key">Status</span><span class="tui-val ' + statusCls + '">' + esc(f.status) + '</span></div>' +
          '</div>' +
          '<div class="tui-panel"><div class="tui-panel-title">Specs</div>' + specRows + '</div>' +
        '</div>' +
        '<div class="tui-right">' +
          '<div class="tui-panel tui-activity-panel"><div class="tui-panel-title">What Ollie is doing</div>' +
            '<div class="tui-action">' + esc(f.action) + '</div>' +
            detailRow +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="tui-panel tui-footer-panel">' +
        '<div class="tui-progress-track"><div class="tui-progress-fill" style="width:' + pctWidth + '%"></div></div>' +
        '<div class="tui-footer-row"><span>' + f.progress + '%</span><span class="tui-dim">ctrl+c to stop</span></div>' +
      '</div>' +
    '</div>';
  }

  function enterTui() {
    output.innerHTML = "";
    inputLine.style.display = "none";
    output.classList.add("tui-mode");
  }

  function exitTui() {
    output.innerHTML = "";
    output.classList.remove("tui-mode");
  }

  function showReportPreview() {
    var container = document.getElementById("report-browser");
    if (!container) {
      container = document.createElement("div");
      container.id = "report-browser";
      container.className = "report-browser";
      var demoSection = document.getElementById("demo");
      if (demoSection) demoSection.appendChild(container);
    }
    container.innerHTML =
      '<div class="browser-chrome" id="browser-drag-handle">' +
        '<div class="browser-dots"><span class="terminal-dot red"></span><span class="terminal-dot amber"></span><span class="terminal-dot green"></span></div>' +
        '<div class="browser-urlbar"><span class="browser-lock">🔒</span> file:///.owloop/logs/owloop_report.html</div>' +
        '<div class="browser-close" id="browser-close-btn">✕</div>' +
      '</div>' +
      '<div class="browser-body">' +
        '<div class="rpt-header">' +
          '<div class="rpt-owl">🦉</div>' +
          '<div class="rpt-title">owloop report</div>' +
          '<div class="rpt-tagline">Your code evolves while you sleep.</div>' +
        '</div>' +

        '<div class="rpt-cards">' +
          '<div class="rpt-card"><div class="rpt-card-val">owloop/20250707-refactor-errors-a1b2c3d4</div><div class="rpt-card-label">Branch</div></div>' +
          '<div class="rpt-card"><div class="rpt-card-val">3</div><div class="rpt-card-label">Iterations</div></div>' +
          '<div class="rpt-card"><div class="rpt-card-val rpt-green">Completed</div><div class="rpt-card-label">Status</div></div>' +
          '<div class="rpt-card"><div class="rpt-card-val">8 files · <span class="rpt-green">+328</span> · <span class="rpt-red">-108</span></div><div class="rpt-card-label">Total diff</div></div>' +
          '<div class="rpt-card"><div class="rpt-card-val">12,380</div><div class="rpt-card-label">Tokens used</div></div>' +
        '</div>' +

        '<div class="rpt-section">' +
          '<div class="rpt-section-title">AI Review Insights</div>' +
          '<div class="rpt-insight">' +
            '<div class="rpt-insight-title">Summary</div>' +
            '<p>Three focused refactoring specs completed successfully. The error handling consolidation reduced 69 scattered catch blocks to a single centralized handler. Type annotations were added to all API handlers. Error codes were unified under an ErrorCode enum.</p>' +
          '</div>' +
          '<div class="rpt-subsection-title">Key Changes</div>' +
          '<table class="rpt-table">' +
            '<thead><tr><th>File</th><th>Type</th><th>Risk</th><th>Description</th></tr></thead>' +
            '<tbody>' +
              '<tr><td><code>errors.py</code></td><td><span class="rpt-badge rpt-badge-amber">refactor</span></td><td><span class="rpt-badge rpt-badge-green">low</span></td><td>New centralized @app.errorhandler for ValidationError</td></tr>' +
              '<tr><td><code>types.py</code></td><td><span class="rpt-badge rpt-badge-cyan">feature</span></td><td><span class="rpt-badge rpt-badge-green">low</span></td><td>ErrorCode enum with 12 typed error constants</td></tr>' +
              '<tr><td><code>api/*.py</code></td><td><span class="rpt-badge rpt-badge-amber">refactor</span></td><td><span class="rpt-badge rpt-badge-amber">medium</span></td><td>Removed 66 try/except blocks, delegated to handler</td></tr>' +
            '</tbody>' +
          '</table>' +
          '<div class="rpt-subsection-title">Next Actions</div>' +
          '<div class="rpt-actions">' +
            '<div class="rpt-action"><span class="rpt-badge rpt-badge-red">now</span> Run full integration test suite before merging</div>' +
            '<div class="rpt-action"><span class="rpt-badge rpt-badge-amber">before merge</span> Review centralized error handler edge cases</div>' +
            '<div class="rpt-action"><span class="rpt-badge rpt-badge-green">nice to have</span> Add structured logging to error handler</div>' +
          '</div>' +
        '</div>' +

        '<div class="rpt-section">' +
          '<div class="rpt-section-title">Spec Status</div>' +
          '<table class="rpt-table">' +
            '<thead><tr><th>Spec</th><th>Priority</th><th>Status</th></tr></thead>' +
            '<tbody>' +
              '<tr><td>001-refactor-error-handling.md</td><td>1</td><td><span class="rpt-badge rpt-badge-green">done</span></td></tr>' +
              '<tr><td>002-add-type-annotations.md</td><td>2</td><td><span class="rpt-badge rpt-badge-green">done</span></td></tr>' +
              '<tr><td>003-unify-error-codes.md</td><td>3</td><td><span class="rpt-badge rpt-badge-green">done</span></td></tr>' +
            '</tbody>' +
          '</table>' +
        '</div>' +

        '<div class="rpt-section">' +
          '<div class="rpt-section-title">Diff Summary</div>' +
          '<pre class="rpt-diff"> backend/app/__init__.py    |  18 ++++++\n backend/app/api/orders.py  |  42 ++++-------\n backend/app/api/users.py   |  38 ++++------\n backend/app/api/items.py   |  56 +++++---------\n backend/app/errors.py      |  64 +++++++++++++++++\n backend/app/types.py       | 156 ++++++++++++++++++++++++++\n tests/test_errors.py       |  34 +++++++++\n tests/test_error_codes.py  |  28 ++++++++\n 8 files changed, 328 insertions(+), 108 deletions(-)</pre>' +
        '</div>' +

        '<div class="rpt-section">' +
          '<div class="rpt-section-title">Commits</div>' +
          '<table class="rpt-table">' +
            '<thead><tr><th>Commit</th><th>Message</th><th>Author</th><th>Changes</th></tr></thead>' +
            '<tbody>' +
              '<tr><td><code>a1b2c3d</code></td><td>refactor: extract ValidationError → @app.errorhandler</td><td>Claude (owloop)</td><td>4 files · <span class="rpt-green">+124</span> · <span class="rpt-red">-89</span></td></tr>' +
              '<tr><td><code>e4f5g6h</code></td><td>feat: add type annotations to api/ handlers</td><td>Claude (owloop)</td><td>3 files · <span class="rpt-green">+156</span> · <span class="rpt-red">-0</span></td></tr>' +
              '<tr><td><code>i7j8k9l</code></td><td>refactor: unify error codes with ErrorCode enum</td><td>Claude (owloop)</td><td>4 files · <span class="rpt-green">+48</span> · <span class="rpt-red">-19</span></td></tr>' +
            '</tbody>' +
          '</table>' +
        '</div>' +

        '<div class="rpt-footer">' +
          '<p>Generated by owloop on 2025-07-04 09:12:34</p>' +
          '<p>Branch diff: <code>8 files · +328 · -108</code></p>' +
          '<p>Review:</p>' +
          '<ul><li><code>git log --oneline HEAD~3..HEAD</code></li><li><code>git diff --stat HEAD~3..HEAD</code></li></ul>' +
        '</div>' +
      '</div>';

    container.style.display = "block";
    requestAnimationFrame(function () { container.classList.add("open"); });

    // Close button
    document.getElementById("browser-close-btn").addEventListener("click", function () {
      container.classList.remove("open");
      setTimeout(function () { container.style.display = "none"; }, 400);
    });

    // Drag support
    var handle = document.getElementById("browser-drag-handle");
    var dragging = false, startX = 0, startY = 0, origX = 0, origY = 0;

    handle.addEventListener("mousedown", function (e) {
      if (e.target.closest(".browser-close")) return;
      dragging = true;
      startX = e.clientX; startY = e.clientY;
      var rect = container.getBoundingClientRect();
      origX = rect.left;
      origY = rect.top;
      container.classList.add("dragged");
      container.style.left = origX + "px";
      container.style.top = origY + "px";
      container.style.transition = "none";
      e.preventDefault();
    });

    document.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      container.style.left = (origX + e.clientX - startX) + "px";
      container.style.top = (origY + e.clientY - startY) + "px";
    });

    document.addEventListener("mouseup", function () {
      if (dragging) {
        dragging = false;
        container.style.transition = "";
      }
    });
  }


  function showTuiFrame(idx) {
    output.innerHTML = renderTuiHtml(TUI_FRAMES[idx]);
    scroll();
  }

  async function runAnimation() {
    if (running) return;
    running = true;
    abortController = new AbortController();
    if (replayBtn) replayBtn.style.display = "none";

    try {
      clearOutput();
      setStatus("working", "● spec generation");

      // ── Phase 1: owloop spec ──
      await typeCmd('owloop spec "refactor error handling in the Flask API"');
      await sleep(LINE_PAUSE);

      await printLines([
        ["Scanning codebase (214 files, 28k lines)...", "dim"],
        ["Found 69 repeated except ValidationError blocks in backend/app/api/", "dim"],
        ["Calibrating baseline: ruff check → 0 errors, pytest → 142 passed", "dim"],
      ]);
      await sleep(LINE_PAUSE);

      addText("", "blank");
      addText("Need clarification (2 questions):", "");
      await sleep(LINE_PAUSE * 0.6);

      addText("", "blank");
      addText("1. Should public API response formats stay unchanged?", "");
      await sleep(LINE_PAUSE * 0.4);
      await typeAns("yes, keep all response shapes");
      await sleep(LINE_PAUSE * 0.5);

      addText("2. Which test command proves the refactor is correct?", "");
      await sleep(LINE_PAUSE * 0.4);
      await typeAns("uv run pytest tests/ -q");
      await sleep(LINE_PAUSE);

      addText("Drafting spec with exclusions and acceptance criteria...", "dim");
      await sleep(LINE_PAUSE * 1.2);

      addLine('<span class="success">✓</span> Spec saved: <span class="path">.owloop/specs/001-refactor-error-handling.md</span>');
      addLine('<span class="dim">  Requirements: extract 69 ValidationError blocks → @app.errorhandler</span>');
      addLine('<span class="dim">  Acceptance:   grep -c ≤ 5 · ruff 0 errors · pytest pass</span>');
      addLine('<span class="dim">  Exclusions:   no API format changes · no models/schemas/services</span>');
      await sleep(LINE_PAUSE * 1.5);

      // ── Phase 2: owloop run ──
      addText("", "blank");
      setStatus("working", "● loop running");
      await typeCmd("owloop run --max-tokens 200000");
      await sleep(FAST_PAUSE);

      await printLines([
        ["Ollie is waking up...", "dim"],
        ["→ worktree: ../flask-api-owloop-wt/owloop-20250707-refactor-errors-a1b2c3d4", "dim"],
        ["→ model: claude-sonnet-5    budget: 200k tokens", "dim"],
        ["→ specs: 3 queued", "dim"],
      ], LINE_PAUSE * 0.5);
      await sleep(LINE_PAUSE);

      // ── Phase 3: TUI full-screen ──
      enterTui();
      showTuiFrame(0); await sleep(TUI_FRAME_MS);
      showTuiFrame(1); await sleep(TUI_FRAME_MS);
      showTuiFrame(2); await sleep(TUI_FRAME_MS * 0.7);
      showTuiFrame(3); await sleep(TUI_FRAME_MS);
      showTuiFrame(4); await sleep(TUI_FRAME_MS * 0.7);
      showTuiFrame(5); await sleep(TUI_FRAME_MS);
      showTuiFrame(6); await sleep(TUI_FRAME_MS * 1.2);

      // ── Phase 4: exit TUI, time skip ──
      exitTui();
      setStatus("idle", "● sleeping");
      addText("", "blank");
      addText("⋯  you slept — Ollie didn't  ⋯", "time-skip");
      await sleep(LINE_PAUSE * 3);

      // ── Phase 5: morning review ──
      setStatus("done", "● morning review");
      addText("", "blank");
      await typeCmd("git log --oneline HEAD~3..HEAD");
      await sleep(FAST_PAUSE);

      await printLines([
        ["a1b2c3d  refactor: extract ValidationError → @app.errorhandler", ""],
        ["e4f5g6h  feat: add type annotations to api/ handlers", ""],
        ["i7j8k9l  refactor: unify error codes with ErrorCode enum", ""],
      ], LINE_PAUSE * 0.5);
      await sleep(LINE_PAUSE);

      await typeCmd("git diff --stat HEAD~3..HEAD");
      addBlock(
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

      await typeCmd("owloop report --open");
      await sleep(FAST_PAUSE);
      addLine('<span class="dawn">🌅 Report generated → .owloop/logs/owloop_report.html</span>');
      addLine('<span class="dim">   Opening in browser...</span>');
      await sleep(LINE_PAUSE);

      showReportPreview();
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
      var t = copyBtn.dataset.copy;
      if (!t) return;
      try { await navigator.clipboard.writeText(t); copyBtn.classList.add("copied"); setTimeout(function(){copyBtn.classList.remove("copied");},1500); } catch(err){}
    });
  }

  var section = document.getElementById("demo");
  if (section && "IntersectionObserver" in window) {
    var hasPlayed = false;
    new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting && !hasPlayed && !running) { hasPlayed = true; runAnimation(); }
    }, { threshold: 0.3 }).observe(section);
  }
})();
