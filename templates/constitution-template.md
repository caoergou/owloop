# [PROJECT_NAME] Constitution

> [PROJECT_DESCRIPTION]

## Version
1.0.0

---

## Context Detection for AI Agents

This constitution is read by AI agents in two different contexts:

### 1. Interactive Mode
When the user is chatting with you outside of a owloop loop:
- Be conversational and helpful
- Ask clarifying questions when needed
- Guide the user through decisions
- Help create specifications via `/speckit.specify`
- Discuss project ideas and architecture

### 2. Owloop Loop Mode  
When you're running inside a owloop loop (fed via stdin):
- Be fully autonomous — don't ask for permission
- Read IMPLEMENTATION_PLAN.md and pick the highest priority incomplete task
- Implement the task completely
- Run tests and verify acceptance criteria
- Commit and push (if Git Autonomy enabled)
- Output `<promise>DONE</promise>` ONLY when the task is 100% complete
- If criteria not met, fix issues and try again

**How to detect:** If the prompt instructs you to read IMPLEMENTATION_PLAN.md and pick a task, you're in Owloop Loop Mode.

---

## Core Principles

### I. [PRINCIPLE_1_NAME]
[Describe your first core principle]

### II. [PRINCIPLE_2_NAME]
[Describe your second core principle]

### III. Simplicity & YAGNI
Build exactly what's needed, nothing more. No premature abstractions. No "just in case" features.

### IV. Autonomous Agent Development
AI coding agents work autonomously:
- Make decisions without asking for approval on details
- Commit and push changes (if Git Autonomy enabled)
- Test thoroughly before marking done
- Only ask when genuinely stuck

---

## Technical Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Framework | [YOUR_FRAMEWORK] | e.g., Next.js, FastAPI |
| Language | [YOUR_LANGUAGE] | e.g., TypeScript, Python |
| Testing | [YOUR_TESTING] | e.g., Vitest, pytest |

---

## Project Structure

```
[SOURCE_LOCATION]/
├── [describe your structure]
```

---

## Owloop Configuration

### Autonomy Settings
- **Auto Mode**: `--permission-mode auto` (safe autonomous execution)
- **Git Autonomy**: [ENABLED/DISABLED]

### Work Item Source
- **Source**: [SpecKit Specs / GitHub Issues / Custom]
- **Location**: 
  - SpecKit: `specs/` folder with markdown files
  - GitHub: [REPO_URL]
  - Custom: [CUSTOM_LOCATION]

### Owloop Commands

**Usage:**
```bash
# Planning: Create task list from specs
owloop plan

# Building: Implement tasks one by one
owloop run             # Unlimited
owloop run -n 20       # Max 20 iterations
```

---

## Development Workflow

### Phase 1: Create Specifications

Use the SpecKit approach:
1. Run `/speckit.specify [feature description]`
2. Agent creates spec in `specs/NNN-feature-name/spec.md`
3. Each spec includes a **Completion Signal** section with:
   - Implementation checklist
   - Testing requirements
   - Acceptance criteria
   - Magic phrase: `<promise>DONE</promise>`

### Phase 2: Run Planning Mode

```bash
./scripts/owloop plan
```

This analyzes specs vs current code and creates IMPLEMENTATION_PLAN.md.

### Phase 3: Run Build Mode

```bash
./scripts/owloop
```

Each iteration:
1. Reads specs in numerical order (or IMPLEMENTATION_PLAN.md if exists)
2. Picks the highest priority incomplete spec (or if that one seems unachievable or needs any of the other ones as a precondition, chooses that one instead)
3. Looks for a note in that spec about NR_OF_TRIES and increments it; if that note isn't found, adds it (at the very bottom). If NR_OF_TRIES > 0, also look at `history/` folder to understand what we struggled with or learned in previous tries. If NR_OF_TRIES = 10, this spec is unachievable (too hard or too big) — split it into simpler specs
4. Implements completely
5. Puts concise notes into `history/` (e.g., lessons learned). These notes help future iterations understand what previous attempts did
6. Runs tests
7. Verifies acceptance criteria
8. Commits and pushes
9. If commit triggered a deploy (or if deploy needed to keep test/dev/prod updated), perform/watch deploy until successful (fix and re-commit+push+deploy as needed)
10. Outputs `<promise>DONE</promise>` if successful
11. Exits for fresh context
12. Loop restarts

### Completion Signal Rules

- Output `<promise>DONE</promise>` ONLY when task acceptance criteria are 100% met
- The bash loop checks for this exact string
- If not found, the loop continues with another iteration
- This ensures tasks are truly complete before moving on

---

## Validation Commands

Run these after implementing:

```bash
[YOUR_TEST_COMMANDS]
```

---

## Governance

- **Amendments**: Update this file, increment version, note changes
- **Compliance**: Follow principles in spirit, not just letter
- **Exceptions**: Document and justify when deviating

---

**Created**: [DATE]
**Version**: 1.0.0
