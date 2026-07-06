---
name: owloop-report
description: >-
  Generate rich, reviewable HTML reports for owloop autonomous loop runs.
  Use when user asks for owloop report, run summary, loop analysis,
  overnight run review, or wants a beautified artifact of what the loop did.
license: MIT
compatibility: Requires owloop methodology; works with or without the owloop CLI
metadata:
  author: caoergou
  version: "0.3.0"
  repository: https://github.com/caoergou/owloop
---

# Owloop Report

Owloop runs can produce a lot of output. A good report turns that output into a reviewable artifact: what was attempted, what succeeded, what failed, and what needs human attention next.

## When to Use

Use this skill when the user asks for:
- "generate an owloop report"
- "summarize the last owloop run"
- "what happened overnight?"
- "review my loop run"
- "create a report for the autonomous loop"
- "owloop report"

Also use when:
- A loop run just finished and the user needs a readable summary
- You want to surface blockers, risks, and next steps from `.owloop/logs/`

## When NOT to Use

- Do not use if the user only wants raw logs (point them to `.owloop/logs/`).
- Do not use if there is no owloop run data to summarize.

## Quick Start

If the owloop CLI is available, the built-in report command is the fastest path:

```bash
# AI-powered HTML report (default)
owloop report

# Offline fast report
owloop report --no-ai

# Generate and open with lavish-axi
owloop report --open
```

The built-in command writes to `.owloop/reports/owloop_report.html` by default. The `.owloop/reports/` directory is part of owloop runtime state and should not be committed.

## What a Good Report Contains

A reviewable owloop report should have these sections:

### 1. Executive Summary

One paragraph covering:
- How many specs were processed
- How many succeeded, failed, or were blocked
- Total runtime and token usage (if available)
- The single most important takeaway

Example:

```markdown
## Summary

- Specs processed: 5
- Succeeded: 3
- Blocked: 1 (`002-kimi-adapter` — permission mode mismatch)
- Failed: 1 (`004-report-ui` — baseline test still failing)
- Runtime: 3h 12m
- Recommendation: Review the blocked spec before re-running.
```

### 2. Per-Spec Breakdown

For each spec:
- Spec name and priority
- Final state: DONE / BLOCKED / DECIDE / FAILED
- Key actions taken (files changed, tests run)
- Blockers or risks
- Link to the spec file

### 3. Blockers & Risks

List everything that needs human attention:
- `<promise>BLOCKED:...</promise>` items
- Repeated failures (fix loops)
- Scope creep or unexpected file changes
- Security-sensitive changes
- Tests that were weakened or skipped

### 4. Verification Results

Summarize the verification commands that passed/failed:
- Lint/type check status
- Test suite status
- Any new failures introduced

### 5. Next Steps

Concrete recommendations:
- Which specs to re-run
- Which specs need human review
- Any follow-up specs to write

## How to Generate a Report

### Option 1: Use `owloop report` (recommended when CLI is available)

```bash
# Default AI-powered report
owloop report

# Specify output path
owloop report -o reports/owloop-run-2026-07-06.html

# Fast offline report
owloop report --no-ai

# Generate and open in browser
owloop report --open
```

### Option 2: When the CLI is unavailable

If the owloop CLI is not installed, build the report directly from loop state:

1. Read `.owloop/specs/*.md` to collect spec statuses (`**Status**: COMPLETE`, `## Blockers`, etc.).
2. Read `.owloop/logs/` or `run-notes.md` for iteration summaries.
3. Run `git log --oneline` on the loop branch to list commits.
4. Assemble the report sections described in [What a Good Report Contains](#what-a-good-report-contains).
5. Write a self-contained HTML or Markdown file to a path the user specifies.

> **Important:** Write reports under `.owloop/reports/` or another gitignored directory so generated artifacts are not committed to the repo.

### Option 3: Build a custom report from logs

If the built-in command is not enough, read the run logs and build a custom artifact:

```bash
# Find the latest log
ls -t .owloop/logs/*.md | head -1

# Read it and summarize the key events
cat .owloop/logs/owloop_run_*.md
```

Then create an HTML or Markdown artifact with the sections above.

### Option 4: Build an independent HTML artifact

If you need a custom report beyond what `owloop report` produces, generate HTML directly. Do not rely on the `lavish` skill.

Use the standard library or project dependencies to write a self-contained HTML file:

```python
from pathlib import Path

html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Owloop Run Report</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #222; }
    h1 { color: #d4a025; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }
    th { background: #f5f5f5; }
    .done { color: #2e7d32; }
    .blocked { color: #ed6c02; }
    .failed { color: #d32f2f; }
  </style>
</head>
<body>
  <h1>Owloop Run Report</h1>
  <!-- insert content here -->
</body>
</html>
"""

report_path = Path("reports/owloop_report.html")
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(html, encoding="utf-8")
```

For a complete starting template, see [references/report-template.md](references/report-template.md).

> **Note:** Choose a report output path under `.owloop/reports/` or another gitignored directory. Do not commit generated HTML artifacts to the repository.

## Report Design Guidelines

1. **Lead with the conclusion**
   - Busy users should understand the outcome in the first 3 lines.

2. **Use tables for per-spec breakdowns**
   - Tables make it easy to scan status across multiple specs.

3. **Highlight blockers in red/amber**
   - Anything requiring human attention should stand out visually.

4. **Include evidence, not opinions**
   - "Tests passed" is better than "looks good".
   - Link to specific commands and outputs.

5. **Keep it scannable**
   - Use headings, lists, and tables.
   - Avoid long paragraphs of raw log dumps.

## Anti-Patterns

1. **Dumping raw logs**
   - Bad: Pasting the entire `.owloop/logs/` content into the chat.
   - Good: Extracting the 5-10 most important events.

2. **Hiding blockers**
   - Bad: Report says "run complete" without mentioning the blocked spec.
   - Good: Blockers are in their own section at the top.

3. **AI-generated fluff**
   - Bad: Long paragraphs summarizing what is already in the logs.
   - Good: Structured facts with clear next steps.

## Example Report Outline

```markdown
# Owloop Run Report — 2026-07-06

## Summary
5 specs processed · 3 done · 1 blocked · 1 failed · 3h 12m

## Per-Spec Breakdown
| Spec | Status | Files | Notes |
|---|---|---|---|
| 001-fix-banner | ✅ DONE | `cli.py` | banner test passes |
| 002-kimi-adapter | ⚠️ BLOCKED | `adapters.py` | Kimi permission mode mismatch |
| 003-spec-rewrite | ✅ DONE | 4 skill files | npx skills discovers 4 skills |
| 004-report-ui | ❌ FAILED | `report.py` | baseline test still failing |
| 005-verify-skill | ✅ DONE | `owloop-verify/` | added code-review gate |

## Blockers & Risks
- **002-kimi-adapter**: Kimi `--prompt` cannot combine with `--auto`; needs config-based permission mode.
- **004-report-ui**: Same test failed 3 rounds — possible fix loop.

## Verification
- `pytest`: 188 passed, 2 failed (pre-existing)
- `ruff`: 0 errors
- `mypy`: 0 errors

## Next Steps
1. Fix Kimi permission mode documentation.
2. Split 004-report-ui into smaller specs.
3. Re-run after blockers resolved.
```

## References

- [Report Template](references/report-template.md)
