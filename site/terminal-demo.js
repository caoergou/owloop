(function () {
  "use strict";

  const output = document.getElementById("terminal-output");
  const cursor = document.getElementById("terminal-cursor");
  const replayBtn = document.getElementById("replay-btn");

  if (!output || !cursor || !replayBtn) return;

  const lines = [
    "$ owloop run",
    "🦉 Ollie is waking up...",
    "Iteration 1: 001-fix-lint.md → ✅ committed",
    "Iteration 2: 002-add-types.md → ✅ committed",
    "Iteration 3: 003-unify-errors.md → ✅ committed",
    "🌅 Complete. 3 specs done, 0 failures.",
  ];

  const lineDelay = 650;   // pause between lines
  const charDelay = 32;    // typing speed
  const initialDelay = 400;

  let animationFrame = null;
  let timeoutId = null;

  function clearTerminal() {
    output.textContent = "";
    cursor.style.display = "inline";
  }

  function sleep(ms) {
    return new Promise((resolve) => {
      timeoutId = window.setTimeout(resolve, ms);
    });
  }

  async function typeLine(line) {
    for (let i = 0; i < line.length; i++) {
      output.textContent += line[i];
      // Allow cancellation between characters
      await sleep(charDelay);
    }
  }

  async function runAnimation() {
    // Cancel any in-flight animation
    if (timeoutId) {
      window.clearTimeout(timeoutId);
      timeoutId = null;
    }
    if (animationFrame) {
      cancelAnimationFrame(animationFrame);
      animationFrame = null;
    }

    clearTerminal();
    replayBtn.disabled = true;

    await sleep(initialDelay);

    for (let i = 0; i < lines.length; i++) {
      await typeLine(lines[i]);
      if (i < lines.length - 1) {
        output.textContent += "\n";
        await sleep(lineDelay);
      }
    }

    replayBtn.disabled = false;
  }

  replayBtn.addEventListener("click", runAnimation);

  // Start on first idle so content is visible without JS, then enhanced.
  if ("requestIdleCallback" in window) {
    requestIdleCallback(runAnimation, { timeout: 500 });
  } else {
    animationFrame = requestAnimationFrame(runAnimation);
  }
})();
